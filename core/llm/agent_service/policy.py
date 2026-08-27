"""Which tool calls the V2 chat endpoint stops on before running them.

The V2 stream runs every catalog and sandboxed file tool call the
model makes without a pause: that class of tool is offered by this
platform itself, so its own approval default is treated as advisory
here. A tool an MCP server surfaces is different -- it is a
third-party integration the user connected, never audited by this
platform -- so V2 holds it to the same sign-off gate V1 always has,
regardless of what an individual MCP tool's own approval default says.

`ToolDisplay.server_name` is what distinguishes the two: populated
only for a tool surfaced through an MCP server (see
`mcp_bridge.MCPToolSource`), unset for every built-in tool under
`agent_core.tools`. `run_every_call_except_mcp` is the `ApprovalPolicy`
that reads it, so the endpoint's behaviour is declared in one place
rather than depending on which tools a request happened to bind.
"""

from __future__ import annotations

from ..agent_core.events import ToolCall
from ..agent_core.registry import ToolApproval, ToolDefinition


def run_every_call_except_mcp(definition: ToolDefinition, _call: ToolCall) -> ToolApproval:
    """`REQUIRED` for a tool an MCP server surfaces; `AUTO` for every other tool."""

    if definition.display.server_name:
        return ToolApproval.REQUIRED
    return ToolApproval.AUTO
