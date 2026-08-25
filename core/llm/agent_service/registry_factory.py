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
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..agent.feature_flags import AgentFeatureFlags
from ..agent.tool_registry import AgentToolRegistry
from ..agent_core.mcp_bridge import MCPToolSource
from ..agent_core.registry import ToolDefinition, ToolRegistry, discover_tools

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
    mcp_tools: Optional[MCPToolSource] = None,
) -> RequestToolSet:
    """Everything this request's switches entitle it to call."""

    bound_callables, legacy_display_names = _bound_tools(flags)
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
