"""The `reasoning` request field, shared by the V1 and V2 turn builders.

OpenRouter is the only endpoint either turn ever sends it to: a direct
provider endpoint rejects a parameter outside its own API, and BYOK
already resolves such requests straight to the provider.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

REASONING_FIELD = "reasoning"


def reasoning_extra(
    *,
    is_openrouter: bool,
    enable_reasoning: bool,
    model: str,
    reasoning_effort: Optional[str],
    reasoning_max_tokens: Optional[int],
) -> Optional[Dict[str, Any]]:
    """The `reasoning` object this turn's request carries, or `None`."""

    if not (is_openrouter and enable_reasoning):
        return None

    from ..reasoning_options import build_reasoning_option

    return build_reasoning_option(
        model=model,
        reasoning_effort=reasoning_effort,
        reasoning_max_tokens=reasoning_max_tokens,
    )
