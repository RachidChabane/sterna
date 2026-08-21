"""
Billing Service - Central Entry Point for All Billable Operations.

This service provides a unified interface for:
- Pre-flight quota checks
- Cost calculation
- Usage recording
- Quota status queries

All billable operations should go through this service.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from usage_quota.billing.operations import BillableOperation, QuotaStatus
from usage_quota.constants import (
    BILLING_ORIGIN_BYOK,
    BILLING_ORIGIN_PLATFORM,
    OPENROUTER_BACKED_SERVICES,
    PLATFORM_ONLY_SERVICES,
    VALID_BILLING_ORIGINS,
)
from usage_quota.exceptions import (
    BillingMisconfiguration,
    FeatureNotAvailableException,
    QuotaExceededException,
    SubscriptionNotFoundException,
)
from usage_quota.models import ServiceType, FeatureType, SubscriptionPlan, UsageLog
from usage_quota.services.cost_calculator import get_cost_calculator
from usage_quota.services.quota_service import get_quota_service, QuotaCheckResult

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)


class BillingService:
    """
    Centralized billing service for all billable operations.

    Single entry point for:
    - Pre-flight quota checks (check_quota)
    - Cost calculation (calculate_cost)
    - Usage recording (record_usage)
    - Atomic check and record (check_and_record)
    - Quota status queries (get_quota_status)

    Example usage:
        billing = get_billing_service()

        # Pre-flight check
        status = billing.check_quota(user, ServiceType.OPENROUTER, Decimal('0.01'))
        if not status.allowed:
            raise QuotaExceededException(...)

        # After operation completes
        operation = BillableOperation(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            model_id='anthropic/claude-3-5-sonnet',
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=Decimal('0.015'),
        )
        billing.record_usage(user, operation)
    """

    def __init__(self):
        self._quota_service = get_quota_service()
        self._cost_calculator = get_cost_calculator()

    def calculate_cost(self, operation: BillableOperation) -> Decimal:
        """
        Calculate cost for an operation using centralized pricing.

        If operation.cost_usd is already set (non-zero), returns that value.
        Otherwise calculates based on service type and metrics.

        Args:
            operation: The billable operation

        Returns:
            Cost in USD as Decimal
        """
        if operation.cost_usd > Decimal('0'):
            return operation.cost_usd

        return self._cost_calculator.calculate_cost(
            service=operation.service.value if hasattr(operation.service, 'value') else str(operation.service),
            model_id=operation.model_id or None,
            prompt_tokens=operation.prompt_tokens,
            completion_tokens=operation.completion_tokens,
            character_count=operation.character_count,
            audio_seconds=operation.audio_seconds,
            request_count=operation.request_count or 1,
        )

    def check_quota(
        self,
        user: 'User',
        service: ServiceType,
        estimated_cost: Decimal,
        feature: FeatureType = FeatureType.CHAT,
        assume_origin: Optional[str] = None,
        *,
        feature_name: Optional[str] = None,
        request_units: int = 1,
    ) -> QuotaStatus:
        """Pre-flight quota check. Does NOT deduct.

        When ``feature_name`` is passed, runs a cascading guard:
          1. feature-flag gate (raises ``FeatureNotAvailable``)
          2. per-feature limit gate (raises ``QuotaExceeded``)
          3. global weekly_limit_usd gate (existing logic; BYOK bypass
             lives inside ``_check_global_quota`` only)

        Ordering invariant: BYOK does NOT bypass steps 1 + 2. A personal
        OpenRouter key is not a license to call free-tier-disabled
        features.

        Backwards-compatible: callers that omit ``feature_name`` get the
        old behavior (USD-only check with BYOK fast-path intact via
        ``_check_global_quota``) and a ``QuotaStatus`` return value.
        When ``feature_name`` is set, denial converts to a raised
        exception so callers get uniform raise-semantics.
        """
        if feature_name is not None:
            from usage_quota.feature_registry import get as get_spec

            spec = get_spec(feature_name)
            if spec is None:
                raise BillingMisconfiguration(
                    f"Unknown feature_name: {feature_name!r}",
                    hint="Register it in core/usage_quota/feature_registry.py",
                )

            plan = self.get_user_plan(user)

            # 1. Flag gate
            if spec.flag_key is not None and not plan.features.get(spec.flag_key, False):
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
                    used = spec.count_provider(user, plan)
                    if used + request_units > limit:
                        if spec.quota_window == 'storage':
                            resets_in = None
                        else:
                            resets_in = self._weekly_resets_in_seconds(user)
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

        # 3. Fall through to existing USD-based global check.
        status = self._check_global_quota(
            user, service, estimated_cost, feature, assume_origin,
        )
        if feature_name is not None and not status.allowed:
            denial = status.denial_reason or 'weekly'
            raise QuotaExceededException(
                message=(
                    "Weekly usage limit exceeded"
                    if denial == 'weekly'
                    else "Session rate limit exceeded"
                ),
                limit_usd=(
                    status.weekly_limit_usd
                    if denial == 'weekly'
                    else status.session_limit_usd
                ),
                used_usd=(
                    status.weekly_used_usd
                    if denial == 'weekly'
                    else status.session_used_usd
                ),
                remaining_usd=(
                    status.weekly_remaining_usd
                    if denial == 'weekly'
                    else status.session_remaining_usd
                ),
                limit_type=denial,
                resets_in_seconds=(
                    status.weekly_resets_in_seconds
                    if denial == 'weekly'
                    else status.session_resets_in_seconds
                ),
                feature_name=feature_name,
            )
        return status

    def _check_global_quota(
        self,
        user: 'User',
        service: ServiceType,
        estimated_cost: Decimal,
        feature: FeatureType = FeatureType.CHAT,
        assume_origin: Optional[str] = None,
    ) -> QuotaStatus:
        """Global USD-based quota check (legacy body of check_quota).

        BYOK fast-path lives here so it bypasses ONLY the USD gate, not
        the feature-flag / per-feature-count gates in the caller.
        """
        service_value = service.value if hasattr(service, 'value') else str(service)
        feature_value = feature.value if hasattr(feature, 'value') else str(feature)

        # BYOK fast-path: only skip when the service is OpenRouter-backed.
        # PLATFORM_ONLY services always enforce quota — the user can't
        # bypass them with a personal OpenRouter key.
        if (
            assume_origin == BILLING_ORIGIN_BYOK
            and service_value in OPENROUTER_BACKED_SERVICES
            and service_value not in PLATFORM_ONLY_SERVICES
        ):
            return QuotaStatus(
                allowed=True,
                weekly_limit_usd=Decimal('0'),
                weekly_used_usd=Decimal('0'),
                weekly_remaining_usd=Decimal('0'),
                session_limit_usd=Decimal('0'),
                session_used_usd=Decimal('0'),
                session_remaining_usd=Decimal('0'),
                weekly_resets_in_seconds=0,
                session_resets_in_seconds=0,
                denial_reason=None,
            )

        result: QuotaCheckResult = self._quota_service.check_quota(
            user=user,
            service=service_value,
            estimated_cost_usd=estimated_cost,
            feature=feature_value,
        )

        from django.utils import timezone
        now = timezone.now()

        weekly_resets_in = 0
        if result.weekly_window_end:
            weekly_resets_in = max(0, int((result.weekly_window_end - now).total_seconds()))

        session_resets_in = 0
        if result.session_window_end:
            session_resets_in = max(0, int((result.session_window_end - now).total_seconds()))

        return QuotaStatus(
            allowed=result.allowed,
            weekly_limit_usd=result.weekly_limit_usd,
            weekly_used_usd=result.weekly_used_usd,
            weekly_remaining_usd=result.remaining_weekly_usd,
            session_limit_usd=result.session_limit_usd,
            session_used_usd=result.session_used_usd,
            session_remaining_usd=result.remaining_session_usd,
            weekly_resets_in_seconds=weekly_resets_in,
            session_resets_in_seconds=session_resets_in,
            denial_reason=result.reason if not result.allowed else None,
        )

    def _weekly_resets_in_seconds(self, user) -> Optional[int]:
        from django.utils import timezone

        sub = self._quota_service._get_or_create_subscription(user)
        if sub is None or sub.weekly_window_start is None:
            return None
        end = sub.weekly_window_start + timedelta(days=7)
        return max(0, int((end - timezone.now()).total_seconds()))

    def get_feature_usage(self, user: 'User', feature_name: str) -> dict:
        """Return ``{used, limit}`` for any feature with a count provider.

        For features without a per-feature limit (USD-only, or flag-only),
        both fields are ``None``.
        """
        from usage_quota.feature_registry import get as get_spec

        spec = get_spec(feature_name)
        if spec is None:
            return {'used': None, 'limit': None}
        plan = self.get_user_plan(user)
        if spec.limit_field is None or spec.count_provider is None:
            return {'used': None, 'limit': None}
        limit = getattr(plan, spec.limit_field, None)
        used = spec.count_provider(user, plan)
        return {'used': used, 'limit': limit}

    def _resolve_origin(
        self,
        operation: BillableOperation,
        service_value: str,
        billing_origin: Optional[str],
    ) -> str:
        """Resolve and validate the final billing_origin for an op.

        Precedence: explicit kwarg > operation.billing_origin > 'platform'.
        Raises BillingMisconfiguration on invalid origin OR when 'byok' is
        requested for a service that is not OpenRouter-backed.
        """
        final_origin = (
            billing_origin
            or getattr(operation, 'billing_origin', None)
            or BILLING_ORIGIN_PLATFORM
        )
        if final_origin not in VALID_BILLING_ORIGINS:
            raise BillingMisconfiguration(
                f"Invalid billing_origin: {final_origin!r}",
                hint=f"Valid origins: {sorted(VALID_BILLING_ORIGINS)}",
            )
        if (
            final_origin == BILLING_ORIGIN_BYOK
            and service_value not in OPENROUTER_BACKED_SERVICES
        ):
            raise BillingMisconfiguration(
                f"billing_origin='byok' is not permitted for service "
                f"{service_value!r} (not OpenRouter-backed).",
                hint=(
                    "Video, voice (TTS/STT), Brave Search, Google Maps and "
                    "transcription always bill the platform regardless of BYOK. "
                    "Either pass billing_origin='platform' or fix the caller."
                ),
            )
        return final_origin

    def _record_byok_analytics_row(
        self,
        user: 'User',
        operation: BillableOperation,
        would_have_cost: Decimal,
    ) -> None:
        """Write a UsageLog row for a BYOK call without touching quota state.

        Bypasses ``quota_service.deduct_usage`` because:
          - No weekly/session window should start (no platform spending).
          - No subscription row lock is needed (nothing to update).
          - No quota cache invalidation needed (totals unchanged).

        Preserves session_id and feature for analytics joins. The
        ``would_have_cost`` is logged (not stored) for observability.
        """
        service_value = (
            operation.service.value
            if hasattr(operation.service, 'value')
            else str(operation.service)
        )
        feature_value = (
            operation.feature.value
            if hasattr(operation.feature, 'value')
            else str(operation.feature)
        )
        UsageLog.objects.create(
            user=user,
            service=service_value,
            feature=feature_value,
            session_id=operation.session_id or '',
            model_id=operation.model_id or '',
            prompt_tokens=operation.prompt_tokens or 0,
            completion_tokens=operation.completion_tokens or 0,
            total_tokens=operation.total_tokens,
            character_count=operation.character_count or 0,
            audio_seconds=operation.audio_seconds or 0,
            request_count=operation.request_count or 1,
            cost_usd=Decimal('0'),
            request_id=operation.request_id or '',
            extra_data=operation.extra_data or {},
            billing_origin=BILLING_ORIGIN_BYOK,
        )
        logger.info(
            "billing.byok_bypass",
            extra={
                "user_id": str(user.id),
                "service": service_value,
                "feature": feature_value,
                "model_id": operation.model_id,
                "would_have_cost_usd": str(would_have_cost),
            },
        )

    def record_usage(
        self,
        user: 'User',
        operation: BillableOperation,
        *,
        billing_origin: Optional[str] = None,
    ) -> None:
        """
        Record usage after operation completes.

        Calculates cost if not already set on the operation.
        Does NOT enforce quota limits (use check_and_record for enforcement).

        Args:
            user: The user who made the request
            operation: The completed billable operation
            billing_origin: Optional override. If 'byok', writes a
                cost_usd=0 analytics row and skips quota deduction (the
                user pays OpenRouter directly). Raises
                BillingMisconfiguration if 'byok' is used with a
                non-OpenRouter-backed service.
        """
        # Calculate cost if not provided
        if operation.cost_usd == Decimal('0'):
            operation.cost_usd = self.calculate_cost(operation)

        service_value = (
            operation.service.value
            if hasattr(operation.service, 'value')
            else str(operation.service)
        )
        feature_value = (
            operation.feature.value
            if hasattr(operation.feature, 'value')
            else str(operation.feature)
        )

        final_origin = self._resolve_origin(operation, service_value, billing_origin)
        operation.billing_origin = final_origin

        if final_origin == BILLING_ORIGIN_BYOK:
            # BYOK rows have cost_usd=0 — the user pays OpenRouter directly.
            # We still record the row for analytics (model_id, tokens, etc.).
            self._record_byok_analytics_row(user, operation, operation.cost_usd)
            return

        try:
            self._quota_service.deduct_usage(
                user=user,
                service=service_value,
                cost_usd=operation.cost_usd,
                feature=feature_value,
                model_id=operation.model_id,
                prompt_tokens=operation.prompt_tokens,
                completion_tokens=operation.completion_tokens,
                total_tokens=operation.total_tokens,
                character_count=operation.character_count,
                audio_seconds=operation.audio_seconds,
                request_count=operation.request_count or 1,
                request_id=operation.request_id,
                session_id=operation.session_id,
                extra_data=operation.extra_data,
                billing_origin=final_origin,
            )
            logger.info(
                "billing.usage_recorded",
                extra={
                    "service": service_value,
                    "feature": feature_value,
                    "cost_usd": str(operation.cost_usd),
                    "user_id": str(user.id),
                    "billing_origin": final_origin,
                },
            )
        except Exception:
            # Queue for retry - never lose usage data
            logger.error(
                "billing.deduct_failed",
                extra={"user_id": str(user.id)},
                exc_info=True,
            )
            self._queue_failed_deduction(user, operation)

    def check_and_record(
        self,
        user: 'User',
        operation: BillableOperation,
        enforce_quota: bool = True,
        *,
        billing_origin: Optional[str] = None,
    ) -> None:
        """
        Atomic check and record. Use for critical operations.

        This method:
        1. Calculates cost if not set
        2. Checks quota (if enforce_quota=True)
        3. Records usage atomically

        Args:
            user: The user making the request
            operation: The billable operation
            enforce_quota: If True, raises QuotaExceededException when exceeded
            billing_origin: Optional override. If 'byok', skips
                check_and_deduct entirely and writes a BYOK analytics row
                (cost_usd=0). Raises BillingMisconfiguration if 'byok' is
                passed for a non-OpenRouter-backed service.

        Raises:
            QuotaExceededException: If quota exceeded and enforce_quota=True
        """
        # Calculate cost if not provided
        if operation.cost_usd == Decimal('0'):
            operation.cost_usd = self.calculate_cost(operation)

        service_value = (
            operation.service.value
            if hasattr(operation.service, 'value')
            else str(operation.service)
        )
        feature_value = (
            operation.feature.value
            if hasattr(operation.feature, 'value')
            else str(operation.feature)
        )

        final_origin = self._resolve_origin(operation, service_value, billing_origin)
        operation.billing_origin = final_origin

        if final_origin == BILLING_ORIGIN_BYOK:
            # BYOK: no quota to enforce — the user pays OpenRouter directly.
            self._record_byok_analytics_row(user, operation, operation.cost_usd)
            return

        if enforce_quota:
            self._quota_service.check_and_deduct(
                user=user,
                service=service_value,
                cost_usd=operation.cost_usd,
                feature=feature_value,
                model_id=operation.model_id,
                prompt_tokens=operation.prompt_tokens,
                completion_tokens=operation.completion_tokens,
                total_tokens=operation.total_tokens,
                character_count=operation.character_count,
                audio_seconds=operation.audio_seconds,
                request_count=operation.request_count or 1,
                request_id=operation.request_id,
                session_id=operation.session_id,
                extra_data=operation.extra_data,
                billing_origin=final_origin,
            )
        else:
            self.record_usage(user, operation, billing_origin=final_origin)

    def get_quota_status(self, user: 'User') -> QuotaStatus:
        """
        Get user's current quota status.

        Args:
            user: The user to get status for

        Returns:
            QuotaStatus with current limits and usage
        """
        return self.check_quota(
            user=user,
            service=ServiceType.OPENROUTER,  # Service doesn't matter for status query
            estimated_cost=Decimal('0'),
            feature=FeatureType.CHAT,
            assume_origin=None,
        )

    @property
    def quota_service(self):
        """Public accessor for the underlying QuotaService.

        Used by tests that need to patch quota_service methods. Production
        callers should use the BillingService API, not poke at the
        QuotaService directly.
        """
        return self._quota_service

    def get_user_plan(self, user: 'User') -> SubscriptionPlan:
        """Return the user's active SubscriptionPlan.

        Falls back to the default plan if the user has no subscription yet.
        Raises SubscriptionNotFoundException if there is no default plan
        configured (a server-misconfiguration state, not a user state).
        """
        subscription = self._quota_service._get_or_create_subscription(user)
        if subscription is not None:
            return subscription.plan
        default = SubscriptionPlan.get_default_plan()
        if default is None:
            raise SubscriptionNotFoundException(str(user.id))
        return default

    def invalidate_for_user(self, user: 'User') -> None:
        """Drop the per-user quota cache.

        Used by the post-checkout reconcile path (task 12) and the
        webhook handler (task 13) so a plan change is visible on the
        next read without waiting for the cache TTL. Wraps the
        ``QuotaService._invalidate_user_cache`` private helper so the
        view-layer doesn't reach across class boundaries.
        """
        self._quota_service._invalidate_user_cache(str(user.id))

    def check_feature_access(self, user: 'User', feature_name: str) -> bool:
        """Return True iff the user's plan grants ``feature_name``.

        Unlike :meth:`QuotaService.check_feature_access` (which raises),
        this returns a bool — the call surface used by view-layer gates
        and the frontend PlanCard. Delegates the JSON lookup to
        :meth:`SubscriptionPlan.has_feature` so there is exactly one
        source of truth for "is this feature in the plan".
        """
        plan = self.get_user_plan(user)
        return plan.has_feature(feature_name)

    def _queue_failed_deduction(self, user: 'User', operation: BillableOperation) -> None:
        """Queue failed deduction for async retry."""
        try:
            from usage_quota.tasks import queue_failed_deduction
            queue_failed_deduction({
                'user_id': str(user.id),
                'operation': operation.to_dict(),
            })
        except Exception:
            # Last resort: log for manual recovery
            logger.critical(
                "billing.queue_failed_critical",
                extra={
                    "user_id": str(user.id),
                    "operation": operation.to_dict(),
                },
                exc_info=True,
            )


# Singleton instance
_billing_service: Optional[BillingService] = None


def get_billing_service() -> BillingService:
    """Get the singleton BillingService instance."""
    global _billing_service
    if _billing_service is None:
        _billing_service = BillingService()
    return _billing_service
