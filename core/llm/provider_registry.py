"""Registry of first-party providers eligible for provider-scoped BYOK.

Users may store a per-provider API key (User.provider_api_keys). When a
chat request targets a model whose OpenRouter slug prefix matches one of
these providers AND the user has a key for it, the request is routed
DIRECTLY to the provider's OpenAI-compatible endpoint instead of through
OpenRouter.

Only first-party providers are listed: models like ``meta-llama/...`` or
``qwen/...`` are hosted by third parties on OpenRouter and cannot be
called directly with a single vendor key, so they are NOT BYOK-eligible
and resolve exactly as before (OpenRouter key or platform fallback).

V1 scope: chat completions only. Image/video/voice/embeddings always
stay on OpenRouter.
"""

from typing import Dict, Optional

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

BYOK_PROVIDERS: Dict[str, Dict[str, str]] = {
    'openai': {
        'label': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
    },
    'anthropic': {
        # OpenAI-compat layer; temperature capped at 1.0 and a single
        # hoisted system message — acceptable for chat completions.
        'label': 'Anthropic',
        'base_url': 'https://api.anthropic.com/v1',
    },
    'google': {
        'label': 'Google AI Studio',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
    },
    'mistralai': {
        'label': 'Mistral',
        'base_url': 'https://api.mistral.ai/v1',
    },
    'deepseek': {
        'label': 'DeepSeek',
        'base_url': 'https://api.deepseek.com/v1',
    },
    'x-ai': {
        'label': 'xAI',
        'base_url': 'https://api.x.ai/v1',
    },
}


def provider_for_model(model_id: Optional[str]) -> Optional[str]:
    """Return the BYOK provider slug for an OpenRouter model id.

    The slug is the part before the first ``/`` — but only when it names
    a first-party provider in ``BYOK_PROVIDERS``. Models without a
    ``/`` (or with a non-first-party prefix like ``meta-llama``) return
    ``None`` and are not BYOK-eligible.
    """
    if not model_id or '/' not in model_id:
        return None
    prefix = model_id.split('/', 1)[0]
    return prefix if prefix in BYOK_PROVIDERS else None


def native_model_name(model_id: Optional[str]) -> Optional[str]:
    """Strip the ``<provider>/`` prefix and any ``:suffix`` variant.

    Example: ``anthropic/claude-sonnet-4.5:thinking`` -> ``claude-sonnet-4.5``.

    Suffixes like ``:online`` / ``:thinking`` are OpenRouter routing
    variants and must never be sent to a direct provider endpoint.
    """
    if not model_id:
        return model_id
    name = model_id.split('/', 1)[1] if '/' in model_id else model_id
    return name.split(':', 1)[0]


def provider_base_url(provider: str) -> str:
    """Base URL for a registered BYOK provider (raises KeyError if unknown)."""
    return BYOK_PROVIDERS[provider]['base_url']


def is_openrouter_url(base_url: Optional[str]) -> bool:
    """True when ``base_url`` points at OpenRouter (or is unset — the default)."""
    if not base_url:
        return True
    return 'openrouter.ai' in base_url
