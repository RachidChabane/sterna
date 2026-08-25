"""Translation of the endpoint's chat messages into the provider port's shape.

The endpoint receives OpenAI-shaped message mappings and the agent
core speaks `ProviderMessage`. Content normalization -- flattening a
text-only content-part list, keeping a multimodal one intact so a
vision model still sees its images -- is shared with the LangChain
path so both stacks send a model the same thing.

Tool-role messages in the request are dropped: the loop regenerates
one per call it runs, and a stale pair from an earlier turn would
answer a call the model is no longer making.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..agent.message_conversion import (
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_USER,
    normalize_content,
)
from ..agent_core.provider import ProviderMessage

ROLE_FIELD = "role"
CONTENT_FIELD = "content"

CONVERSATION_ROLES = frozenset({ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM})


def to_provider_messages(
    messages: Sequence[Dict[str, Any]],
    *,
    system_prompt: Optional[str] = None,
) -> List[ProviderMessage]:
    """The conversation to send, with `system_prompt` leading it when given."""

    converted = [
        ProviderMessage(
            role=message[ROLE_FIELD],
            content=normalize_content(message.get(CONTENT_FIELD, "")),
        )
        for message in messages
        if message and message.get(ROLE_FIELD) in CONVERSATION_ROLES
    ]
    if system_prompt:
        converted.insert(0, ProviderMessage(role=ROLE_SYSTEM, content=system_prompt))
    return converted
