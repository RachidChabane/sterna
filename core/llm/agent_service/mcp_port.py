"""The MCP tools a user has, reached through the platform's own registry.

`llm.agent_core.mcp_bridge` turns whatever an `MCPToolPort` reports
into `ToolDefinition`s the loop can offer, and never reaches an MCP
server itself. This is that port: it lists a user's tools through
`mcp.registry`, and runs a call through `mcp.tool_discovery_adapter`,
which is where an MCP invocation's own quota deduction and server
routing live.

A tool is named the way every other surface names it -- the server's
sanitized name and the tool's, under an `mcp_` prefix -- so the id the
model is offered, the id a catalog lookup answers to, and the id a
result is attributed to are the same string.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from asgiref.sync import sync_to_async

from ..agent_core.events import JsonDict
from ..agent_core.mcp_bridge import MCPToolSpec

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

TOOL_NAME_PREFIX = "mcp_"
FALLBACK_SERVER_NAME = "mcp"


class RegistryMCPTools:
    """Lists and runs one user's MCP tools through the platform registry."""

    async def list_tools(self, user_id: str) -> List[MCPToolSpec]:
        from mcp.registry import get_registry

        user = await _resolve_user(user_id)
        if user is None:
            return []
        try:
            tools = await get_registry().get_available_tools(user)
        except Exception:
            logger.error("agent_service.mcp_discovery_failed", exc_info=True)
            return []

        specs: List[MCPToolSpec] = []
        for tool in tools:
            spec = await _as_spec(tool)
            if spec is not None:
                specs.append(spec)
        return specs

    async def call_tool(
        self, user_id: str, tool_id: str, arguments: JsonDict
    ) -> JsonDict:
        from mcp.tool_discovery_adapter import get_mcp_adapter

        result = await get_mcp_adapter().execute_mcp_tool(
            user_id=user_id, tool_id=_catalog_tool_id(tool_id), arguments=dict(arguments)
        )
        return result if isinstance(result, dict) else {"result": result}


async def _resolve_user(user_id: str) -> Optional[Any]:
    from authentication.models import User

    try:
        return await sync_to_async(User.objects.filter(id=user_id).first)()
    except Exception:
        logger.error("agent_service.mcp_user_lookup_failed", exc_info=True)
        return None


async def _as_spec(tool: Any) -> Optional[MCPToolSpec]:
    try:
        return await sync_to_async(_spec_of)(tool)
    except Exception:
        logger.error("agent_service.mcp_tool_unreadable", exc_info=True)
        return None


def _spec_of(tool: Any) -> MCPToolSpec:
    from mcp.utils import sanitize_tool_name

    server = getattr(tool, "server", None)
    server_name = getattr(server, "name", None) or FALLBACK_SERVER_NAME
    prefix = sanitize_tool_name(server_name).lower()
    return MCPToolSpec(
        tool_id=f"{TOOL_NAME_PREFIX}{prefix}_{sanitize_tool_name(tool.name)}",
        server_id=str(getattr(server, "id", FALLBACK_SERVER_NAME)),
        server_name=server_name,
        name=tool.name,
        description=tool.description or "",
        input_schema=tool.input_schema or {},
        server_icon_url=getattr(server, "icon_url", None) or None,
        server_icon_invert=bool(getattr(server, "icon_invert_in_dark_mode", False)),
    )


def _catalog_tool_id(tool_id: str) -> str:
    """The id the MCP adapter routes on, from the id the model was offered."""

    from ..agent.tool_naming import unsanitize_tool_name

    return unsanitize_tool_name(tool_id)
