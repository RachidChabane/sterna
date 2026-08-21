"""
PTC Tool - Programmatic Tool Calling for Complex Programming Tasks

Enables LLM to orchestrate complex multi-file programming workflows
similar to Coding Agent. The LLM generates Python code that:
- Reads and analyzes multiple files
- Executes code and checks results
- Makes coordinated changes across files
- Runs iterative test-fix loops

Key benefit: Intermediate results stay in code execution context,
reducing token consumption by ~37% on complex tasks.
"""

import json
import logging
import httpx
from typing import Optional, Callable
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PTCToolContext:
    """Context for PTC execution - holds user info for sandbox access."""

    def __init__(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: str,
        auth_token: str,
        orchestrator_url: str = "http://orchestrator:8003",
        is_cancelled_callback: Optional[Callable[[], bool]] = None,
    ):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.chat_id = chat_id
        self.auth_token = auth_token
        self.orchestrator_url = orchestrator_url
        self.is_cancelled_callback = is_cancelled_callback
        self._http_client: Optional[httpx.AsyncClient] = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=600.0)  # 10 min for complex tasks
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class OrchestrationCodeInput(BaseModel):
    """Input schema for orchestration code execution."""
    code: str = Field(
        ...,
        description="Python code for multi-file tasks. Use relative paths (Path('.')). Print JSON summary at end."
    )
    task_description: str = Field(
        ...,
        description="Brief task description"
    )


# Context variable to hold the current PTC context
_ptc_context_var = None


def set_ptc_context(context: PTCToolContext):
    """Set the current PTC context."""
    global _ptc_context_var
    _ptc_context_var = context


def get_ptc_context() -> Optional[PTCToolContext]:
    """Get the current PTC context."""
    return _ptc_context_var


def create_ptc_tool(context: PTCToolContext):
    """
    Create the execute_programming_task tool with injected context.

    This implements Anthropic's Programmatic Tool Calling pattern for
    complex programming workflows where:
    - LLM generates Python code that performs multi-file operations
    - Intermediate results stay in code execution context
    - Only final summary returns to LLM context
    - Enables efficient batch processing of files
    """

    @tool("execute_programming_task", args_schema=OrchestrationCodeInput)
    async def execute_programming_task(code: str, task_description: str) -> str:
        """For multi-file tasks: refactoring, codebase analysis, batch operations. Use relative paths. Print JSON summary."""
        logger.info(f"[PTC] Executing programming task: {task_description}")

        # Check if cancelled
        if context.is_cancelled_callback and context.is_cancelled_callback():
            return json.dumps({
                "success": False,
                "error": "Operation cancelled by user"
            })

        try:
            # Execute via orchestrator (same sandbox as execute_code)
            client = context._get_http_client()

            request_data = {
                "code": code,  # Send code directly - no wrapping needed
                "language": "python",
                "timeout": 600,  # 10 minutes for complex programming tasks
                "user_id": context.user_id,
                "conversation_id": context.conversation_id,
                "chat_id": context.chat_id,
                "sync_mode": True,
            }

            logger.info(f"[PTC] Sending programming task to orchestrator: {task_description[:50]}...")

            response = await client.post(
                f"{context.orchestrator_url}/execute",
                json=request_data,
                headers={"Authorization": f"Bearer {context.auth_token}"}
            )
            response.raise_for_status()
            result = response.json()

            output = result.get("output", "")
            error = result.get("error", "")
            exit_code = result.get("exit_code", 0)

            if exit_code != 0 or error:
                logger.warning(f"[PTC] Execution error: {error}")
                return json.dumps({
                    "success": False,
                    "error": error or "Execution failed",
                    "output": output,
                    "task": task_description
                })

            # Try to parse output as JSON for cleaner response
            try:
                parsed_output = json.loads(output.strip())
                return json.dumps({
                    "success": True,
                    "result": parsed_output,
                    "task": task_description
                })
            except json.JSONDecodeError:
                # Return raw output if not JSON
                return json.dumps({
                    "success": True,
                    "output": output,
                    "task": task_description
                })

        except httpx.HTTPStatusError as e:
            logger.error(f"[PTC] HTTP error: {e.response.status_code} - {e.response.text}")
            return json.dumps({
                "success": False,
                "error": f"Orchestrator error: {e.response.status_code}",
                "task": task_description
            })
        except Exception as e:
            logger.error(f"[PTC] Execution failed: {e}", exc_info=True)
            return json.dumps({
                "success": False,
                "error": str(e),
                "task": task_description
            })

    return execute_programming_task


# Example complex programming tasks that benefit from PTC
PTC_EXAMPLE_TASKS = [
    {
        "description": "Refactor function name across codebase",
        "code": """
import json
from pathlib import Path
import re

old_name = "oldFunctionName"
new_name = "newFunctionName"
workspace = Path('.')  # Use current directory, NOT /workspace

# Find all files containing the old name
updated_files = []
for f in workspace.rglob('*.py'):
    content = f.read_text()
    if old_name in content:
        new_content = re.sub(r'\\b' + old_name + r'\\b', new_name, content)
        f.write_text(new_content)
        count = content.count(old_name)
        updated_files.append({'file': str(f), 'replacements': count})

print(json.dumps({
    'task': 'Refactored function name',
    'old_name': old_name,
    'new_name': new_name,
    'files_updated': len(updated_files),
    'details': updated_files
}))
"""
    },
    {
        "description": "Find and fix type errors",
        "code": """
import json
import subprocess
from pathlib import Path

# Run type checker on current directory
result = subprocess.run(['python', '-m', 'mypy', '.', '--json'],
                       capture_output=True, text=True)

# Parse errors
errors = []
for line in result.stdout.strip().split('\\n'):
    if line:
        try:
            errors.append(json.loads(line))
        except:
            pass

# Group by file
by_file = {}
for err in errors:
    f = err.get('file', 'unknown')
    if f not in by_file:
        by_file[f] = []
    by_file[f].append(err)

print(json.dumps({
    'total_errors': len(errors),
    'files_with_errors': len(by_file),
    'errors_by_file': {k: len(v) for k, v in by_file.items()}
}))
"""
    },
    {
        "description": "Analyze codebase dependencies",
        "code": """
import json
from pathlib import Path
import re

workspace = Path('.')  # Use current directory
imports = {}

for f in workspace.rglob('*.py'):
    content = f.read_text()
    file_imports = re.findall(r'^(?:from|import) ([\\w.]+)', content, re.MULTILINE)
    imports[str(f)] = list(set(file_imports))

# Find most common imports
all_imports = [imp for imps in imports.values() for imp in imps]
from collections import Counter
common = Counter(all_imports).most_common(10)

print(json.dumps({
    'files_analyzed': len(imports),
    'total_unique_imports': len(set(all_imports)),
    'most_common_imports': common
}))
"""
    }
]


def is_complex_programming_task(user_message: str) -> bool:
    """
    Detect if a user message describes a complex programming task
    that would benefit from PTC.

    Returns True for tasks like:
    - Multi-file refactoring
    - Codebase-wide searches/replacements
    - Running tests and fixing errors
    - Batch file operations
    """
    # Keywords indicating complex programming tasks
    complex_indicators = [
        # Multi-file operations
        "across all files", "in all files", "throughout the codebase",
        "every file", "all python files", "all .py files",
        "entire project", "whole codebase", "everywhere",
        # Refactoring
        "refactor", "rename everywhere", "replace all", "update all",
        "migrate", "upgrade all",
        # Analysis
        "find all", "count all", "analyze the codebase",
        "dependency analysis", "import analysis",
        # Testing loops
        "fix all errors", "fix all tests", "run tests and fix",
        "type errors", "lint errors",
        # Batch operations
        "batch", "bulk", "all occurrences",
    ]

    message_lower = user_message.lower()
    return any(indicator in message_lower for indicator in complex_indicators)
