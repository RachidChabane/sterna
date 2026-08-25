"""The streaming HTTP response a V1 chat request gets.

The direct-completion endpoint validates a request and then needs one
thing: a response that streams the turn. This module is that step. It
resolves the key and the endpoint this user's model is reached on,
lists the MCP tools the turn is both told about and offered, builds
the system prompt the direct-completion prompt builder assembles, and
turns the request's sampling parameters into the provider fields they
are sent as.

The ceiling on one generation is resolved here rather than inside the
turn: a conversation that no longer leaves room to answer is refused
before any upstream call is made, which is how a V1 client learns its
conversation has outgrown its model.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from django.http import StreamingHttpResponse

from ..agent.feature_flags import AgentFeatureFlags
from ..agent.prompt_assembly import (
    build_direct_completion_system_prompt,
    split_custom_system_prompt,
)
from ..agent_core import sse
from ..agent_core.events import EventType
from ..agent_core.mcp_bridge import MCPToolSource
from ..exceptions import ContextLimitExceededException
from ..provider_registry import is_openrouter_url, native_model_name
from .dependencies import TurnRequest
from .mcp_port import ListedMCPTools, published_tool_id
from .v1_stream import V1TurnRunner

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

STREAM_CONTENT_TYPE = "text/event-stream; charset=utf-8"
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1000
DEFAULT_TOP_P = 1.0
DEFAULT_CONVERSATION_ID = "default"

TOP_P_FIELD = "top_p"
PLUGINS_FIELD = "plugins"
REASONING_FIELD = "reasoning"
STREAM_OPTIONS_FIELD = "stream_options"
INCLUDE_USAGE_OPTION = {"include_usage": True}

SAMPLING_PARAMS = (
    "top_k",
    "frequency_penalty",
    "presence_penalty",
    "repetition_penalty",
    "min_p",
    "top_a",
)
"""The optional sampling parameters a V1 request may carry upstream."""

BEARER_PREFIX = "Bearer "
AUTHORIZATION_META_KEY = "HTTP_AUTHORIZATION"

ERROR_FIELD = "error"
DETAIL_FIELD = "detail"
CONTEXT_LIMIT_ERROR = "Conversation too long for selected model"
"""What a client is told when the conversation leaves no room to answer."""


def v1_streaming_response(*, request, data: Dict[str, Any]) -> StreamingHttpResponse:
    """Stream this direct-completion request's turn through the agent core."""

    from llm.services.api_key_resolver import resolve_endpoint

    model = data["model"]
    user_id = str(request.user.id)
    flags = _flags_for(data, request.user)
    mcp_tools = _mcp_tools(request.user) if flags.mcp_tools else []

    api_key, base_url, _origin, provider_slug = resolve_endpoint(
        user=request.user, request=request, model_id=model
    )
    if not api_key:
        raise ValueError("OpenRouter API key is required")
    is_openrouter = is_openrouter_url(base_url)

    custom_prompt, conversation = split_custom_system_prompt(data["messages"])
    try:
        max_tokens = _generation_ceiling(model, conversation, data)
    except ContextLimitExceededException as exceeded:
        logger.error("agent_service.v1_context_limit_exceeded", exc_info=True)
        return _refusal(CONTEXT_LIMIT_ERROR, str(exceeded))

    turn = TurnRequest(
        user_id=user_id,
        conversation_id=str(data.get("conversation_id") or DEFAULT_CONVERSATION_ID),
        chat_id=data.get("chat_id"),
        model=model,
        request_model=(native_model_name(model) or model) if provider_slug else model,
        api_key=api_key,
        base_url=base_url,
        temperature=data.get("temperature", DEFAULT_TEMPERATURE),
        max_tokens=max_tokens,
        flags=flags,
        extra=_provider_extra(data, model=model, is_openrouter=is_openrouter),
    )
    runner = V1TurnRunner(
        turn=turn,
        messages=conversation,
        system_prompt=build_direct_completion_system_prompt(
            custom_prompt=custom_prompt,
            enable_reasoning=flags.reasoning,
            enable_file_tools=flags.file_tools,
            mcp_tools=mcp_tools,
        ),
        auth_token=_auth_token(request),
        mcp_tools=MCPToolSource(
            ListedMCPTools(mcp_tools, naming=published_tool_id)
        ),
    )

    return StreamingHttpResponse(
        runner.frames(),
        content_type=STREAM_CONTENT_TYPE,
        headers=dict(STREAM_HEADERS),
    )


def _refusal(message: str, detail: str) -> StreamingHttpResponse:
    """A stream carrying one `error` frame and nothing else."""

    def _frame():
        yield sse.render_frame(str(EventType.ERROR), {ERROR_FIELD: message, DETAIL_FIELD: detail})

    return StreamingHttpResponse(
        _frame(), content_type=STREAM_CONTENT_TYPE, headers=dict(STREAM_HEADERS)
    )


def _flags_for(data: Dict[str, Any], user) -> AgentFeatureFlags:
    """The switches this request turned on, as the tool set reads them."""

    from ..file_tools_integration import should_enable_file_tools

    return AgentFeatureFlags(
        file_tools=should_enable_file_tools(data, user),
        brave_search=bool(data.get("enable_brave_search", False)),
        google_maps=bool(data.get("enable_google_maps", False)),
        reasoning=bool(data.get("enable_reasoning", False)),
        mcp_tools=bool(data.get("enable_mcp_tools", False)),
    )


def _mcp_tools(user) -> List[Any]:
    """The MCP tools this user has, listed once for the prompt and the turn."""

    from mcp.registry import get_registry

    try:
        return list(get_registry().get_available_tools_sync(user) or [])
    except Exception:
        logger.error("agent_service.v1_mcp_discovery_failed", exc_info=True)
        return []


def _generation_ceiling(
    model: str, messages: Sequence[Dict[str, Any]], data: Dict[str, Any]
) -> int:
    """How many tokens this turn's answers may take, given what it already holds.

    Raises `ContextLimitExceededException` when the conversation
    leaves no room to answer in.
    """

    from ..context_utils import calculate_dynamic_max_tokens

    return calculate_dynamic_max_tokens(
        model_id=model,
        messages=list(messages),
        configured_max_tokens=data.get("max_tokens", DEFAULT_MAX_TOKENS),
    )


def _provider_extra(
    data: Dict[str, Any], *, model: str, is_openrouter: bool
) -> Dict[str, Any]:
    """The request fields the provider takes beyond model, messages and tools.

    A direct provider endpoint is sent neither OpenRouter's own
    extensions nor a reasoning option it has no vocabulary for, and is
    asked explicitly for the usage it reports only when asked.
    """

    from ..client import OpenRouterClient

    extra: Dict[str, Any] = {TOP_P_FIELD: data.get(TOP_P_FIELD, DEFAULT_TOP_P)}
    for name in SAMPLING_PARAMS:
        if data.get(name) is not None:
            extra[name] = data[name]
    if data.get(PLUGINS_FIELD) is not None:
        extra[PLUGINS_FIELD] = data[PLUGINS_FIELD]

    if not is_openrouter:
        extra = {
            name: value
            for name, value in extra.items()
            if name not in OpenRouterClient.OPENROUTER_ONLY_PARAMS
        }
        extra[STREAM_OPTIONS_FIELD] = dict(INCLUDE_USAGE_OPTION)
        return extra

    if data.get("enable_reasoning", False):
        from ..reasoning_options import build_reasoning_option

        extra[REASONING_FIELD] = build_reasoning_option(
            model=model,
            reasoning_effort=data.get("reasoning_effort"),
            reasoning_max_tokens=data.get("reasoning_max_tokens"),
        )
    return extra


def _auth_token(request) -> Optional[str]:
    """The bearer token this request carries, for the tools that call back in."""

    header = request.META.get(AUTHORIZATION_META_KEY, "")
    if header.startswith(BEARER_PREFIX):
        return header[len(BEARER_PREFIX):]
    return None
