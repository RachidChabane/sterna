"""The `reasoning` option a request carrying extended reasoning is sent with.

OpenRouter takes one object, and which member of it a model honours
depends on the model: an effort-based model (the OpenAI o-series,
Grok) reads `effort`, a token-limited one (Anthropic, Gemini, Qwen)
reads `max_tokens`. What the user chose in the UI decides when it says
anything; the model family decides otherwise.

The option is always built with `exclude` false: a reasoning request
whose trace is excluded returns nothing to show for it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

EFFORT_FIELD = "effort"
MAX_TOKENS_FIELD = "max_tokens"
ENABLED_FIELD = "enabled"
EXCLUDE_FIELD = "exclude"

TOKEN_LIMITED_MODEL_MARKERS = ("anthropic", "claude", "gemini", "qwen")
"""Model ids whose family reads a token budget rather than an effort level."""

DEFAULT_REASONING_MAX_TOKENS = 4000
"""The budget a token-limited model reasons within when none was chosen."""


def build_reasoning_option(
    *,
    model: str,
    reasoning_effort: Optional[str] = None,
    reasoning_max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """The `reasoning` object for one request on `model`."""

    option: Dict[str, Any] = {}
    if reasoning_max_tokens:
        option[MAX_TOKENS_FIELD] = reasoning_max_tokens
    elif reasoning_effort:
        option[EFFORT_FIELD] = reasoning_effort
    elif _is_token_limited(model):
        option[MAX_TOKENS_FIELD] = DEFAULT_REASONING_MAX_TOKENS
    else:
        option[ENABLED_FIELD] = True
    option[EXCLUDE_FIELD] = False
    return option


def _is_token_limited(model: str) -> bool:
    lowered = model.lower()
    return any(marker in lowered for marker in TOKEN_LIMITED_MODEL_MARKERS)
