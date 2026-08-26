"""The tools one request offers the model, and the callables behind them.

Which tools a chat turn may use is decided by the request's feature
switches, and `llm.agent.tool_registry.AgentToolRegistry` is where that
decision lives: it binds the always-on set, adds the groups the
request enabled, and carries the labels the frontend shows. Asking it
rather than restating its rules keeps one answer to "which tools does
this request have".

What comes back is a set of bound callables. The loop needs typed
definitions instead, so each bound name is matched against
`llm.agent_core.tools`; a name with no definition there is left out of
what the model is offered, while the callable stays reachable so a
definition added later needs no change here. A user's MCP tools are
appended from `mcp_bridge`, which sources them through the port in
`mcp_port`.

The tool-discovery meta-tools (`search_available_tools`,
`get_tool_details`) are bound the same way but on a separate gate: a
request whose `AgentFeatureFlags.has_tool_features` is true and whose
`user_id` and `conversation_id` are both non-empty gets both tools;
every other request gets neither.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..agent.feature_flags import AgentFeatureFlags
from ..agent.tool_registry import AgentToolRegistry
from ..agent_core.mcp_bridge import MCPToolSource
from ..agent_core.registry import ToolDefinition, ToolRegistry, discover_tools
from ..tool_discovery import (
    create_get_tool_details_tool,
    create_tool_search_tool,
    get_discovery_service,
)

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)


class RequestToolSet:
    """The tools one request offers, in each of the shapes it needs.

    `registry` is what the model is offered, `bound_callables` is what
    runs a call, and `display_names`/`server_icons` are what the
    frontend labels one with.
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        bound_callables: Dict[str, Any],
        display_names: Dict[str, str],
        server_icons: Dict[str, Dict[str, Any]],
    ) -> None:
        self.registry = registry
        self.bound_callables = bound_callables
        self.display_names = display_names
        self.server_icons = server_icons


async def build_tool_set(
    flags: AgentFeatureFlags,
    *,
    user_id: str,
    conversation_id: str,
    chat_id: Optional[str] = None,
    mcp_tools: Optional[MCPToolSource] = None,
) -> RequestToolSet:
    """Everything this request's switches entitle it to call."""

    bound_callables, legacy_display_names = _bound_tools(flags)
    bound_callables.update(
        _discovery_tools(
            flags,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
        )
    )
    definitions = _definitions_for(bound_callables)
    if mcp_tools is not None and flags.mcp_tools:
        definitions.extend(await _mcp_definitions(mcp_tools, user_id))

    display_names = {
        definition.id: definition.display.name for definition in definitions
    }
    display_names.update(
        {
            name: label
            for name, label in legacy_display_names.items()
            if name in display_names
        }
    )
    return RequestToolSet(
        registry=ToolRegistry(definitions),
        bound_callables=bound_callables,
        display_names=display_names,
        server_icons=_server_icons(definitions),
    )


def _server_icons(definitions: List[ToolDefinition]) -> Dict[str, Dict[str, Any]]:
    """The icon the frontend badges a tool with, for the tools that carry one."""

    return {
        definition.id: {
            "url": definition.display.icon_url,
            "invert": definition.display.icon_invert,
        }
        for definition in definitions
        if definition.display.icon_url
    }


def _bound_tools(flags: AgentFeatureFlags) -> Tuple[Dict[str, Any], Dict[str, str]]:
    legacy = AgentToolRegistry(flags)
    legacy.load_initial_tools()
    return (
        {tool.name: tool for tool in legacy.tools},
        dict(legacy.display_names),
    )


def _discovery_tools(
    flags: AgentFeatureFlags,
    *,
    user_id: str,
    conversation_id: str,
    chat_id: Optional[str],
) -> Dict[str, Any]:
    """The `search_available_tools` / `get_tool_details` callables, by name.

    Bound from `llm.tool_discovery` against a session context keyed on
    this conversation so repeated searches within one turn share the
    discovery service's cache. Gated on `flags.has_tool_features` plus a
    real user and conversation id (see module docstring). Best-effort
    beyond that gate: a request the discovery service cannot build a
    context for (an unexpected failure, not a normal flag state) still
    gets its turn, just without these two tools bound.
    """

    if not (user_id and conversation_id and flags.has_tool_features):
        return {}

    try:
        service = get_discovery_service()
        context = service.get_or_create_context(
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            enabled_features=flags.discovery_feature_names(),
        )
        search_tool = create_tool_search_tool(discovery_service=service, context=context)
        details_tool = create_get_tool_details_tool(discovery_service=service, context=context)
    except Exception:
        logger.error("agent_service.tool_discovery_unavailable", exc_info=True)
        return {}
    return {search_tool.name: search_tool, details_tool.name: details_tool}


def _definitions_for(bound_callables: Dict[str, Any]) -> List[ToolDefinition]:
    catalog = discover_tools()
    return [
        catalog[name] for name in bound_callables if name in catalog
    ]


async def _mcp_definitions(
    mcp_tools: MCPToolSource, user_id: str
) -> List[ToolDefinition]:
    try:
        return await mcp_tools.discover(user_id)
    except Exception:
        logger.error("agent_service.mcp_tools_unavailable", exc_info=True)
        return []
