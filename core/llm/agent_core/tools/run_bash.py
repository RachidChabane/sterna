"""Run Bash tool: executes a shell command in the sandbox workspace.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from the `run_bash` entry of
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

TOOL_ID = "run_bash"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Run Bash"),
    description=(
        "Execute a bash command in the ISOLATED sandbox. Use for: running "
        "tests (npm test, pytest), installing dependencies (npm install, "
        "pip install), running build commands, checking versions. "
        "IMPORTANT: This sandbox is ISOLATED from GitHub - local git "
        "commands (git checkout, git commit, git push) will NOT affect "
        "the remote repository. To make changes to GitHub, use the "
        "github_* tools instead: github_create_branch to create branches, "
        "github_push_files to push changes, github_create_pull_request "
        "to create PRs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "The bash command to execute. Examples: 'npm install', "
                    "'npm run build', 'npm run test', 'pytest', 'pip install "
                    "-r requirements.txt'. NOTE: Do NOT use git "
                    "push/commit/checkout for GitHub operations - use "
                    "github_* tools instead."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Timeout in seconds (default: 120, max: 300). Use "
                    "higher values for long-running commands like npm "
                    "install."
                ),
                "default": 120,
            },
        },
        "required": ["command"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.AUTO,
)
