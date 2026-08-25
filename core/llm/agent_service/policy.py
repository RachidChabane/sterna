"""Which tool calls the V2 chat endpoint stops on before running them.

The V2 stream runs every call the model makes, whatever the tool is:
sandboxed file tools, catalog tools, and the tools an MCP server
surfaces alike. A pause for sign-off belongs to the V1 endpoint, which
mints an `MCPToolApproval` and ends its stream awaiting an answer.

A `ToolDefinition` states its own approval requirement, and the ones
this endpoint offers do not all say `AUTO`. `run_every_call` is the
`ApprovalPolicy` that answers for them, so the endpoint's behaviour is
declared in one place rather than depending on which tools a request
happened to bind.
"""

from __future__ import annotations

from ..agent_core.events import ToolCall
from ..agent_core.registry import ToolApproval, ToolDefinition


def run_every_call(_definition: ToolDefinition, _call: ToolCall) -> ToolApproval:
    """Answer every call with `AUTO`, whatever its tool requires."""

    return ToolApproval.AUTO
