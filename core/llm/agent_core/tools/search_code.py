"""Search Code tool: searches for a pattern across sandbox files.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from the `search_code` entry of
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

TOOL_ID = "search_code"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Search Code"),
    description=(
        "Search for patterns in files using regex. Faster than reading "
        "multiple files. Returns matching lines with file paths and line "
        "numbers. Use for: finding function definitions, locating "
        "imports, finding all usages of a variable/function, searching "
        "for TODOs/FIXMEs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": (
                    "Regex pattern to search for. Examples: "
                    "'def process_', 'import.*requests', 'TODO|FIXME', "
                    "'class.*Controller'"
                ),
            },
            "path": {
                "type": "string",
                "description": (
                    "Directory or file to search in (relative to "
                    "/workspace). Default: '.' (entire workspace). "
                    "Examples: 'src', 'src/components', 'app.py'"
                ),
                "default": ".",
            },
            "include": {
                "type": "string",
                "description": (
                    "Glob pattern to filter files. Examples: '*.py', "
                    "'*.ts', '*.{js,jsx,ts,tsx}', 'test_*.py'"
                ),
            },
            "context_lines": {
                "type": "integer",
                "description": (
                    "Number of lines to show before and after each match "
                    "(like grep -C). Default: 0"
                ),
                "default": 0,
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return. Default: 50",
                "default": 50,
            },
            "ignore_case": {
                "type": "boolean",
                "description": "Case-insensitive search. Default: false",
                "default": False,
            },
        },
        "required": ["pattern"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.REQUIRED,
)
