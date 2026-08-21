"""Chat quota gate, run before any upstream call is made.

Guard. Estimates what this turn will cost from the message payload, asks
the billing service whether the user may spend it, and hands back an SSE
error event when the answer is no. Returning the event (instead of
yielding it) keeps control flow in the streaming generator that called
us -- see the module docstring in `llm/agent/streaming/__init__.py`.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async

from ...catalog_service import CatalogService
from ..sse_events import quota_error_event

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# Rough estimate: ~1 token per 4 characters of message content.
CHARS_PER_TOKEN_ESTIMATE = 4
MINIMUM_ESTIMATED_TOKENS = 1000
# Used when the catalog cannot price the model.
DEFAULT_ESTIMATED_COST_USD = Decimal('0.01')
CHAT_FEATURE_NAME = 'chat'


async def _estimate_cost(model_id: str, messages: List[Dict[str, Any]]) -> Decimal:
    total_chars = sum(len(str(m.get('content', ''))) for m in messages)
    estimated_tokens = max(MINIMUM_ESTIMATED_TOKENS, total_chars // CHARS_PER_TOKEN_ESTIMATE)
    try:
        # Pricing lookup hits the DB (ModelCatalog) — must be wrapped in
        # async context or SynchronousOnlyOperation silently degrades the
        # estimate to the default.
        cost_details = await sync_to_async(CatalogService().estimate_cost_detailed)(
            model_id=model_id,
            prompt_tokens=estimated_tokens,
            completion_tokens=estimated_tokens // 2,
        )
        return cost_details.get('total_cost', DEFAULT_ESTIMATED_COST_USD)
    except Exception:
        return DEFAULT_ESTIMATED_COST_USD


async def precheck_chat_quota(
    *,
    user_id: str,
    model_id: str,
    messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return an SSE error event when this turn must not start, else None.

    Any unexpected failure is logged and treated as "allow" — the quota
    gate must never take a chat down on its own.
    """
    from authentication.models import User
    from usage_quota.billing.service import get_billing_service
    from usage_quota.exceptions import (
        FeatureNotAvailableException,
        QuotaExceededException,
    )
    from usage_quota.models import ServiceType, FeatureType

    try:
        user = await sync_to_async(User.objects.get)(id=user_id)
        estimated_cost = await _estimate_cost(model_id, messages)

        try:
            await sync_to_async(get_billing_service().check_quota)(
                user=user,
                service=ServiceType.OPENROUTER,
                estimated_cost=estimated_cost,
                feature=FeatureType.CHAT,
                feature_name=CHAT_FEATURE_NAME,
            )
        except (QuotaExceededException, FeatureNotAvailableException) as exc:
            logger.warning(
                "langchain.tier_gate_denied",
                extra={"error": exc.code, "feature": CHAT_FEATURE_NAME},
            )
            return quota_error_event(
                exc,
                feature_not_available=isinstance(exc, FeatureNotAvailableException),
            )
    except (QuotaExceededException, FeatureNotAvailableException):
        raise
    except Exception:
        logger.error("langchain.quota_precheck_error", exc_info=True)

    return None
