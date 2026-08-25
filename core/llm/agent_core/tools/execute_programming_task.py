"""Execute Programming Task tool: runs Python in the sandbox for programmatic tool calling.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from the `execute_programming_task`
entry of `FILE_TOOLS` in `sandbox.orchestrator.file_tools` — the
model-facing tool contract legacy V1 sends the model via
`get_file_tools()` (`llm.file_tools_integration`, called from
`llm.views.stream_complete`). Execution delegates to that same tool
id via the injected legacy invoker. `test_agent_core_file_tools_drift.py`
guards this module against drifting from that source.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "execute_programming_task"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Execute Programming Task"),
    description=(
        "For COMPLEX multi-file programming tasks: refactoring across "
        "files, codebase-wide searches/replacements, batch operations, "
        "running tests and fixing errors. Generate Python code that "
        "performs the task - intermediate results stay in code context "
        "(37% token savings). Use relative paths (Path('.')). Print JSON "
        "summary at end."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Python code for multi-file tasks. Use relative "
                    "paths like Path('.'). Available: pathlib, "
                    "subprocess, json, re, os. Print JSON summary at end "
                    "for results."
                ),
            },
            "task_description": {
                "type": "string",
                "description": "Brief description of what this programming task accomplishes",
            },
        },
        "required": ["code", "task_description"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.REQUIRED,
)
