"""Run Bash tool: executes a shell command in the sandbox workspace.

No entry exists for this tool in `llm.tool_catalog.core_tools`, so its
schema is transcribed here from `HTTPToolExecutor._handle_run_bash` in
`llm.http_tool_executor`, the handler this tool's execution delegates
to via the injected legacy invoker.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "run_bash"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Run Bash"),
    description="Execute a bash command in the sandbox workspace and return its output.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to let the command run (capped at 300).",
                "default": 120,
            },
        },
        "required": ["command"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
