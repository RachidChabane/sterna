"""Prepare Pull Request tool: formats PR metadata for the coding-agent task loop.

No entry exists for this tool in `llm.tool_catalog.core_tools`, so its
schema is transcribed here from
`HTTPToolExecutor._handle_prepare_pull_request` in
`llm.http_tool_executor`, the handler this tool's execution delegates
to via the injected legacy invoker. It never reaches the sandbox: the
handler only assembles the PR title and body for the caller to use.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "prepare_pull_request"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Prepare Pull Request"),
    description=(
        "Assemble a pull request's title and body from a summary of the "
        "change, its individual changes, and an optional test plan."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The pull request title."},
            "summary": {
                "type": "string",
                "description": "A summary of what the change does and why.",
            },
            "changes": {
                "type": "array",
                "description": "Individual changes, listed as bullet points in the PR body.",
                "items": {"type": "string"},
            },
            "test_plan": {
                "type": "string",
                "description": "How the change was or should be verified.",
            },
        },
        "required": ["title", "summary"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
