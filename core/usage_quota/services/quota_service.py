"""
Quota Service for Usage Tracking and Enforcement.

Central service for checking quotas, deducting usage, and enforcing limits.
Uses Redis for fast quota checks with PostgreSQL as source of truth.

Key Design Decisions:
- Weekly window: FIXED (starts on first usage, expires after 7 days)
- Session window: FIXED (starts on first usage, expires after 3 hours)
- Race conditions: Prevented via select_for_update() on subscription
- Cache: Versioned keys for easy invalidation
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, TYPE_CHECKING

from django.core.cache import cache
from django.db import transaction, models
from django.utils import timezone

from usage_quota.models import (
    UsageLog,
    UserSubscription,
    SubscriptionPlan,
    FeatureType,
)
from usage_quota.exceptions import (
    QuotaExceededException,
    FeatureNotAvailableException,
    SubscriptionNotFoundException,
)

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_PREFIX = "quota:"
CACHE_TTL = 300  # 5 minutes

# Window configurations
WEEKLY_WINDOW_DAYS = 7  # Weekly limit: fixed window starting on first usage
SESSION_WINDOW_HOURS = 3  # Session limit: fixed window starting on first usage


@dataclass
class QuotaCheckResult:
    """Result of a quota check."""
    allowed: bool
    reason: Optional[str] = None
    remaining_weekly_usd: Decimal = Decimal('0')
    remaining_session_usd: Decimal = Decimal('0')
    weekly_limit_usd: Decimal = Decimal('0')
    session_limit_usd: Decimal = Decimal('0')
    weekly_used_usd: Decimal = Decimal('0')
    session_used_usd: Decimal = Decimal('0')
    # Window end times for user-friendly reset messages
    weekly_window_end: Optional[datetime] = None
    session_window_end: Optional[datetime] = None


@dataclass
class UsageDeductResult:
    """Result of a usage deduction."""
    success: bool
    usage_log_id: Optional[str] = None
    new_weekly_used_usd: Decimal = Decimal('0')
    new_remaining_weekly_usd: Decimal = Decimal('0')


@dataclass
class QuotaInfo:
    """Complete quota information for a user."""
    plan_name: str
    plan_display_name: str

    # Weekly limits (fixed 7-day window starting on first usage)
    weekly_limit_usd: Decimal
    weekly_used_usd: Decimal
    weekly_remaining_usd: Decimal
    window_start: str  # ISO format - when window started (empty if no active window)
    window_end: str  # ISO format - when window expires

    # Session limits (fixed 3-hour window starting on first usage)
    session_limit_usd: Decimal
    session_used_usd: Decimal
    session_remaining_usd: Decimal
    session_window_start: str  # ISO format - when session started (empty if no active session)
    session_window_end: str  # ISO format - when session expires

    # Feature access
    features: Dict[str, bool]

    # Breakdown by service
    by_service: Dict[str, Dict[str, Any]]

    # Breakdown by feature
    by_feature: Dict[str, Dict[str, Any]]


class QuotaService:
    """
    Central service for quota checking and usage tracking.

    All billable operations should call this service before proceeding.
    Uses Redis for real-time quota caching with database as source of truth.

    Window Types:
    - Weekly: FIXED window (starts on first usage, expires after 7 days)
    - Session: FIXED window (starts on first usage, expires after 3 hours)

    Thread Safety:
    - Use check_and_deduct() for atomic operations
    - Uses select_for_update() to prevent race conditions
    """

    # =========================================================================
    # Cache Management (Versioned Keys)
    # =========================================================================

    def _get_cache_version(self, user_id: str) -> int:
        """Get cache version for a user (incremented on each change)."""
        version_key = f"{CACHE_PREFIX}version:{user_id}"
        return cache.get(version_key, 0)

    def _increment_cache_version(self, user_id: str) -> None:
        """Increment cache version to invalidate all cached data for user."""
        version_key = f"{CACHE_PREFIX}version:{user_id}"
        try:
            cache.incr(version_key)
        except ValueError:
            cache.set(version_key, 1, timeout=None)  # No expiry on version

    def _get_cache_key(self, user_id: str, key_type: str) -> str:
        """Get versioned cache key."""
        version = self._get_cache_version(user_id)
        return f"{CACHE_PREFIX}{key_type}:{user_id}:v{version}"

    def _invalidate_user_cache(self, user_id: str) -> None:
        """Invalidate all cached data for a user by incrementing version."""
        self._increment_cache_version(user_id)
        # Also clear subscription cache (not versioned)
        cache.delete(f"{CACHE_PREFIX}subscription:{user_id}")

    # =========================================================================
    # Window Helpers
    # =========================================================================

    def _is_weekly_window_active(
        self,
        window_start: Optional[datetime],
    ) -> bool:
        """Check if the fixed weekly window is currently active."""
        if window_start is None:
            return False
        window_end = window_start + timedelta(days=WEEKLY_WINDOW_DAYS)
        return timezone.now() < window_end

    def _get_weekly_window_end(
        self,
        window_start: Optional[datetime],
    ) -> Optional[datetime]:
        """Get the end time of the fixed weekly window."""
        if window_start is None:
            return None
        return window_start + timedelta(days=WEEKLY_WINDOW_DAYS)

    def _is_session_window_active(
        self,
        window_start: Optional[datetime],
    ) -> bool:
        """Check if the fixed session window is currently active."""
        if window_start is None:
            return False
        window_end = window_start + timedelta(hours=SESSION_WINDOW_HOURS)
        return timezone.now() < window_end

    def _get_session_window_end(
        self,
        window_start: Optional[datetime],
    ) -> Optional[datetime]:
        """Get the end time of the fixed session window."""
        if window_start is None:
            return None
        return window_start + timedelta(hours=SESSION_WINDOW_HOURS)

    # =========================================================================
    # Usage Calculations
    # =========================================================================

    def get_weekly_usage(
        self,
        user: 'User',
        window_start: Optional[datetime],
    ) -> Decimal:
        """
        Get total usage within the fixed weekly window.

        Args:
            user: User to get usage for
            window_start: When the weekly window started (None = no active window)

        Returns:
            Total cost in USD within the active window, or 0 if window not active
        """
        if window_start is None:
            return Decimal('0')

        window_end = window_start + timedelta(days=WEEKLY_WINDOW_DAYS)
        if timezone.now() >= window_end:
            return Decimal('0')

        # Check cache
        cache_key = self._get_cache_key(str(user.id), "weekly_usage")
        cached = cache.get(cache_key)
        if cached is not None:
            return Decimal(str(cached))

        # Calculate from database
        total = UsageLog.objects.filter(
            user=user,
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        ).aggregate(
            total=models.Sum('cost_usd')
        )['total'] or Decimal('0')

        # Cache the result
        cache.set(cache_key, str(total), CACHE_TTL)
        return total

    def get_session_usage(
        self,
        user: 'User',
        window_start: Optional[datetime],
    ) -> Decimal:
        """
        Get total usage within the fixed session window.

        This is a rate limiter to prevent rapid spending bursts.
        Uses FIXED window (starts on first usage, expires after 3 hours).

        Args:
            user: User to get usage for
            window_start: When the session window started (None = no active session)

        Returns:
            Total cost in USD within the active session window, or 0 if no active session
        """
        if window_start is None:
            return Decimal('0')

        window_end = window_start + timedelta(hours=SESSION_WINDOW_HOURS)
        if timezone.now() >= window_end:
            return Decimal('0')

        # Check cache
        cache_key = self._get_cache_key(str(user.id), "session_usage")
        cached = cache.get(cache_key)
        if cached is not None:
            return Decimal(str(cached))

        # Calculate from database - fixed window
        total = UsageLog.objects.filter(
            user=user,
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        ).aggregate(
            total=models.Sum('cost_usd')
        )['total'] or Decimal('0')

        # Cache the result
        cache.set(cache_key, str(total), CACHE_TTL)
        return total

    # =========================================================================
    # Quota Check (Non-Atomic - for pre-flight checks)
    # =========================================================================

    def check_quota(
        self,
        user: 'User',
        service: str,
        estimated_cost_usd: Decimal,
        feature: str = FeatureType.CHAT,
        session_id: Optional[str] = None,
    ) -> QuotaCheckResult:
        """
        Pre-flight check before a billable operation.

        NOTE: This is NOT atomic. For atomic check+deduct, use check_and_deduct().

        Args:
            user: User making the request
            service: Service type (from ServiceType)
            estimated_cost_usd: Estimated cost of the operation
            feature: Feature type (from FeatureType)
            session_id: Optional session ID

        Returns:
            QuotaCheckResult indicating if the operation is allowed

        Raises:
            SubscriptionNotFoundException: If user has no subscription
        """
        subscription = self._get_or_create_subscription(user)
        if subscription is None:
            raise SubscriptionNotFoundException(str(user.id))

        # task 10: per-feature limit consultation lives here — consult
        # subscription.plan.get_per_feature_limits()[feature] when the
        # feature is gated by a count limit instead of (or in addition to)
        # the global weekly_limit_usd.
        weekly_limit = subscription.effective_weekly_limit
        session_limit = subscription.effective_session_limit

        # Get current usage (using fixed windows from subscription)
        weekly_used = self.get_weekly_usage(user, subscription.weekly_window_start)
        session_used = self.get_session_usage(user, subscription.session_window_start)

        # Calculate remaining
        weekly_remaining = max(Decimal('0'), weekly_limit - weekly_used)
        session_remaining = max(Decimal('0'), session_limit - session_used)

        # Calculate window end times for user-friendly messages
        weekly_window_end = self._get_weekly_window_end(subscription.weekly_window_start)
        session_window_end = self._get_session_window_end(subscription.session_window_start)

        # Check weekly limit
        if estimated_cost_usd > weekly_remaining:
            return QuotaCheckResult(
                allowed=False,
                reason="weekly",  # Just the limit type, not user-facing
                remaining_weekly_usd=weekly_remaining,
                remaining_session_usd=session_remaining,
                weekly_limit_usd=weekly_limit,
                session_limit_usd=session_limit,
                weekly_used_usd=weekly_used,
                session_used_usd=session_used,
                weekly_window_end=weekly_window_end,
                session_window_end=session_window_end,
            )

        # Check session limit (fixed)
        if estimated_cost_usd > session_remaining:
            return QuotaCheckResult(
                allowed=False,
                reason="session",  # Just the limit type, not user-facing
                remaining_weekly_usd=weekly_remaining,
                remaining_session_usd=session_remaining,
                weekly_limit_usd=weekly_limit,
                session_limit_usd=session_limit,
                weekly_used_usd=weekly_used,
                session_used_usd=session_used,
                weekly_window_end=weekly_window_end,
                session_window_end=session_window_end,
            )

        return QuotaCheckResult(
            allowed=True,
            remaining_weekly_usd=weekly_remaining,
            remaining_session_usd=session_remaining,
            weekly_limit_usd=weekly_limit,
            session_limit_usd=session_limit,
            weekly_used_usd=weekly_used,
            session_used_usd=session_used,
            weekly_window_end=weekly_window_end,
            session_window_end=session_window_end,
        )

    # =========================================================================
    # Atomic Check and Deduct (Race-Condition Safe)
    # =========================================================================

    @transaction.atomic
    def check_and_deduct(
        self,
        user: 'User',
        service: str,
        cost_usd: Decimal,
        feature: str = FeatureType.CHAT,
        session_id: Optional[str] = None,
        model_id: str = '',
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        character_count: int = 0,
        audio_seconds: float = 0,
        request_count: int = 1,
        request_id: str = '',
        extra_data: Optional[Dict] = None,
        billing_origin: str = 'platform',
    ) -> UsageDeductResult:
        """
        Atomic check and deduct - prevents race conditions.

        Use this when you need to ensure quota isn't exceeded by concurrent requests.
        Locks the subscription row during the operation.

        Args:
            user: User who made the request
            service: Service type (from ServiceType)
            cost_usd: Cost in USD
            feature: Feature type (from FeatureType)
            ... (other usage details)

        Returns:
            UsageDeductResult with new quota state

        Raises:
            QuotaExceededException: If quota would be exceeded
            SubscriptionNotFoundException: If user has no subscription
        """
        # Lock subscription row to prevent concurrent modifications
        subscription: Optional[UserSubscription]
        try:
            subscription = UserSubscription.objects.select_for_update().get(
                user=user,
                is_active=True,
            )
        except UserSubscription.DoesNotExist:
            # Create default subscription (outside lock)
            subscription = self._create_default_subscription(user)
            if not subscription:
                raise SubscriptionNotFoundException(str(user.id))
            # Re-fetch with lock
            subscription = UserSubscription.objects.select_for_update().get(
                user=user,
                is_active=True,
            )

        now = timezone.now()
        update_fields = []

        # Check and potentially start weekly window
        weekly_window_start = subscription.weekly_window_start
        if not self._is_weekly_window_active(weekly_window_start):
            # Start new weekly window
            weekly_window_start = now
            subscription.weekly_window_start = now
            update_fields.append('weekly_window_start')
            logger.info(f"Started new weekly window for user {user.id}")

        # Check and potentially start session window
        session_window_start = subscription.session_window_start
        if not self._is_session_window_active(session_window_start):
            # Start new session window
            session_window_start = now
            subscription.session_window_start = now
            update_fields.append('session_window_start')
            logger.info(f"Started new session window for user {user.id}")

        # Save any window updates
        if update_fields:
            update_fields.append('updated_at')
            subscription.save(update_fields=update_fields)

        # Calculate usage under lock (bypass cache for accuracy)
        weekly_used = self._calculate_weekly_usage_direct(user, weekly_window_start)
        session_used = self._calculate_session_usage_direct(user, session_window_start)

        weekly_limit = subscription.effective_weekly_limit
        session_limit = subscription.effective_session_limit

        # Check weekly limit
        if weekly_used + cost_usd > weekly_limit:
            window_end = self._get_weekly_window_end(weekly_window_start)
            resets_in = int((window_end - now).total_seconds()) if window_end else None
            raise QuotaExceededException(
                message="Weekly usage limit exceeded",
                limit_usd=weekly_limit,
                used_usd=weekly_used,
                remaining_usd=max(Decimal('0'), weekly_limit - weekly_used),
                limit_type="weekly",
                resets_in_seconds=resets_in,
            )

        # Check session limit (fixed)
        if session_used + cost_usd > session_limit:
            session_window_end = self._get_session_window_end(session_window_start)
            session_resets_in = int((session_window_end - now).total_seconds()) if session_window_end else None
            raise QuotaExceededException(
                message="Session rate limit exceeded. Try again in a few hours.",
                limit_usd=session_limit,
                used_usd=session_used,
                remaining_usd=max(Decimal('0'), session_limit - session_used),
                limit_type="session",
                resets_in_seconds=session_resets_in,
            )

        # Create usage log
        usage_log = UsageLog.objects.create(
            user=user,
            service=service,
            feature=feature,
            session_id=session_id or '',
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or (prompt_tokens + completion_tokens),
            character_count=character_count,
            audio_seconds=audio_seconds,
            request_count=request_count,
            cost_usd=cost_usd,
            request_id=request_id,
            extra_data=extra_data or {},
            billing_origin=billing_origin,
        )

        # Invalidate cache
        self._invalidate_user_cache(str(user.id))

        new_weekly_used = weekly_used + cost_usd
        new_remaining = weekly_limit - new_weekly_used

        logger.info(
            f"Usage deducted (atomic): user={user.id}, service={service}, "
            f"cost=${cost_usd}, new_weekly_used=${new_weekly_used}, "
            f"remaining=${new_remaining}"
        )

        return UsageDeductResult(
            success=True,
            usage_log_id=str(usage_log.id),
            new_weekly_used_usd=new_weekly_used,
            new_remaining_weekly_usd=new_remaining,
        )

    def _calculate_weekly_usage_direct(
        self,
        user: 'User',
        window_start: datetime,
    ) -> Decimal:
        """Calculate weekly usage directly from DB (bypasses cache)."""
        window_end = window_start + timedelta(days=WEEKLY_WINDOW_DAYS)
        return UsageLog.objects.filter(
            user=user,
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        ).aggregate(
            total=models.Sum('cost_usd')
        )['total'] or Decimal('0')

    def _calculate_session_usage_direct(
        self,
        user: 'User',
        window_start: datetime,
    ) -> Decimal:
        """Calculate session usage directly from DB (bypasses cache)."""
        window_end = window_start + timedelta(hours=SESSION_WINDOW_HOURS)
        return UsageLog.objects.filter(
            user=user,
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        ).aggregate(
            total=models.Sum('cost_usd')
        )['total'] or Decimal('0')

    # =========================================================================
    # Simple Deduct (For Backward Compatibility)
    # =========================================================================

    @transaction.atomic
    def deduct_usage(
        self,
        user: 'User',
        service: str,
        cost_usd: Decimal,
        feature: str = FeatureType.CHAT,
        session_id: Optional[str] = None,
        model_id: str = '',
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        character_count: int = 0,
        audio_seconds: float = 0,
        request_count: int = 1,
        request_id: str = '',
        extra_data: Optional[Dict] = None,
        billing_origin: str = 'platform',
    ) -> UsageDeductResult:
        """
        Record usage and update quota (with locking).

        This method logs usage but does NOT enforce quota limits.
        For enforcement, use check_and_deduct() instead.

        Note: Still uses select_for_update() for consistency but won't reject
        if quota is exceeded (for backward compatibility with existing code).
        """
        # Get or create subscription with lock
        subscription: Optional[UserSubscription]
        try:
            subscription = UserSubscription.objects.select_for_update().get(
                user=user,
                is_active=True,
            )
        except UserSubscription.DoesNotExist:
            subscription = self._create_default_subscription(user)
            if not subscription:
                raise SubscriptionNotFoundException(str(user.id))
            subscription = UserSubscription.objects.select_for_update().get(
                user=user,
                is_active=True,
            )

        now = timezone.now()
        update_fields = []

        # Start weekly window if needed
        if not self._is_weekly_window_active(subscription.weekly_window_start):
            subscription.weekly_window_start = now
            update_fields.append('weekly_window_start')
            logger.info(f"Started new weekly window for user {user.id}")

        # Start session window if needed
        if not self._is_session_window_active(subscription.session_window_start):
            subscription.session_window_start = now
            update_fields.append('session_window_start')
            logger.info(f"Started new session window for user {user.id}")

        # Save any window updates
        if update_fields:
            update_fields.append('updated_at')
            subscription.save(update_fields=update_fields)

        # Create usage log
        usage_log = UsageLog.objects.create(
            user=user,
            service=service,
            feature=feature,
            session_id=session_id or '',
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or (prompt_tokens + completion_tokens),
            character_count=character_count,
            audio_seconds=audio_seconds,
            request_count=request_count,
            cost_usd=cost_usd,
            request_id=request_id,
            extra_data=extra_data or {},
            billing_origin=billing_origin,
        )

        # Invalidate cache
        self._invalidate_user_cache(str(user.id))

        # Get new totals
        new_weekly_used = self.get_weekly_usage(user, subscription.weekly_window_start)
        weekly_limit = subscription.effective_weekly_limit
        new_remaining = max(Decimal('0'), weekly_limit - new_weekly_used)

        logger.info(
            f"Usage deducted: user={user.id}, service={service}, "
            f"cost=${cost_usd}, new_weekly_used=${new_weekly_used}, "
            f"remaining=${new_remaining}"
        )

        return UsageDeductResult(
            success=True,
            usage_log_id=str(usage_log.id),
            new_weekly_used_usd=new_weekly_used,
            new_remaining_weekly_usd=new_remaining,
        )

    # =========================================================================
    # Async Methods
    # =========================================================================

    async def acheck_quota(
        self,
        user: 'User',
        service: str,
        estimated_cost_usd: Decimal,
        feature: str = FeatureType.CHAT,
        session_id: Optional[str] = None,
        *,
        feature_name: Optional[str] = None,
        request_units: int = 1,
    ) -> QuotaCheckResult:
        """Async version of check_quota.

        When ``feature_name`` is passed, runs the same cascading guard as
        ``BillingService.check_quota``: feature-flag gate, per-feature
        count gate, then the USD-budget gate. Raises
        ``FeatureNotAvailableException`` or ``QuotaExceededException``
        on denial instead of returning ``allowed=False``.
        """
        from asgiref.sync import sync_to_async

        if feature_name is not None:
            from usage_quota.exceptions import (
                BillingMisconfiguration,
                FeatureNotAvailableException,
                QuotaExceededException,
            )
            from usage_quota.feature_registry import get as get_spec

            spec = get_spec(feature_name)
            if spec is None:
                raise BillingMisconfiguration(
                    f"Unknown feature_name: {feature_name!r}",
                    hint="Register it in core/usage_quota/feature_registry.py",
                )

            subscription = await sync_to_async(
                self._get_or_create_subscription
            )(user)
            plan = subscription.plan if subscription else None
            if plan is None:
                from usage_quota.models import SubscriptionPlan
                plan = await sync_to_async(SubscriptionPlan.get_default_plan)()

            if plan is not None:
                # 1. Flag gate
                if (
                    spec.flag_key is not None
                    and not plan.features.get(spec.flag_key, False)
                ):
                    raise FeatureNotAvailableException(
                        feature=feature_name,
                        plan_name=plan.display_name,
                        plan_slug=plan.name,
                    )

                # 2. Per-feature count/limit gate
                if spec.limit_field is not None:
                    limit = getattr(plan, spec.limit_field, None)
                    if limit == 0:
                        raise FeatureNotAvailableException(
                            feature=feature_name,
                            plan_name=plan.display_name,
                            plan_slug=plan.name,
                        )
                    if limit is not None and spec.count_provider is not None:
                        used = await sync_to_async(spec.count_provider)(user, plan)
                        if used + request_units > limit:
                            if spec.quota_window == 'storage':
                                resets_in = None
                            else:
                                from datetime import timedelta as _td
                                if subscription and subscription.weekly_window_start:
                                    end = subscription.weekly_window_start + _td(days=7)
                                    resets_in = max(
                                        0,
                                        int((end - timezone.now()).total_seconds()),
                                    )
                                else:
                                    resets_in = None
                            raise QuotaExceededException(
                                message=f"{feature_name} limit reached ({used}/{limit})",
                                limit_usd=Decimal('0'),
                                used_usd=Decimal('0'),
                                remaining_usd=Decimal('0'),
                                limit_type=spec.quota_window,
                                resets_in_seconds=resets_in,
                                feature_name=feature_name,
                                used_count=used,
                                limit_count=limit,
                            )

        return await sync_to_async(self.check_quota)(
            user, service, estimated_cost_usd, feature, session_id
        )

    async def adeduct_usage(
        self,
        user: 'User',
        service: str,
        cost_usd: Decimal,
        feature: str = FeatureType.CHAT,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> UsageDeductResult:
        """Async version of deduct_usage."""
        from asgiref.sync import sync_to_async
        return await sync_to_async(self.deduct_usage)(
            user, service, cost_usd, feature, session_id, **kwargs
        )

    async def acheck_and_deduct(
        self,
        user: 'User',
        service: str,
        cost_usd: Decimal,
        feature: str = FeatureType.CHAT,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> UsageDeductResult:
        """Async version of check_and_deduct."""
        from asgiref.sync import sync_to_async
        return await sync_to_async(self.check_and_deduct)(
            user, service, cost_usd, feature, session_id, **kwargs
        )

    # =========================================================================
    # Feature Access
    # =========================================================================

    def check_feature_access(
        self,
        user: 'User',
        feature: str,
    ) -> bool:
        """
        Check if user has access to a feature.

        Args:
            user: User to check
            feature: Feature name (e.g., 'voice_rooms', 'code_sessions')

        Returns:
            True if user has access

        Raises:
            FeatureNotAvailableException: If feature is not in user's plan
        """
        subscription = self._get_or_create_subscription(user)

        if subscription and subscription.has_feature(feature):
            return True

        plan_name = subscription.plan.display_name if subscription else "Free"
        raise FeatureNotAvailableException(feature, plan_name)

    # =========================================================================
    # Quota Info (for Settings UI)
    # =========================================================================

    def get_user_quota_info(self, user: 'User') -> QuotaInfo:
        """
        Get complete quota information for display in settings.

        Args:
            user: User to get quota info for

        Returns:
            QuotaInfo with all quota details
        """
        subscription = self._get_or_create_subscription(user)

        if not subscription:
            return QuotaInfo(
                plan_name='none',
                plan_display_name='No Plan',
                weekly_limit_usd=Decimal('0'),
                weekly_used_usd=Decimal('0'),
                weekly_remaining_usd=Decimal('0'),
                window_start='',
                window_end='',
                session_limit_usd=Decimal('0'),
                session_used_usd=Decimal('0'),
                session_remaining_usd=Decimal('0'),
                session_window_start='',
                session_window_end='',
                features={},
                by_service={},
                by_feature={},
            )

        weekly_limit = subscription.effective_weekly_limit
        session_limit = subscription.effective_session_limit

        # Weekly: Fixed window
        w_start = subscription.weekly_window_start
        if w_start is not None and self._is_weekly_window_active(w_start):
            weekly_used = self.get_weekly_usage(user, w_start)
            weekly_window_start = w_start.isoformat()
            w_end = self._get_weekly_window_end(w_start)
            weekly_window_end = w_end.isoformat() if w_end else ''
        else:
            weekly_used = Decimal('0')
            weekly_window_start = ''
            weekly_window_end = ''

        # Session: Fixed window (like weekly)
        s_start = subscription.session_window_start
        if s_start is not None and self._is_session_window_active(s_start):
            session_used = self.get_session_usage(user, s_start)
            session_window_start = s_start.isoformat()
            s_end = self._get_session_window_end(s_start)
            session_window_end = s_end.isoformat() if s_end else ''
        else:
            session_used = Decimal('0')
            session_window_start = ''
            session_window_end = ''

        weekly_remaining = max(Decimal('0'), weekly_limit - weekly_used)
        session_remaining = max(Decimal('0'), session_limit - session_used)

        # Get usage breakdown (only within active weekly window)
        active_w_start = w_start if weekly_window_start else None
        by_service = self._get_usage_by_service(user, active_w_start)
        by_feature = self._get_usage_by_feature(user, active_w_start)

        return QuotaInfo(
            plan_name=subscription.plan.name,
            plan_display_name=subscription.plan.display_name,
            weekly_limit_usd=weekly_limit,
            weekly_used_usd=weekly_used,
            weekly_remaining_usd=weekly_remaining,
            window_start=weekly_window_start,
            window_end=weekly_window_end,
            session_limit_usd=session_limit,
            session_used_usd=session_used,
            session_remaining_usd=session_remaining,
            session_window_start=session_window_start,
            session_window_end=session_window_end,
            features=subscription.plan.features,
            by_service=by_service,
            by_feature=by_feature,
        )

    # =========================================================================
    # Subscription Management
    # =========================================================================

    def _get_or_create_subscription(self, user: 'User') -> Optional[UserSubscription]:
        """Get user's subscription, creating default if needed."""
        subscription = self._get_subscription_cached(user)
        if subscription is None:
            subscription = self._create_default_subscription(user)
        return subscription

    def _get_subscription_cached(self, user: 'User') -> Optional[UserSubscription]:
        """Get user's subscription with caching."""
        cache_key = f"{CACHE_PREFIX}subscription:{user.id}"
        cached = cache.get(cache_key)
        if cached == 'none':
            return None
        if cached is not None:
            return cached

        try:
            subscription = UserSubscription.objects.select_related('plan').get(
                user=user,
                is_active=True,
            )
            cache.set(cache_key, subscription, CACHE_TTL)
            return subscription
        except UserSubscription.DoesNotExist:
            cache.set(cache_key, 'none', CACHE_TTL)
            return None

    def _create_default_subscription(self, user: 'User') -> Optional[UserSubscription]:
        """Create a subscription with the default plan for new users."""
        default_plan = SubscriptionPlan.get_default_plan()
        if not default_plan:
            logger.warning(f"No default plan found, cannot create subscription for user {user.id}")
            return None

        subscription, created = UserSubscription.objects.get_or_create(
            user=user,
            defaults={'plan': default_plan, 'is_active': True}
        )

        if created:
            logger.info(f"Created default subscription for user {user.id} with plan {default_plan.name}")
            self._invalidate_user_cache(str(user.id))

        return subscription

    # =========================================================================
    # Usage Breakdown Helpers
    # =========================================================================

    def _get_usage_by_service(
        self,
        user: 'User',
        window_start: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Get usage breakdown by service within the fixed window."""
        if window_start is None:
            return {}

        results = UsageLog.objects.filter(
            user=user,
            timestamp__gte=window_start,
        ).values('service').annotate(
            total_cost=models.Sum('cost_usd'),
            total_requests=models.Count('id'),
            total_tokens=models.Sum('total_tokens'),
            total_chars=models.Sum('character_count'),
            total_audio=models.Sum('audio_seconds'),
        )

        by_service = {}
        for row in results:
            service = row['service']
            cost = row['total_cost'] or Decimal('0')
            by_service[service] = {
                'used_usd': str(cost),
                'requests': row['total_requests'],
            }
            if row['total_tokens']:
                by_service[service]['tokens'] = row['total_tokens']
            if row['total_chars']:
                by_service[service]['characters'] = row['total_chars']
            if row['total_audio']:
                by_service[service]['audio_seconds'] = float(row['total_audio'])

        return by_service

    def _get_usage_by_feature(
        self,
        user: 'User',
        window_start: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Get usage breakdown by feature within the fixed window."""
        if window_start is None:
            return {}

        results = UsageLog.objects.filter(
            user=user,
            timestamp__gte=window_start,
        ).values('feature').annotate(
            total_cost=models.Sum('cost_usd'),
            total_requests=models.Count('id'),
        )

        return {
            row['feature']: {
                'used_usd': str(row['total_cost'] or Decimal('0')),
                'requests': row['total_requests'],
            }
            for row in results
        }

    # =========================================================================
    # Legacy Methods (Deprecated)
    # =========================================================================

    def get_rolling_usage(
        self,
        user: 'User',
        days: int = WEEKLY_WINDOW_DAYS,
    ) -> Decimal:
        """
        DEPRECATED: Use get_weekly_usage() for fixed windows.
        Get total usage over rolling window.
        """
        window_start = timezone.now() - timedelta(days=days)
        return UsageLog.objects.filter(
            user=user,
            timestamp__gte=window_start,
        ).aggregate(
            total=models.Sum('cost_usd')
        )['total'] or Decimal('0')

    def get_fixed_window_usage(
        self,
        user: 'User',
        window_start: Optional[datetime],
        duration: timedelta,
    ) -> Decimal:
        """
        DEPRECATED: Use get_weekly_usage() instead.
        Kept for backward compatibility.
        """
        if duration.days == WEEKLY_WINDOW_DAYS:
            return self.get_weekly_usage(user, window_start)
        elif duration.total_seconds() == SESSION_WINDOW_HOURS * 3600:
            return self.get_session_usage(user, window_start)
        else:
            # Generic fallback
            if window_start is None:
                return Decimal('0')
            window_end = window_start + duration
            if timezone.now() >= window_end:
                return Decimal('0')
            return UsageLog.objects.filter(
                user=user,
                timestamp__gte=window_start,
                timestamp__lt=window_end,
            ).aggregate(
                total=models.Sum('cost_usd')
            )['total'] or Decimal('0')


# Singleton instance
_quota_service: Optional[QuotaService] = None


def get_quota_service() -> QuotaService:
    """Get the singleton QuotaService instance."""
    global _quota_service
    if _quota_service is None:
        _quota_service = QuotaService()
    return _quota_service
