"""Explore Codebase tool: runs a fast exploration pass over the workspace.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from the `explore_codebase` entry of
`FILE_TOOLS` in `sandbox.orchestrator.file_tools` — the model-facing
tool contract legacy V1 sends the model via `get_file_tools()`
(`llm.file_tools_integration`, called from `llm.views.stream_complete`).
Execution delegates to that same tool id via the injected legacy
invoker. `test_agent_core_file_tools_drift.py` guards this module
against drifting from that source.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "explore_codebase"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Explore Codebase"),
    description=(
        "Use a fast AI model to explore and analyze the codebase "
        "structure. Returns relevant files to modify, suggested "
        "approach, and code snippets. Use this BEFORE making changes "
        "when: (1) you're unfamiliar with the codebase, (2) you need to "
        "find where specific functionality lives, (3) the task requires "
        "understanding multiple files, or (4) you need to find all "
        "places affected by a change. For simple targeted changes where "
        "you already know the exact file, skip this and proceed "
        "directly."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "Description of what you're trying to accomplish. Be "
                    "specific about what you need to find or understand "
                    "in the codebase."
                ),
            },
            "focus_areas": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of directories or file patterns to "
                    "focus the exploration on (e.g., ['src/', 'tests/', "
                    "'*.py']). Leave empty to explore the entire "
                    "workspace."
                ),
            },
        },
        "required": ["task"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
