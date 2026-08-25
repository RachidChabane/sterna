"""Prepare Pull Request tool: formats PR metadata for the coding-agent task loop.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from the `prepare_pull_request` entry
of `FILE_TOOLS` in `sandbox.orchestrator.file_tools` — the
model-facing tool contract legacy V1 sends the model via
`get_file_tools()` (`llm.file_tools_integration`, called from
`llm.views.stream_complete`). Execution delegates to that same tool
id via the injected legacy invoker; it never reaches the sandbox,
since that handler only assembles the PR title and body for the
caller to use. `test_agent_core_file_tools_drift.py` guards this
module against drifting from that source.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "prepare_pull_request"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Prepare Pull Request"),
    description=(
        "Prepare pull request metadata as your FINAL STEP after making "
        "code changes. This stores the PR title and description so the "
        "user can create the PR with one click. IMPORTANT: Before "
        "calling this, review recent commits in the repository to "
        "understand the naming convention (e.g., 'feat:', 'fix:', "
        "conventional commits, etc.). Use run_bash with 'git log "
        "--oneline -10' to see recent commits."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "PR title following the repository's commit/PR "
                    "naming convention. Keep it concise (max 72 chars). "
                    "Examples: 'feat: add user authentication', 'fix: "
                    "resolve login redirect issue'"
                ),
            },
            "summary": {
                "type": "string",
                "description": "Brief 1-3 sentence summary of what the PR accomplishes.",
            },
            "changes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of key changes made (bullet points). Each item "
                    "is one change."
                ),
            },
            "test_plan": {
                "type": "string",
                "description": (
                    "How the changes can be tested. Include specific "
                    "steps or commands."
                ),
            },
        },
        "required": ["title", "summary", "changes"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
