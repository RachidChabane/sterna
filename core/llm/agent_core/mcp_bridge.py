"""Surfaces a user's MCP tools through the same `ToolDefinition` shape.

MCP tools are per-user and discovered at runtime, unlike the static
entries under `llm.agent_core.tools`, so they cannot be a file the
`registry.discover_tools` walk picks up. Instead this module defines
the port a caller injects — `MCPToolPort` — and `MCPToolSource`, which
turns whatever that port reports into `ToolDefinition`s on demand. The
port's real implementation (reaching `core.mcp`'s registry, which is
Django-backed) lives outside `agent_core` and is constructed by the
caller; this module never imports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from .events import JsonDict
from .registry import ToolDefinition, ToolDisplay, ToolApproval, ToolExecutionContext


@dataclass(frozen=True, slots=True)
class MCPToolSpec:
    """One tool as reported by an MCP server, ahead of being wrapped as a `ToolDefinition`."""

    tool_id: str
    server_id: str
    server_name: str
    name: str
    description: str
    input_schema: JsonDict
    server_icon_url: Optional[str] = None
    server_icon_invert: bool = False


class MCPToolPort(Protocol):
    """The port `MCPToolSource` reaches to discover and run a user's MCP tools."""

    async def list_tools(self, user_id: str) -> List[MCPToolSpec]:
        ...

    async def call_tool(
        self, user_id: str, tool_id: str, arguments: JsonDict
    ) -> JsonDict:
        ...


class MCPToolSource:
    """Converts one user's MCP tools into `ToolDefinition`s via an injected `MCPToolPort`.

    Every tool produced this way requires approval before it runs —
    the platform never auto-executes a call against a third-party MCP
    server, unlike the built-in catalog tools under `tools/`.
    """

    def __init__(self, port: MCPToolPort):
        self._port = port

    async def discover(self, user_id: str) -> List[ToolDefinition]:
        specs = await self._port.list_tools(user_id)
        return [self._to_definition(spec) for spec in specs]

    def _to_definition(self, spec: MCPToolSpec) -> ToolDefinition:
        async def handler(
            arguments: JsonDict, context: ToolExecutionContext
        ) -> JsonDict:
            return await self._port.call_tool(context.user_id, spec.tool_id, arguments)

        return ToolDefinition(
            id=spec.tool_id,
            display=ToolDisplay(
                name=spec.name,
                icon_url=spec.server_icon_url,
                icon_invert=spec.server_icon_invert,
                server_name=spec.server_name,
            ),
            description=spec.description,
            input_schema=spec.input_schema,
            handler=handler,
            approval=ToolApproval.REQUIRED,
        )
