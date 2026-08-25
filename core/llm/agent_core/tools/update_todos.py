"""Update Todos tool: reports a task's todo list for display.

No entry exists for this tool in `llm.tool_catalog.core_tools`, so its
schema is transcribed here from `HTTPToolExecutor._handle_update_todos`
in `llm.http_tool_executor`, the handler this tool's execution
delegates to via the injected legacy invoker. It never reaches the
sandbox: the handler only validates and returns the list for the
frontend to render.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "update_todos"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Update Todos"),
    description=(
        "Report the current todo list for a multi-step task, so the user can "
        "see progress. Each item has an id, text, and status."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "The task's current todo items, in order.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["text", "status"],
                },
            },
        },
        "required": ["todos"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
