"""Shared model resolver for AI-powered generation features.

Centralizes the model used for lightweight generation tasks (room generation,
MCP config extraction, agent auto-configuration) so it can be updated in one
place and benefits from a TTL cache to avoid repeated DB hits.
"""

import logging
import time

logger = logging.getLogger(__name__)

_FALLBACK_MODEL = "anthropic/claude-haiku-4.5"
_TTL_SECONDS = 600  # 10 minutes

_cached_model: str | None = None
_cache_timestamp: float = 0.0


def get_generation_assistant_model() -> str:
    """Return the model ID for lightweight generation tasks.

    Queries ModelCatalog for the latest anthropic haiku model with a 10-minute
    TTL cache. Falls back to a hardcoded default if no match is found.
    """
    global _cached_model, _cache_timestamp

    now = time.monotonic()
    if _cached_model and (now - _cache_timestamp) < _TTL_SECONDS:
        return _cached_model

    try:
        from django.apps import apps

        ModelCatalog = apps.get_model("llm", "ModelCatalog")
        match = (
            ModelCatalog.objects.filter(model_id__startswith="anthropic/")
            .filter(model_id__contains="haiku")
            .order_by("-model_id")
            .values_list("model_id", flat=True)
            .first()
        )
        if match:
            _cached_model = match
            _cache_timestamp = now
            return match
    except Exception as exc:
        logger.warning("ModelCatalog lookup failed, using fallback: %s", exc)

    logger.warning(
        "No anthropic haiku model found in ModelCatalog, using fallback: %s",
        _FALLBACK_MODEL,
    )
    _cached_model = _FALLBACK_MODEL
    _cache_timestamp = now
    return _FALLBACK_MODEL


def log_generation_usage(
    response_data: dict,
    model_id: str,
    user=None,
    request_source: str = "generation",
) -> None:
    """Extract usage from an OpenRouter response and log it for billing.

    Call this after every successful OpenRouter chat/completions call in
    generation features (room generator, config helper, agent generator).

    Uses the unified BillingService so costs appear in quota tracking
    and the ``user_usage`` management command.

    Args:
        response_data: The parsed JSON response from OpenRouter.
        model_id: The model ID that was used.
        user: Django User object (None skips logging).
        request_source: One of 'voice_room_generation', 'mcp_config_help',
                        'agent_generation'.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return

    usage = response_data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    if not prompt_tokens and not completion_tokens:
        return

    try:
        from usage_quota.billing.service import get_billing_service
        from usage_quota.billing.operations import BillableOperation
        from usage_quota.models import ServiceType, FeatureType

        _FEATURE_MAP = {
            "voice_room_generation": FeatureType.VOICE_ROOM,
            "mcp_config_help": FeatureType.OTHER,
            "agent_generation": FeatureType.CODE_SESSION,
        }

        from llm.services.api_key_resolver import resolve_with_origin
        try:
            _, origin = resolve_with_origin(user=user)
        except Exception:
            origin = 'platform'

        billing = get_billing_service()
        billing.record_usage(
            user=user,
            operation=BillableOperation(
                service=ServiceType.OPENROUTER,
                feature=_FEATURE_MAP.get(request_source, FeatureType.OTHER),
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
            billing_origin=origin,
        )
    except Exception as exc:
        logger.warning("Failed to record generation usage: %s", exc)
