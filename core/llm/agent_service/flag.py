"""Which streaming stack answers one V2 chat request.

Two stacks can serve `stream-complete-v2`: the agent core behind
`llm.agent_service`, and the LangChain streaming agent. The choice is
made per request, so a single request can be steered without a deploy
and the whole endpoint can be moved back with one setting.

Precedence, highest first:

1. the `X-Sterna-Agent-Core` request header, when it names a stack,
2. the `LLM_AGENT_CORE_V2_STREAMING` Django setting,
3. `DEFAULT_ENABLED`.

A turn that asks for reasoning traces or image output is answered by
the LangChain stack whatever the flag says: those two capabilities are
served by a separate path with a wire format of its own, and routing
them through the agent core would change what their clients read.
"""

from __future__ import annotations

from typing import Optional

from django.conf import settings

DEFAULT_ENABLED = False
"""Which stack answers a request that names none."""

SETTING_NAME = "LLM_AGENT_CORE_V2_STREAMING"
"""The Django setting that answers a request naming no stack."""

HEADER_NAME = "X-Sterna-Agent-Core"
"""The request header that names a stack for one request."""

HEADER_META_KEY = "HTTP_X_STERNA_AGENT_CORE"
"""The `request.META` key that header arrives under."""

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def header_choice(request) -> Optional[bool]:
    """The stack this request's header names, or `None` when it names none."""

    raw = request.META.get(HEADER_META_KEY)
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None


def configured_default() -> bool:
    """The stack a request that names none is answered by."""

    return bool(getattr(settings, SETTING_NAME, DEFAULT_ENABLED))


def serves_agent_core(
    request, *, enable_reasoning: bool, supports_image_output: bool
) -> bool:
    """Whether the agent core answers this request."""

    if enable_reasoning or supports_image_output:
        return False
    chosen = header_choice(request)
    return configured_default() if chosen is None else chosen
