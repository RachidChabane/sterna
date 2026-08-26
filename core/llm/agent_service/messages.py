"""Translation of the endpoint's chat messages into the provider port's shape.

The endpoint receives OpenAI-shaped message mappings and the agent
core speaks `ProviderMessage`. Content normalization -- flattening a
text-only content-part list, keeping a multimodal one intact so a
vision model still sees its images -- is shared with the LangChain
path so both stacks send a model the same thing.

The two endpoints disagree about what a tool exchange in the request
means, so each gets its own conversion. A V2 request's tool-role
messages are dropped: the loop regenerates one per call it runs, and a
stale pair from an earlier turn would answer a call the model is no
longer making. A V1 request's are kept: a V1 turn ends when a call
needs sign-off, and the conversation the client posts back after the
user has answered is the only place the approved call and its result
exist.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from ..agent.message_conversion import (
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_USER,
    normalize_content,
)
from ..agent_core.events import ToolCall, ToolCallFunction
from ..agent_core.provider import ProviderMessage

ROLE_FIELD = "role"
CONTENT_FIELD = "content"
TOOL_CALLS_FIELD = "tool_calls"
TOOL_CALL_ID_FIELD = "tool_call_id"
NAME_FIELD = "name"
ID_FIELD = "id"
TYPE_FIELD = "type"
FUNCTION_FIELD = "function"
ARGUMENTS_FIELD = "arguments"

ROLE_TOOL = "tool"
FUNCTION_TYPE = "function"
EMPTY_ARGUMENTS = "{}"

CONVERSATION_ROLES = frozenset({ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM})
V1_ROLES = frozenset({ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_TOOL})


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


def to_v1_provider_messages(
    messages: Sequence[Dict[str, Any]],
    *,
    system_prompt: Optional[str] = None,
) -> List[ProviderMessage]:
    """The conversation a V1 turn sends, tool exchanges intact.

    An assistant message keeps the calls it made and a tool-role
    message keeps the call it answers, so a conversation resumed after
    an approval still shows the model what its call returned.
    """

    converted = [
        _v1_message(message)
        for message in messages
        if message and message.get(ROLE_FIELD) in V1_ROLES
    ]
    if system_prompt:
        converted.insert(0, ProviderMessage(role=ROLE_SYSTEM, content=system_prompt))
    return converted


def _v1_message(message: Dict[str, Any]) -> ProviderMessage:
    role = message[ROLE_FIELD]
    content = message.get(CONTENT_FIELD)
    return ProviderMessage(
        role=role,
        content=_v1_content(role, content),
        tool_calls=_tool_calls(message.get(TOOL_CALLS_FIELD)),
        tool_call_id=message.get(TOOL_CALL_ID_FIELD),
        name=message.get(NAME_FIELD),
    )


def _v1_content(role: str, content: Any) -> Optional[str]:
    """One message's content, as the provider port carries it.

    A tool-role message answers with a string whatever it holds, since
    that is what the model reads a result as.
    """

    if role == ROLE_TOOL:
        return content if isinstance(content, str) else json.dumps(content)
    return normalize_content(content if content is not None else "")


def _tool_calls(raw: Any) -> Optional[List[ToolCall]]:
    if not isinstance(raw, list) or not raw:
        return None
    calls = [_tool_call(entry) for entry in raw if isinstance(entry, dict)]
    return calls or None


def _tool_call(entry: Dict[str, Any]) -> ToolCall:
    function = entry.get(FUNCTION_FIELD) or {}
    return ToolCall(
        id=str(entry.get(ID_FIELD) or ""),
        type=str(entry.get(TYPE_FIELD) or FUNCTION_TYPE),
        function=ToolCallFunction(
            name=str(function.get(NAME_FIELD) or ""),
            arguments=str(function.get(ARGUMENTS_FIELD) or EMPTY_ARGUMENTS),
        ),
    )
