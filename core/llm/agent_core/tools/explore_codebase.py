"""Explore Codebase tool: runs a fast exploration pass over the workspace.

No entry exists for this tool in `llm.tool_catalog.core_tools`, so its
schema is transcribed here from
`HTTPToolExecutor._handle_explore_codebase` in `llm.http_tool_executor`,
the handler this tool's execution delegates to via the injected legacy
invoker.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "explore_codebase"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Explore Codebase"),
    description=(
        "Explore the workspace with a fast, low-cost model to find the files "
        "relevant to a task and suggest an approach, without modifying anything."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task to explore the codebase for.",
            },
        },
        "required": ["task"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
