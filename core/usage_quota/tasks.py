"""
Celery tasks for Usage Quota system.

Handles retry logic for failed usage deductions to ensure no usage is lost.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Protocol

import stripe as _stripe
from celery import shared_task  # type: ignore[import-untyped]
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Redis key for storing failed deductions when Celery is unavailable
FAILED_DEDUCTIONS_KEY = "quota:failed_deductions"

# Maximum age for failed deductions before they're discarded (24 hours)
MAX_DEDUCTION_AGE_SECONDS = 86400


class _RedisListOps(Protocol):
    """Narrow view of the redis-py client's list commands this module
    needs. Django's cache API (BaseCache) has no LPOP/RPUSH/LLEN — the
    default cache backend must be a Redis-backed one for the failed
    deductions fallback queue below to function.
    """

    def lpop(self, name: str) -> Optional[bytes]: ...
    def rpush(self, name: str, *values: Any) -> int: ...
    def llen(self, name: str) -> int: ...


def _redis_list_client() -> _RedisListOps:
    """Reach through the Django cache wrapper to the underlying
    redis-py client, which exposes the native list commands Django's
    cache API does not.
    """
    # `_cache` is RedisCache's own implementation attribute (not part
    # of BaseCache's public contract), so this is a genuine framework
    # edge rather than something a narrower type could express.
    return cache._cache.get_client()  # type: ignore[attr-defined]


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
)
def retry_failed_deduction(self, deduction_data: Dict[str, Any]) -> bool:
    """
    Retry a failed usage deduction.

    This task is queued when a deduct_usage() call fails after a successful
    API operation. It ensures usage is eventually recorded even if there
    are temporary database or service issues.

    Args:
        deduction_data: Dictionary containing:
            - user_id: User ID
            - service: Service type (openrouter, elevenlabs_tts, etc.)
            - cost_usd: Cost in USD (string for Decimal precision)
            - feature: Feature type (chat, voice_room, etc.)
            - extra: Additional kwargs for deduct_usage

    Returns:
        True if deduction was successful
    """
    try:
        from usage_quota.services import get_quota_service
        from authentication.models import User

        user_id = deduction_data.get('user_id')
        if not user_id:
            logger.error("Failed deduction missing user_id")
            return False

        # Check if deduction is too old
        queued_at = deduction_data.get('queued_at')
        if queued_at:
            try:
                queued_time = datetime.fromisoformat(queued_at)
                age_seconds = (timezone.now() - queued_time).total_seconds()
                if age_seconds > MAX_DEDUCTION_AGE_SECONDS:
                    logger.warning(
                        f"Discarding stale failed deduction for user {user_id} "
                        f"(age: {age_seconds:.0f}s)"
                    )
                    return False
            except (ValueError, TypeError):
                pass

        # Get user
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found for failed deduction")
            return False

        # Get quota service
        quota_service = get_quota_service()

        # Extract deduction parameters
        service = deduction_data.get('service', '')
        cost_usd = Decimal(deduction_data.get('cost_usd', '0'))
        feature = deduction_data.get('feature', 'chat')
        extra = deduction_data.get('extra', {})

        # Perform deduction
        result = quota_service.deduct_usage(
            user=user,
            service=service,
            cost_usd=cost_usd,
            feature=feature,
            **extra
        )

        logger.info(
            f"Successfully retried failed deduction for user {user_id}: "
            f"service={service}, cost=${cost_usd}"
        )
        return result.success

    except Exception as e:
        logger.error(f"Failed to retry deduction (attempt {self.request.retries + 1}): {e}")
        raise  # Let Celery handle retry with backoff


@shared_task
def process_failed_deductions_queue() -> int:
    """
    Process any failed deductions stored in Redis.

    This is a periodic task that picks up failed deductions that couldn't
    be queued to Celery (e.g., when Celery was unavailable).

    Returns:
        Number of deductions processed
    """
    processed = 0

    try:
        redis_client = _redis_list_client()
        # Get all failed deductions from Redis list
        while True:
            raw = redis_client.lpop(FAILED_DEDUCTIONS_KEY)
            if not raw:
                break

            try:
                deduction_data = json.loads(raw)
                # Queue for processing
                retry_failed_deduction.delay(deduction_data)
                processed += 1
            except json.JSONDecodeError:
                logger.error(
                    "Invalid JSON in failed deductions queue: %r",
                    raw.decode(errors="replace"),
                )
            except Exception as e:
                logger.error(f"Failed to queue deduction for retry: {e}")
                # Put it back at the end of the queue
                redis_client.rpush(FAILED_DEDUCTIONS_KEY, raw)
                break

    except Exception as e:
        logger.error(f"Error processing failed deductions queue: {e}")

    if processed > 0:
        logger.info(f"Processed {processed} failed deductions from queue")

    return processed


def queue_failed_deduction(
    user_id: str,
    service: str,
    cost_usd: str,
    feature: str,
    **extra
) -> bool:
    """
    Queue a failed deduction for retry.

    Call this when deduct_usage() fails after a successful API operation.
    Tries to queue via Celery first, falls back to Redis if Celery unavailable.

    Args:
        user_id: User ID
        service: Service type
        cost_usd: Cost in USD (as string for precision)
        feature: Feature type
        **extra: Additional kwargs for deduct_usage

    Returns:
        True if successfully queued
    """
    deduction_data = {
        'user_id': str(user_id),
        'service': service,
        'cost_usd': str(cost_usd),
        'feature': feature,
        'extra': extra,
        'queued_at': timezone.now().isoformat(),
    }

    try:
        # Try async task first
        retry_failed_deduction.delay(deduction_data)
        logger.info(f"Queued failed deduction for retry: user={user_id}, service={service}")
        return True

    except Exception as e:
        logger.warning(f"Celery unavailable, storing in Redis: {e}")

        try:
            # Fallback: store in Redis for later processing
            _redis_list_client().rpush(
                FAILED_DEDUCTIONS_KEY, json.dumps(deduction_data)
            )
            logger.info(f"Stored failed deduction in Redis: user={user_id}, service={service}")
            return True
        except Exception as redis_error:
            logger.error(f"Failed to store deduction in Redis: {redis_error}")
            return False


def get_failed_deductions_count() -> int:
    """Get the number of failed deductions waiting in the Redis queue."""
    try:
        return _redis_list_client().llen(FAILED_DEDUCTIONS_KEY) or 0
    except Exception:
        return 0


@shared_task(
    bind=True,
    name="usage_quota.tasks.ensure_stripe_customer",
    max_retries=5,
    default_retry_delay=30,
    autoretry_for=(_stripe.RateLimitError, _stripe.APIConnectionError),
    retry_backoff=True,
    retry_backoff_max=600,
)
def ensure_stripe_customer(self, user_id: str) -> Optional[str]:
    """Asynchronously create a Stripe Customer for a new user (task 11).

    Hooked off the post_save(sender=User) signal — see
    ``authentication.signals.enqueue_stripe_customer_on_create``. The
    signal covers both email/password signup (RegisterView) and OAuth
    signup (allauth social_login).

    Idempotent: ``get_or_create_stripe_customer`` is a no-op when the
    user already has a ``stripe_customer_id``, so re-running this task
    across Celery retries / accidental re-deliveries is safe.

    The default ``UserSubscription`` (free plan) is created lazily by
    ``QuotaService`` on the user's first billable surface, so this
    task intentionally does not pre-create it here — doing so races
    with tests that assign a non-default plan immediately after user
    creation.

    Args:
        user_id: stringified ``User`` UUID.

    Returns:
        The ``cus_…`` string, or ``None`` if Stripe isn't configured.
    """
    from authentication.models import User
    from usage_quota.services.stripe_customer import (
        get_or_create_stripe_customer,
    )

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning("ensure_stripe_customer: user_id %s not found", user_id)
        return None

    return get_or_create_stripe_customer(user)
