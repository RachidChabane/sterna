"""Update Todos tool: reports a task's todo list for display.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from the `update_todos` entry of
`FILE_TOOLS` in `sandbox.orchestrator.file_tools` — the model-facing
tool contract legacy V1 sends the model via `get_file_tools()`
(`llm.file_tools_integration`, called from `llm.views.stream_complete`).
Execution delegates to that same tool id via the injected legacy
invoker; it never reaches the sandbox, since that handler only
validates and returns the list for the frontend to render.
`test_agent_core_file_tools_drift.py` guards this module against
drifting from that source.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "update_todos"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Update Todos"),
    description=(
        "Update the task list to track your progress. Call this at the "
        "START of your work to plan tasks, and call it again as you "
        "complete each task. The frontend will display this as an "
        "interactive checklist."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": (
                    "The complete list of tasks. Include all tasks - both "
                    "completed and pending."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": (
                                "Unique identifier for the task (e.g., "
                                "'task-1', 'task-2')"
                            ),
                        },
                        "text": {
                            "type": "string",
                            "description": "Description of the task",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                            "description": (
                                "Current status: 'pending' (not started), "
                                "'in_progress' (currently working on), "
                                "'completed' (done)"
                            ),
                        },
                    },
                    "required": ["id", "text", "status"],
                },
            },
        },
        "required": ["todos"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
