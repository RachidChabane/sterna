"""Celery tasks for the LLM app.

Server-side settlement of aborted streaming completions.

When a user aborts a stream (Stop button / client disconnect), the
frontend *may* PATCH the stopped message with post-hoc usage numbers —
but that path is client-driven and advisory only (see
``conversations.views.MessageViewSet.perform_update``). To guarantee
aborted requests end up billed even when the client never PATCHes, the
stream views enqueue :func:`settle_aborted_generations` on disconnect.
The task waits for OpenRouter to finalize the generation records, then
bills the *true* cost per generation id through ``BillingService``.

Idempotency: each settled generation id is written to
``UsageLog.request_id``. Both this task (across retries / duplicate
deliveries) and the inline per-iteration billing in
``client.OpenRouterClient._log_usage`` (Direct Client path) use that
column as the guard, so a generation is never billed twice.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Delay before the first settlement attempt — OpenRouter takes ~15-20s
# to finalize generation data after a stream ends.
ABORT_SETTLEMENT_DELAY_SECONDS = 30

# Cache marker consumed by conversations.views.MessageViewSet.perform_update:
# when set for a chat, a server-side settlement is pending/complete and the
# client PATCH must not create its own UsageLog row (double-bill guard).
ABORT_SETTLEMENT_CACHE_KEY = "billing:abort_settlement:{chat_id}"
ABORT_SETTLEMENT_CACHE_TTL = 15 * 60  # seconds

OPENROUTER_GENERATION_URL = "https://openrouter.ai/api/v1/generation"


def fetch_generation_data(
    api_key: str,
    generation_id: str,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Fetch a single generation record from OpenRouter.

    Returns the ``data`` dict (``tokens_prompt``, ``tokens_completion``,
    ``total_cost``, ``model``, ...) or None when the record is not (yet)
    available. Network errors propagate to the caller so Celery retry
    policies can handle them; a 404 returns None (not finalized yet).
    """
    with httpx.Client(timeout=timeout) as client:
        response = client.get(
            f"{OPENROUTER_GENERATION_URL}?id={generation_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if response.status_code == 200:
        return response.json().get("data") or None
    if response.status_code == 404:
        return None
    # Unexpected upstream status — raise so the task retries with backoff.
    raise RuntimeError(
        f"OpenRouter generation lookup returned {response.status_code} "
        f"for {generation_id}"
    )


def _is_generation_settled(user, generation_id: str) -> bool:
    """True when a UsageLog row already exists for this generation id."""
    from usage_quota.models import ServiceType, UsageLog

    return UsageLog.objects.filter(
        user=user,
        service=ServiceType.OPENROUTER,
        request_id=generation_id,
    ).exists()


@shared_task(
    bind=True,
    name="llm.tasks.settle_aborted_generations",
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
)
def settle_aborted_generations(
    self,
    user_id: str,
    generation_ids: List[str],
    model_id: str = "",
    session_id: str = "",
) -> Dict[str, int]:
    """Bill the true cost of an aborted stream's generations.

    For each generation id: skip if already settled (idempotent), query
    OpenRouter for the finalized usage, and record it via
    ``BillingService.record_usage`` with ``request_id=generation_id``.

    Safe when OpenRouter is unreachable: any raise triggers Celery
    autoretry with exponential backoff; after ``max_retries`` the task
    gives up with a structured error log (ids settled by earlier
    attempts stay settled — the request_id guard makes re-runs no-ops).
    """
    from authentication.models import User
    from llm.services.api_key_resolver import get_api_key_for_user, resolve_with_origin
    from usage_quota.billing.operations import BillableOperation
    from usage_quota.billing.service import get_billing_service
    from usage_quota.models import FeatureType, ServiceType

    result = {"settled": 0, "skipped": 0, "pending": 0}

    if not user_id or not generation_ids:
        return result

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(
            "billing.abort_settlement_user_missing",
            extra={"user_id": str(user_id)},
        )
        return result

    api_key = get_api_key_for_user(user)
    if not api_key:
        logger.error(
            "billing.abort_settlement_no_api_key",
            extra={"user_id": str(user_id)},
        )
        return result

    try:
        _, billing_origin = resolve_with_origin(user=user)
    except Exception:
        billing_origin = "platform"

    billing = get_billing_service()
    pending_ids: List[str] = []

    for generation_id in generation_ids:
        if not generation_id:
            continue
        if _is_generation_settled(user, generation_id):
            result["skipped"] += 1
            continue

        gen_data = fetch_generation_data(api_key, generation_id)
        if gen_data is None:
            # Not finalized yet — retry the whole task later; settled ids
            # are skipped on the next run.
            pending_ids.append(generation_id)
            continue

        prompt_tokens = gen_data.get("tokens_prompt") or 0
        completion_tokens = gen_data.get("tokens_completion") or 0
        cost_usd = Decimal(str(gen_data.get("total_cost") or 0))

        operation = BillableOperation(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            model_id=gen_data.get("model") or model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            request_id=generation_id,
            session_id=session_id or "",
            extra_data={"settlement": "aborted_stream"},
        )
        billing.record_usage(user, operation, billing_origin=billing_origin)
        result["settled"] += 1
        logger.info(
            "billing.abort_settlement_recorded",
            extra={
                "user_id": str(user_id),
                "generation_id": generation_id,
                "cost_usd": str(cost_usd),
                "billing_origin": billing_origin,
                "session_id": session_id,
            },
        )

    if pending_ids:
        result["pending"] = len(pending_ids)
        if self.request.retries >= self.max_retries:
            logger.error(
                "billing.abort_settlement_gave_up",
                extra={
                    "user_id": str(user_id),
                    "pending_generation_ids": pending_ids,
                    "retries": self.request.retries,
                },
            )
            return result
        raise self.retry(
            countdown=min(60 * (2 ** self.request.retries), 900),
        )

    return result


def enqueue_abort_settlement(
    user_id: str,
    generation_ids: List[str],
    model_id: str = "",
    chat_id: str = "",
) -> bool:
    """Queue :func:`settle_aborted_generations` after a client disconnect.

    Also sets a cache marker so the client's post-abort PATCH
    (``conversations.views.MessageViewSet.perform_update``) knows the
    server settlement owns billing for this abort and skips its own
    ``record_usage`` (double-bill guard).

    Never raises — a failure to enqueue is logged (billing then falls
    back to the clamped client PATCH path).
    """
    ids = [g for g in (generation_ids or []) if g]
    if not user_id or not ids:
        return False
    try:
        settle_aborted_generations.apply_async(
            args=[str(user_id), ids],
            kwargs={"model_id": model_id or "", "session_id": chat_id or ""},
            countdown=ABORT_SETTLEMENT_DELAY_SECONDS,
        )
        if chat_id:
            try:
                cache.set(
                    ABORT_SETTLEMENT_CACHE_KEY.format(chat_id=chat_id),
                    {"user_id": str(user_id), "generation_ids": ids},
                    timeout=ABORT_SETTLEMENT_CACHE_TTL,
                )
            except Exception:
                logger.warning(
                    "billing.abort_settlement_marker_failed",
                    extra={"chat_id": chat_id},
                    exc_info=True,
                )
        logger.info(
            "billing.abort_settlement_enqueued",
            extra={
                "user_id": str(user_id),
                "generation_ids": ids,
                "chat_id": chat_id,
                "delay_seconds": ABORT_SETTLEMENT_DELAY_SECONDS,
            },
        )
        return True
    except Exception:
        logger.error(
            "billing.abort_settlement_enqueue_failed",
            extra={"user_id": str(user_id), "generation_ids": ids},
            exc_info=True,
        )
        return False
