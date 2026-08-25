"""The MCP tools a user has, reached through the platform's own registry.

`llm.agent_core.mcp_bridge` turns whatever an `MCPToolPort` reports
into `ToolDefinition`s the loop can offer, and never reaches an MCP
server itself. This is that port: it lists a user's tools through
`mcp.registry`, and runs a call through `mcp.tool_discovery_adapter`,
which is where an MCP invocation's own quota deduction and server
routing live.

How a tool is named depends on the endpoint that asked for it, so the
name is supplied as a strategy rather than fixed here. The V2 stream
names a tool the way every other V2 surface names it -- the server's
sanitized name and the tool's, under an `mcp_` prefix. The V1 stream
offers the bare name the server publishes, which is what its clients,
its approval records and its tool-call frames are written in terms of.
Whichever is chosen, the id the model is offered, the id a catalog
lookup answers to, and the id a result is attributed to are the same
string.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence

from asgiref.sync import sync_to_async

from ..agent_core.events import JsonDict
from ..agent_core.mcp_bridge import MCPToolSpec

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

TOOL_NAME_PREFIX = "mcp_"
FALLBACK_SERVER_NAME = "mcp"

ToolIdNaming = Callable[[str, str], str]
"""Names one MCP tool from its server's name and its own."""


def server_prefixed_tool_id(server_name: str, tool_name: str) -> str:
    """The tool's name behind its server's, both sanitized, under `mcp_`."""

    from mcp.utils import sanitize_tool_name

    prefix = sanitize_tool_name(server_name).lower()
    return f"{TOOL_NAME_PREFIX}{prefix}_{sanitize_tool_name(tool_name)}"


def published_tool_id(_server_name: str, tool_name: str) -> str:
    """The bare name the MCP server publishes the tool under."""

    return tool_name


class _MCPToolCalls:
    """Runs an MCP tool call through the adapter that owns MCP execution.

    Where the tools were listed makes no difference to how one is run,
    so both ports below reach the adapter the same way.
    """

    def __init__(self, naming: ToolIdNaming = server_prefixed_tool_id) -> None:
        self._naming = naming

    async def call_tool(
        self, user_id: str, tool_id: str, arguments: JsonDict
    ) -> JsonDict:
        from mcp.tool_discovery_adapter import get_mcp_adapter

        result = await get_mcp_adapter().execute_mcp_tool(
            user_id=user_id, tool_id=_catalog_tool_id(tool_id), arguments=dict(arguments)
        )
        return result if isinstance(result, dict) else {"result": result}

    async def _specs_of(self, tools: Any) -> List[MCPToolSpec]:
        specs: List[MCPToolSpec] = []
        for tool in tools:
            spec = await _as_spec(tool, self._naming)
            if spec is not None:
                specs.append(spec)
        return specs


class RegistryMCPTools(_MCPToolCalls):
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
        return await self._specs_of(tools)


class ListedMCPTools(_MCPToolCalls):
    """Runs the MCP tools an endpoint has already listed for itself.

    An endpoint that names the user's tools in its system prompt has
    listed them before the turn starts. Handing that list here is what
    keeps the tools the model is told about and the tools it is
    offered the same set.
    """

    def __init__(
        self, tools: Sequence[Any], *, naming: ToolIdNaming = server_prefixed_tool_id
    ) -> None:
        super().__init__(naming)
        self._tools = list(tools)

    async def list_tools(self, _user_id: str) -> List[MCPToolSpec]:
        return await self._specs_of(self._tools)


async def _resolve_user(user_id: str) -> Optional[Any]:
    from authentication.models import User

    try:
        return await sync_to_async(User.objects.filter(id=user_id).first)()
    except Exception:
        logger.error("agent_service.mcp_user_lookup_failed", exc_info=True)
        return None


async def _as_spec(tool: Any, naming: ToolIdNaming) -> Optional[MCPToolSpec]:
    try:
        return await sync_to_async(_spec_of)(tool, naming)
    except Exception:
        logger.error("agent_service.mcp_tool_unreadable", exc_info=True)
        return None


def _spec_of(tool: Any, naming: ToolIdNaming) -> MCPToolSpec:
    server = getattr(tool, "server", None)
    server_name = getattr(server, "name", None) or FALLBACK_SERVER_NAME
    return MCPToolSpec(
        tool_id=naming(server_name, tool.name),
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
