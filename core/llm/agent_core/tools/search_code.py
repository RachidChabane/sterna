"""Search Code tool: searches for a pattern across sandbox files.

No entry exists for this tool in `llm.tool_catalog.core_tools`, so its
schema is transcribed here from `HTTPToolExecutor._handle_search_code`
in `llm.http_tool_executor`, the handler this tool's execution
delegates to via the injected legacy invoker.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "search_code"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Search Code"),
    description=(
        "Search for a pattern across files in the sandbox workspace and "
        "return matching lines with surrounding context."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression or literal text to search for.",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search within.",
                "default": ".",
            },
            "include": {
                "type": "string",
                "description": "Glob restricting which files are searched, e.g. '*.py'.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of lines of context to include around each match.",
                "default": 0,
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return (capped at 100).",
                "default": 50,
            },
            "ignore_case": {
                "type": "boolean",
                "description": "Whether the search is case-insensitive.",
                "default": False,
            },
        },
        "required": ["pattern"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
