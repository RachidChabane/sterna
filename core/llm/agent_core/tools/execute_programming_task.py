"""Execute Programming Task tool: runs Python in the sandbox for programmatic tool calling.

No entry exists for this tool in `llm.tool_catalog.core_tools`, so its
schema is transcribed here from
`HTTPToolExecutor._handle_execute_programming_task` in
`llm.http_tool_executor`, the handler this tool's execution delegates
to via the injected legacy invoker.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "execute_programming_task"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Execute Programming Task"),
    description=(
        "Run Python code in the sandbox to perform a complex, multi-file "
        "operation programmatically rather than through individual file-tool calls."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute.",
            },
            "task_description": {
                "type": "string",
                "description": "A short description of what the code accomplishes.",
                "default": "Programming task",
            },
        },
        "required": ["code"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
