"""
HTTP Tool Executor for AI Assistant File Operations

Executes file system tool calls from AI assistants by making HTTP calls to the Orchestrator service.
This approach avoids the need for docker package in the web container.
"""

import json
import logging
import asyncio
import requests
from typing import Dict, Any, Optional

from sterna.middleware.request_id import request_id_headers

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(coro)


def _fetch_user_model_preferences_sync(user_id: str) -> dict:
    """Fetch user's coding agent model preferences (sync version for HTTPToolExecutor).

    Returns dict with fast_model_id, balanced_model_id, powerful_model_id.
    Uses get_model_for_tier() to resolve empty values to catalog defaults.
    """
    defaults = {
        "fast_model_id": "anthropic/claude-haiku-4.5",
        "balanced_model_id": "anthropic/claude-sonnet-4.5",
        "powerful_model_id": "anthropic/claude-opus-4.5",
    }
    try:
        from code_sessions.models import UserModelPreferences
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)
        prefs = UserModelPreferences.get_or_create_for_user(user)
        # Use get_model_for_tier() which handles empty values by resolving
        # from catalog, instead of returning raw "" from DB fields
        return {
            "fast_model_id": prefs.get_model_for_tier("fast"),
            "balanced_model_id": prefs.get_model_for_tier("balanced"),
            "powerful_model_id": prefs.get_model_for_tier("powerful"),
        }
    except Exception as e:
        logger.warning(f"[model_prefs] Failed to fetch model preferences: {e}")
        return defaults


def _fetch_sub_agents_sync(user_id: str) -> tuple:
    """Fetch active sub-agents for a user (sync version for HTTPToolExecutor).

    Returns (sub_agents_for_pipeline, sub_agent_descriptions).
    """
    try:
        from code_sessions.models import SubAgent, MAX_SUB_AGENTS_PER_USER

        agents = list(
            SubAgent.objects.filter(user_id=user_id, is_active=True)[:MAX_SUB_AGENTS_PER_USER]
        )
        if not agents:
            return [], []
        pipeline = [{"name": a.name, "markdown": a.to_markdown()} for a in agents]
        descriptions = [{"name": a.name, "description": a.description} for a in agents]
        return pipeline, descriptions
    except Exception as e:
        logger.warning(f"[sub_agents] Failed to fetch sub-agents: {e}")
        return [], []


class HTTPToolExecutor:
    """Executes tool calls from AI assistants via HTTP API to Orchestrator."""

    def __init__(
        self,
        orchestrator_url: str = "http://sterna-orchestrator:8003",
        auth_token: Optional[str] = None,
        github_token: Optional[str] = None
    ):
        """
        Initialize HTTP tool executor.

        Args:
            orchestrator_url: Base URL of orchestrator service
            auth_token: JWT token for authentication (uses dev token if None)
            github_token: Optional GitHub OAuth token for GitHub MCP tools
        """
        self.orchestrator_url = orchestrator_url.rstrip('/')
        # Use provided token or fall back to dev token for development
        self.auth_token = auth_token if auth_token else "dev-access-token-file-tools"
        self.github_token = github_token
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
        # Add GitHub token to headers if provided
        if github_token:
            self.headers["X-GitHub-Token"] = github_token
        logger.debug(f"HTTPToolExecutor initialized (token present: {bool(self.auth_token)})")

    def execute_tool_call(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a tool call from an AI assistant.

        Args:
            tool_name: Name of the tool to execute
            tool_arguments: Arguments for the tool
            user_id: User ID for sandbox isolation
            conversation_id: Conversation ID for sandbox isolation
            chat_id: Optional chat ID for finer isolation
            sync_mode: Whether to use synced sandbox mode

        Returns:
            Dict with execution result (success, data, error)
        """
        logger.info(f"Executing tool call: {tool_name} with args: {tool_arguments}")

        try:
            # Handle GitHub MCP tools directly (no sandbox needed - API calls)
            if tool_name.startswith('github_'):
                return self._handle_github_tool(tool_name, tool_arguments)

            # Normalize paths - convert relative paths to /workspace paths
            if "path" in tool_arguments:
                tool_arguments["path"] = self._normalize_path(tool_arguments["path"])
            if "old_path" in tool_arguments:
                tool_arguments["old_path"] = self._normalize_path(tool_arguments["old_path"])
            if "new_path" in tool_arguments:
                tool_arguments["new_path"] = self._normalize_path(tool_arguments["new_path"])

            # Route to appropriate handler
            handlers = {
                "list_files": self._handle_list_files,
                "read_file": self._handle_read_file,
                "search_code": self._handle_search_code,
                "write_file": self._handle_write_file,
                "edit_file": self._handle_edit_file,
                "create_directory": self._handle_create_directory,
                "delete_file": self._handle_delete_file,
                "rename_file": self._handle_rename_file,
                "run_bash": self._handle_run_bash,
                "update_todos": self._handle_update_todos,
                "prepare_pull_request": self._handle_prepare_pull_request,
                "execute_programming_task": self._handle_execute_programming_task,
                "explore_codebase": self._handle_explore_codebase,
                "coding_agent": self._handle_coding_agent,
                "clone_repo": self._handle_clone_repo,
                "plan_implementation": self._handle_plan_implementation,
                "implement_plan": self._handle_implement_plan,
                "edit_plan": self._handle_edit_plan,
            }

            handler = handlers.get(tool_name)
            if not handler:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}"
                }

            return handler(tool_arguments, user_id, conversation_id, chat_id, sync_mode)

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    def _normalize_path(self, path: str) -> str:
        """Normalize path to be relative to /workspace."""
        path = path.strip()

        # If empty or '.', use /workspace
        if not path or path == '.':
            return '/workspace'

        # If already starts with /workspace, return as-is
        if path.startswith('/workspace'):
            return path

        # If starts with /, make it relative to /workspace
        if path.startswith('/'):
            return f'/workspace{path}'

        # Otherwise, prepend /workspace/
        return f'/workspace/{path}'

    def _make_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make HTTP request to orchestrator."""
        url = f"{self.orchestrator_url}{endpoint}"

        try:
            logger.debug(f"Making request to {url} with payload: {payload}")
            response = requests.post(url, json=payload, headers=request_id_headers(self.headers), timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            return {
                "success": False,
                "error": f"HTTP request failed: {str(e)}"
            }

    def _handle_list_files(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """List files in directory."""
        path = args.get("path", "/workspace")
        depth = args.get("depth", 1)

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "path": path,
            "depth": depth
        }

        result = self._make_request("/fs/list", payload)

        if result.get("success"):
            files = result.get("files", [])
            # Format for AI readability
            file_list = []
            for file in files:
                file_type = "DIR" if file["type"] == "directory" else "FILE"
                file_list.append(f"[{file_type}] {file['name']}")

            return {
                "success": True,
                "data": {
                    "path": path,
                    "files": files,
                    "count": len(files),
                    "formatted": "\n".join(file_list) if file_list else "(empty directory)"
                }
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to list files")
            }

    def _handle_read_file(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Read file content with optional partial reading."""
        path = args["path"]

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "path": path,
        }

        # Add optional parameters if provided
        if "max_lines" in args:
            payload["max_lines"] = args["max_lines"]
        if "from_end" in args:
            payload["from_end"] = args["from_end"]
        if "start_line" in args:
            payload["start_line"] = args["start_line"]
        if "end_line" in args:
            payload["end_line"] = args["end_line"]
        if "summary_only" in args:
            payload["summary_only"] = args["summary_only"]

        result = self._make_request("/fs/read", payload)

        if result.get("success"):
            content = result.get("content", "")
            data = {
                "path": path,
                "content": content,
                "size": len(content),
            }
            # Include line info from the result
            if result.get("line_info"):
                data["line_info"] = result["line_info"]
            if result.get("total_lines"):
                data["total_lines"] = result["total_lines"]
            if result.get("summary_only"):
                data["summary_only"] = True

            return {
                "success": True,
                "data": data
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to read file")
            }

    def _handle_search_code(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Handle search_code tool - search for patterns in files."""
        pattern = args.get("pattern", "")
        if not pattern:
            return {"success": False, "error": "Pattern is required"}

        path = args.get("path", ".")
        include = args.get("include")
        context_lines = args.get("context_lines", 0)
        max_results = args.get("max_results", 50)
        ignore_case = args.get("ignore_case", False)

        # Normalize path
        path = self._normalize_path(path)

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "pattern": pattern,
            "path": path,
            "context_lines": context_lines,
            "max_results": min(max_results, 100),  # Cap at 100
            "ignore_case": ignore_case,
        }
        if include:
            payload["include"] = include

        result = self._make_request("/fs/search", payload)

        if result.get("success"):
            return {
                "success": True,
                "data": result.get("data", {})
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Search failed")
            }

    def _handle_write_file(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Write file content."""
        path = args["path"]
        content = args["content"]

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "path": path,
            "content": content,
            # Versioning metadata
            "source_type": "file_tool",
            "source_tool_name": "Write",
        }

        result = self._make_request("/fs/write", payload)

        if result.get("success"):
            return {
                "success": True,
                "data": {
                    "path": path,
                    "size": len(content),
                    "message": f"Successfully wrote {len(content)} bytes to {path}"
                }
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to write file")
            }

    def _handle_create_directory(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Create directory."""
        path = args["path"]

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "path": path
        }

        result = self._make_request("/fs/mkdir", payload)

        if result.get("success"):
            return {
                "success": True,
                "data": {
                    "path": path,
                    "message": f"Successfully created directory {path}"
                }
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to create directory")
            }

    def _handle_delete_file(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Delete file or directory."""
        path = args["path"]

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "path": path,
            # Versioning metadata
            "source_type": "file_tool",
        }

        result = self._make_request("/fs/delete", payload)

        if result.get("success"):
            return {
                "success": True,
                "data": {
                    "path": path,
                    "message": f"Successfully deleted {path}"
                }
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to delete")
            }

    def _handle_rename_file(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Rename or move file/directory."""
        old_path = args["old_path"]
        new_path = args["new_path"]

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "old_path": old_path,
            "new_path": new_path
        }

        result = self._make_request("/fs/rename", payload)

        if result.get("success"):
            return {
                "success": True,
                "data": {
                    "old_path": old_path,
                    "new_path": new_path,
                    "message": f"Successfully renamed/moved {old_path} to {new_path}"
                }
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to rename")
            }

    def _handle_edit_file(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Edit file by replacing content."""
        path = args["path"]
        old_content = args["old_content"]
        new_content = args["new_content"]

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "path": path,
            "old_content": old_content,
            "new_content": new_content,
            # Versioning metadata
            "source_type": "file_tool",
            "source_tool_name": "Edit",
        }

        result = self._make_request("/fs/edit", payload)

        if result.get("success"):
            return {
                "success": True,
                "data": {
                    "path": path,
                    "message": f"Successfully edited {path}",
                    "diff": result.get("diff", "")  # Pass through the diff from orchestrator
                }
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to edit file")
            }

    def _handle_run_bash(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Execute bash command in sandbox."""
        command = args["command"]
        timeout = min(args.get("timeout", 120), 300)  # Max 5 minutes

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "command": command,
            "timeout": timeout
        }

        result = self._make_request("/fs/bash", payload)

        if result.get("success"):
            return {
                "success": True,
                "data": {
                    "command": command,
                    "output": result.get("output", ""),
                    "exit_code": result.get("exit_code", 0),
                    "execution_time": result.get("execution_time", 0)
                }
            }
        else:
            return {
                "success": False,
                "data": {
                    "command": command,
                    "output": result.get("output", ""),
                    "exit_code": result.get("exit_code", 1),
                    "execution_time": result.get("execution_time", 0)
                },
                "error": result.get("error", "Command failed")
            }

    def _handle_update_todos(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """
        Handle todo list updates.
        This is a "virtual" tool - it doesn't interact with the sandbox,
        but returns the todos for the frontend to display.
        """
        todos = args.get("todos", [])

        # Validate todo structure
        validated_todos = []
        for todo in todos:
            if isinstance(todo, dict) and "status" in todo:
                # Get text from either 'text' or 'content' field
                text = todo.get("text") or todo.get("content") or ""
                todo_id = str(todo.get("id", len(validated_todos) + 1))
                if text:
                    validated_todos.append({
                        "id": todo_id,
                        "text": str(text),
                        "status": todo["status"] if todo["status"] in ["pending", "in_progress", "completed"] else "pending"
                    })

        return {
            "success": True,
            "data": {
                "todos": validated_todos,
                "count": len(validated_todos)
            }
        }

    def _handle_prepare_pull_request(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """
        Handle PR preparation.
        This is a "virtual" tool - it stores PR metadata for later use.
        The task loop will pick up this data and store it on the job.
        """
        title = args.get("title", "")
        summary = args.get("summary", "")
        changes = args.get("changes", [])
        test_plan = args.get("test_plan", "")

        if not title:
            return {
                "success": False,
                "error": "PR title is required"
            }

        if not summary:
            return {
                "success": False,
                "error": "PR summary is required"
            }

        # Build the PR body in standard format
        pr_body_parts = [
            "## Summary",
            "",
            summary,
            "",
            "## Changes",
            "",
        ]
        for change in changes:
            pr_body_parts.append(f"- {change}")

        if test_plan:
            pr_body_parts.extend([
                "",
                "## Test Plan",
                "",
                test_plan,
            ])

        pr_body_parts.extend([
            "",
            "---",
            "*Created with Sterna*"
        ])

        pr_body = "\n".join(pr_body_parts)

        return {
            "success": True,
            "data": {
                "pr_title": title,
                "pr_body": pr_body,
                "pr_ready": True,
                "message": f"PR prepared: {title}"
            }
        }

    def _handle_execute_programming_task(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """
        Execute a programming task (PTC - Programmatic Tool Calling).
        Runs Python code in the sandbox for complex multi-file operations.
        """
        code = args.get("code", "")
        task_description = args.get("task_description", "Programming task")

        if not code:
            return {
                "success": False,
                "error": "Code is required for execute_programming_task"
            }

        logger.info(f"Executing programming task: {task_description[:50]}...")

        # Execute via orchestrator /execute endpoint
        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_id": chat_id,
            "sync_mode": sync_mode,
            "code": code,
            "language": "python",
            "timeout": 600,  # 10 minutes for complex programming tasks
        }

        result = self._make_request("/execute", payload)

        output = result.get("output", "")
        error = result.get("error", "")
        exit_code = result.get("exit_code", 0)

        if exit_code != 0 or error:
            logger.warning(f"PTC execution error: {error}")
            return {
                "success": False,
                "error": error or "Execution failed",
                "output": output,
                "task": task_description
            }

        # Try to parse output as JSON for cleaner response
        try:
            parsed_output = json.loads(output.strip())
            return {
                "success": True,
                "data": {
                    "result": parsed_output,
                    "task": task_description
                }
            }
        except json.JSONDecodeError:
            # Return raw output if not JSON
            return {
                "success": True,
                "data": {
                    "output": output,
                    "task": task_description
                }
            }

    def _handle_explore_codebase(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """
        Explore the codebase using a fast/cheap model (Scout).
        Returns structured findings about relevant files and approach.
        """
        task = args.get("task", "")

        if not task:
            return {
                "success": False,
                "error": "Task description is required for explore_codebase"
            }

        logger.info(f"[explore_codebase] Starting exploration for: {task[:100]}...")

        try:
            from code_sessions.optimization.scout import ScoutAgent

            # Determine workspace path based on chat_id
            workspace_path = f"/workspace/chat-{chat_id}/repo"

            scout = ScoutAgent()
            report = scout.explore(
                task=task,
                workspace_path=workspace_path,
                auth_token=self.auth_token,
                user_id=user_id,
                session_id=conversation_id,
                on_step=None,  # No UI updates needed
            )

            logger.info(f"[explore_codebase] Scout completed: {report.iterations} iterations, "
                       f"{report.exploration_tokens} tokens, success={report.success}")

            if not report.success:
                return {
                    "success": False,
                    "error": report.error or "Exploration failed",
                    "data": {
                        "exploration_tokens": report.exploration_tokens,
                    }
                }

            # Format response for the main model
            result_data = {
                "files_to_modify": [
                    {
                        "path": f.path,
                        "reason": f.reason,
                        "relevant_lines": f.relevant_lines,
                    }
                    for f in report.files_to_modify
                ],
                "files_to_create": [
                    {
                        "path": f.path,
                        "purpose": f.purpose,
                    }
                    for f in report.files_to_create
                ],
                "approach": report.approach,
                "code_snippets": [
                    {
                        "path": s.path,
                        "lines": s.lines,
                        "content": s.content[:2000],  # Limit snippet size
                    }
                    for s in report.snippets[:5]  # Limit to 5 snippets
                ],
                "exploration_tokens": report.exploration_tokens,
                "exploration_cost": float(report.exploration_cost),
            }

            # Build a human-readable summary for the model
            summary_parts = []
            if report.files_to_modify:
                summary_parts.append(f"Found {len(report.files_to_modify)} file(s) to modify:")
                for f in report.files_to_modify[:5]:
                    lines_info = f" (lines {f.relevant_lines})" if f.relevant_lines else ""
                    summary_parts.append(f"  - {f.path}{lines_info}: {f.reason}")

            if report.files_to_create:
                summary_parts.append(f"\nNeed to create {len(report.files_to_create)} new file(s):")
                for f in report.files_to_create[:5]:
                    summary_parts.append(f"  - {f.path}: {f.purpose}")

            if report.approach:
                summary_parts.append(f"\nSuggested approach:\n{report.approach}")

            result_data["summary"] = "\n".join(summary_parts) if summary_parts else "No specific findings."

            return {
                "success": True,
                "data": result_data
            }

        except ImportError as e:
            logger.error(f"[explore_codebase] Import error: {e}")
            return {
                "success": False,
                "error": "Scout agent not available"
            }
        except Exception as e:
            logger.error(f"[explore_codebase] Error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Exploration failed: {str(e)}"
            }

    def _handle_clone_repo(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """
        Clone a GitHub repository into the workspace.

        Args:
            args: Tool arguments (repo_url, branch)
            user_id: User ID for sandbox isolation
            conversation_id: Conversation ID for ClonedRepository record
            chat_id: Chat ID for workspace scoping
            sync_mode: Whether to use synced sandbox mode

        Returns:
            Dict with clone result
        """
        repo_url = args.get("repo_url", "")
        branch = args.get("branch")

        if not repo_url:
            return {
                "success": False,
                "error": "repo_url is required"
            }

        if not self.github_token:
            return {
                "success": False,
                "error": "GitHub not connected. Please connect your GitHub account to clone repositories."
            }

        if not chat_id:
            return {
                "success": False,
                "error": "Chat ID is required for clone_repo (workspace isolation)"
            }

        logger.info(f"[clone_repo] Cloning {repo_url} for user {user_id}, chat {chat_id}")

        try:
            # Import and use the clone service
            from code_sessions.services.clone import clone_repository

            result = _run_async(clone_repository(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                repo_url=repo_url,
                branch=branch,
                github_token=self.github_token,
                auth_token=self.auth_token,
            ))

            if result.get("success"):
                return {
                    "success": True,
                    "data": {
                        "full_name": result.get("full_name"),
                        "branch": result.get("branch"),
                        "workspace_path": result.get("workspace_path"),
                        "head_commit_sha": result.get("head_commit_sha"),
                        "head_commit_message": result.get("head_commit_message"),
                        "message": f"Successfully cloned {result.get('full_name')} to {result.get('workspace_path')}"
                    }
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Clone failed")
                }

        except ImportError as e:
            logger.error(f"[clone_repo] Import error: {e}")
            return {
                "success": False,
                "error": "Clone service not available"
            }
        except Exception as e:
            logger.error(f"[clone_repo] Error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Clone failed: {str(e)}"
            }

    def _handle_github_tool(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle GitHub MCP tools directly (no sandbox needed - API calls).

        Args:
            tool_name: GitHub tool name (e.g., 'github_list_issues')
            tool_arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if not self.github_token:
            return {
                "success": False,
                "error": "GitHub not connected. Please connect your GitHub account to use GitHub tools."
            }

        try:
            from sandbox.orchestrator.mcp_tools import MCPToolExecutor
            mcp_executor = MCPToolExecutor(github_token=self.github_token)
            result = mcp_executor.execute(tool_name, tool_arguments)
            return result
        except ImportError as e:
            logger.error(f"Failed to import MCP tools: {e}")
            return {
                "success": False,
                "error": "GitHub tools not available"
            }
        except Exception as e:
            logger.error(f"GitHub tool execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"GitHub API error: {str(e)}"
            }

    def _handle_coding_agent(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """
        Execute Coding Agent autonomous agent for complex coding tasks.

        Coding Agent runs inside the user's sandbox with access to their workspace,
        using the chat's selected model and the user's OpenRouter API key.

        Args:
            args: Tool arguments (task, allowed_tools, max_iterations)
            user_id: User ID for sandbox isolation
            conversation_id: Conversation ID for context
            chat_id: Chat ID for workspace scoping
            sync_mode: Whether to use synced sandbox mode

        Returns:
            Dict with execution result including steps and summary
        """
        task = args.get("task", "")
        sub_agent = args.get("sub_agent")
        allowed_tools = args.get("allowed_tools")
        max_iterations = args.get("max_iterations", 20)

        if not task:
            return {
                "success": False,
                "error": "Task description is required for coding_agent"
            }

        if not chat_id:
            return {
                "success": False,
                "error": "Chat ID is required for coding_agent (workspace isolation)"
            }

        logger.info(f"[coding_agent] Starting execution for user {user_id}, task: {task[:100]}...")

        try:
            # Import services
            from .services import execute_coding_agent, get_api_key_for_user
            from users.models import User

            # Get model from agent context (passed via thread-local or similar mechanism)
            # For now, use a default model - this will be enhanced when integrated with agent
            model = getattr(self, '_current_model', None) or "anthropic/claude-sonnet-4"

            # Get user object to retrieve API key
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return {
                    "success": False,
                    "error": f"User {user_id} not found"
                }

            # Get user's OpenRouter API key
            api_key = get_api_key_for_user(user)
            if not api_key:
                return {
                    "success": False,
                    "error": "No OpenRouter API key available for user"
                }

            # Get model metadata for file attribution
            model_metadata = self.get_model_metadata()

            # Fetch user's active sub-agents and model preferences
            sub_agents, sub_agent_descs = _fetch_sub_agents_sync(user_id)
            user_model_prefs = _fetch_user_model_preferences_sync(user_id)

            if sub_agent and sub_agent_descs:
                # A specific sub-agent was requested
                matching = [a for a in sub_agent_descs if a["name"] == sub_agent]
                if matching:
                    task = (
                        f"You MUST delegate this task to the \"{sub_agent}\" sub-agent using the Task tool. "
                        f"Do NOT do the work yourself — spawn the \"{sub_agent}\" agent and pass it the following task.\n\n"
                        f"Task for {sub_agent}:\n{task}"
                    )
                else:
                    available = ", ".join(a["name"] for a in sub_agent_descs)
                    return {
                        "success": False,
                        "error": f"Sub-agent '{sub_agent}' not found. Available sub-agents: {available or 'none'}"
                    }
            elif sub_agent_descs:
                agent_list = ", ".join(
                    f"{a['name']} ({a['description'][:80]})" for a in sub_agent_descs
                )
                task = f"{task}\n\nAvailable sub-agents you can delegate to via the Task tool: {agent_list}"

            # Execute Coding Agent via the service (async)
            result = _run_async(execute_coding_agent(
                user_id=user_id,
                chat_id=chat_id,
                task=task,
                model=model,
                api_key=api_key,
                auth_token=self.auth_token,
                allowed_tools=allowed_tools,
                max_iterations=max_iterations,
                conversation_id=conversation_id,
                model_metadata=model_metadata,
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
            ))

            # Extract cost regardless of success/failure
            cost_usd = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)

            if result.get("success"):
                job_result = result.get("result", {})
                return {
                    "success": True,
                    "cost_usd": cost_usd,  # For quota tracking by LangChain agent
                    "data": {
                        "job_id": result.get("job_id"),
                        "status": result.get("status"),
                        "summary": job_result.get("summary", "Task completed"),
                        "files_modified": job_result.get("files_modified", []),
                        "files_created": job_result.get("files_created", []),
                        "steps": result.get("steps", []),
                        "duration_ms": result.get("duration_ms", 0),
                        "total_tokens": job_result.get("total_tokens", 0),
                        "cost_usd": cost_usd,
                    }
                }
            else:
                return {
                    "success": False,
                    "cost_usd": cost_usd,
                    "error": result.get("error", "Coding Agent execution failed"),
                    "data": {
                        "job_id": result.get("job_id"),
                        "status": result.get("status"),
                    }
                }

        except ImportError as e:
            logger.error(f"[coding_agent] Import error: {e}")
            return {
                "success": False,
                "error": "Coding Agent service not available"
            }
        except Exception as e:
            logger.error(f"[coding_agent] Error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Coding Agent execution failed: {str(e)}"
            }

    def _handle_plan_implementation(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool,
    ) -> Dict[str, Any]:
        """Create an implementation plan for a task/issue.

        Flow:
        1. Call orchestrator to run coding agent in plan mode
        2. Orchestrator returns plan_content, read from the plan the run wrote
        3. Parse plan and save to DB via ORM
        """
        task = args.get("task", "")
        if not task:
            return {"success": False, "error": "Task description is required"}
        if not chat_id:
            return {"success": False, "error": "Chat ID is required"}

        try:
            from .services import execute_coding_agent, get_api_key_for_user
            from users.models import User
            from conversations.models import Conversation
            from code_sessions.services.plan_service import create_plan_from_content

            user = User.objects.get(id=user_id)
            api_key = get_api_key_for_user(user)
            if not api_key:
                return {"success": False, "error": "No OpenRouter API key available"}

            model = getattr(self, '_current_model', None) or "anthropic/claude-sonnet-4"
            model_metadata = self.get_model_metadata()

            # Fetch user's active sub-agents and model preferences
            sub_agents, _ = _fetch_sub_agents_sync(user_id)
            user_model_prefs = _fetch_user_model_preferences_sync(user_id)
            # Execute coding agent in plan mode
            result = _run_async(execute_coding_agent(
                user_id=user_id,
                chat_id=chat_id,
                task=task,
                model=model,
                api_key=api_key,
                auth_token=self.auth_token,
                allowed_tools=["Read", "Glob", "Grep", "Bash"],
                max_iterations=20,
                conversation_id=conversation_id,
                model_metadata=model_metadata,
                mode="plan",
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
            ))

            # Extract cost regardless of success/failure
            plan_cost = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)

            if not result.get("success"):
                return {
                    "success": False,
                    "cost_usd": plan_cost,
                    "error": result.get("error", "Planning failed"),
                }

            # Extract plan content from result
            plan_content = result.get("result", {}).get("plan_content", "")
            if not plan_content:
                plan_content = result.get("plan_content", "")
            if not plan_content:
                plan_content = result.get("result", {}).get("summary", "")

            if not plan_content:
                return {
                    "success": False,
                    "error": "Agent completed but no plan was produced.",
                }

            conversation = Conversation.objects.get(id=conversation_id)

            # Resolve target chat for chat-scoped plans
            target_chat = None
            if chat_id:
                from conversations.models import Chat
                target_chat = Chat.objects.filter(id=chat_id, conversation=conversation).first()

            # Parse and save plan via ORM
            plan = create_plan_from_content(
                plan_content=plan_content,
                conversation=conversation,
                task_description=task,
                issue_number=args.get("issue_number"),
                issue_url=args.get("issue_url", ""),
                issue_title=args.get("issue_title", ""),
                chat=target_chat,
            )

            return {
                "success": True,
                "cost_usd": plan_cost,
                "data": {
                    "plan_id": str(plan.id),
                    "plan_title": plan.title,
                    "total_steps": plan.total_steps,
                    "status": plan.status,
                }
            }

        except Exception as e:
            logger.error(f"[plan_implementation] Error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _handle_implement_plan(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool,
    ) -> Dict[str, Any]:
        """Execute an approved implementation plan.

        Flow:
        1. Load plan from DB via ORM
        2. Create implementation branch in sandbox
        3. Mark plan as in_progress
        4. Call orchestrator with plan content
        5. Push branch to GitHub
        6. Update plan status based on result
        """
        plan_id = args.get("plan_id", "")
        if not plan_id:
            return {"success": False, "error": "plan_id is required"}
        if not chat_id:
            return {"success": False, "error": "Chat ID is required"}

        try:
            from .services import execute_coding_agent, get_api_key_for_user
            from users.models import User
            from code_sessions.models import AgentPlan, ClonedRepository, GitHubConnection

            # Load plan from DB
            try:
                plan = AgentPlan.objects.get(id=plan_id, conversation__user_id=user_id)
            except AgentPlan.DoesNotExist:
                return {"success": False, "error": f"Plan {plan_id} not found"}

            if plan.status not in (AgentPlan.Status.READY, AgentPlan.Status.FAILED):
                return {"success": False, "error": f"Plan is not in a ready state (current: {plan.status})"}

            # Mark in progress
            plan.status = AgentPlan.Status.IN_PROGRESS
            plan.save(update_fields=["status", "updated_at"])

            # --- Create implementation branch in sandbox ---
            branch_name = f"implement/{plan.slug}"
            repo_path = f"/workspace/chat-{chat_id}/repo"

            cloned_repo = ClonedRepository.objects.filter(conversation_id=conversation_id).first()
            github_conn = GitHubConnection.objects.filter(user_id=user_id).first()

            # Create branch + set authenticated remote (git config already set in sandbox image)
            setup_cmds = [
                f"cd {repo_path} && git checkout -b {branch_name} || git checkout {branch_name}",
            ]
            if github_conn and github_conn.access_token and cloned_repo:
                auth_url = f"https://oauth2:{github_conn.access_token}@github.com/{cloned_repo.full_name}.git"
                setup_cmds.append(f"cd {repo_path} && git remote set-url origin '{auth_url}'")

            for cmd in setup_cmds:
                try:
                    self._make_request("/fs/bash", {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "chat_id": chat_id,
                        "sync_mode": True,
                        "command": cmd,
                        "timeout": 15,
                    })
                except Exception as cmd_err:
                    logger.warning(f"[implement_plan] Setup cmd failed: {cmd_err}")

            plan.implementation_branch = branch_name
            plan.save(update_fields=["implementation_branch", "updated_at"])

            user = User.objects.get(id=user_id)
            api_key = get_api_key_for_user(user)
            if not api_key:
                return {"success": False, "error": "No OpenRouter API key available"}

            model = getattr(self, '_current_model', None) or "anthropic/claude-sonnet-4"
            model_metadata = self.get_model_metadata()

            # Fetch user's active sub-agents and model preferences
            sub_agents, _ = _fetch_sub_agents_sync(user_id)
            user_model_prefs = _fetch_user_model_preferences_sync(user_id)

            # Execute coding agent in implement mode with plan content
            result = _run_async(execute_coding_agent(
                user_id=user_id,
                chat_id=chat_id,
                task=plan.task_description,
                model=model,
                api_key=api_key,
                auth_token=self.auth_token,
                max_iterations=50,
                conversation_id=conversation_id,
                model_metadata=model_metadata,
                mode="implement",
                plan_id=str(plan.id),
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
            ))

            # Update plan status
            if result.get("success"):
                plan.status = AgentPlan.Status.COMPLETED
            else:
                plan.status = AgentPlan.Status.FAILED
            plan.save(update_fields=["status", "updated_at"])

            # --- Push branch to GitHub after agent completes ---
            if result.get("success") and github_conn and github_conn.access_token:
                try:
                    push_result = self._make_request("/fs/bash", {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "chat_id": chat_id,
                        "sync_mode": True,
                        "command": f"cd {repo_path} && git push -u origin {branch_name}",
                        "timeout": 120,
                    })
                    if not push_result.get("success"):
                        logger.warning(f"[implement_plan] Push failed: {push_result.get('output', '')[:200]}")
                except Exception as push_err:
                    logger.warning(f"[implement_plan] Push error: {push_err}")

            # Extract cost regardless of success/failure
            impl_cost = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)

            if result.get("success"):
                job_result = result.get("result", {})
                return {
                    "success": True,
                    "cost_usd": impl_cost,
                    "data": {
                        "plan_id": str(plan.id),
                        "plan_status": plan.status,
                        "branch_name": branch_name,
                        "job_id": result.get("job_id"),
                        "summary": job_result.get("summary", "Implementation completed"),
                        "files_modified": job_result.get("files_modified", []),
                        "files_created": job_result.get("files_created", []),
                    }
                }
            else:
                return {
                    "success": False,
                    "cost_usd": impl_cost,
                    "error": result.get("error", "Implementation failed"),
                    "data": {"plan_id": str(plan.id), "plan_status": plan.status, "branch_name": branch_name},
                }

        except Exception as e:
            logger.error(f"[implement_plan] Error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _handle_edit_plan(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool,
    ) -> Dict[str, Any]:
        """Edit an existing plan by delegating to the coding agent.

        Flow:
        1. Load existing plan from DB
        2. Build task combining existing plan content + edit instructions
        3. Delegate to coding agent in plan mode (same as creation)
        4. Read updated plan.md, re-parse, update existing plan + steps
        """
        plan_id = args.get("plan_id", "")
        instructions = args.get("instructions", "")
        if not plan_id:
            return {"success": False, "error": "plan_id is required"}
        if not instructions:
            return {"success": False, "error": "instructions are required"}
        if not chat_id:
            return {"success": False, "error": "Chat ID is required"}

        try:
            from .services import execute_coding_agent, get_api_key_for_user
            from users.models import User
            from code_sessions.models import AgentPlan
            from code_sessions.services.plan_service import update_plan_from_content

            # Load existing plan
            try:
                plan = AgentPlan.objects.get(id=plan_id, conversation__user_id=user_id)
            except AgentPlan.DoesNotExist:
                return {"success": False, "error": f"Plan {plan_id} not found"}

            user = User.objects.get(id=user_id)
            api_key = get_api_key_for_user(user)
            if not api_key:
                return {"success": False, "error": "No OpenRouter API key available"}

            model = getattr(self, '_current_model', None) or "anthropic/claude-sonnet-4"
            model_metadata = self.get_model_metadata()

            # Build task: existing plan + edit instructions
            task = (
                f"Review and edit the following implementation plan.\n\n"
                f"**Edit Instructions:** {instructions}\n\n"
                f"**Current Plan:**\n\n{plan.plan_content}\n\n"
                f"Apply the requested changes and save the updated plan where these instructions say to, "
                f"using the same structured format (# Implementation Plan: ..., ## Summary, "
                f"## Steps with ### Step N: ..., **Files:** etc). "
                f"You may re-explore the codebase if needed to improve the plan."
            )

            # Fetch user's active sub-agents and model preferences
            sub_agents, _ = _fetch_sub_agents_sync(user_id)
            user_model_prefs = _fetch_user_model_preferences_sync(user_id)
            # Delegate to coding agent in plan mode
            result = _run_async(execute_coding_agent(
                user_id=user_id,
                chat_id=chat_id,
                task=task,
                model=model,
                api_key=api_key,
                auth_token=self.auth_token,
                allowed_tools=["Read", "Glob", "Grep", "Bash"],
                max_iterations=20,
                conversation_id=conversation_id,
                model_metadata=model_metadata,
                mode="plan",
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
            ))

            # Extract cost regardless of success/failure
            edit_cost = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)

            if not result.get("success"):
                return {
                    "success": False,
                    "cost_usd": edit_cost,
                    "error": result.get("error", "Plan editing failed"),
                }

            # Extract updated plan content
            plan_content = result.get("result", {}).get("plan_content", "")
            if not plan_content:
                plan_content = result.get("plan_content", "")
            if not plan_content:
                plan_content = result.get("result", {}).get("summary", "")

            if not plan_content:
                return {
                    "success": False,
                    "cost_usd": edit_cost,
                    "error": "Agent completed but no updated plan was produced.",
                }

            # Re-parse and update existing plan
            plan = update_plan_from_content(plan, plan_content)

            return {
                "success": True,
                "cost_usd": edit_cost,
                "data": {
                    "plan_id": str(plan.id),
                    "plan_title": plan.title,
                    "total_steps": plan.total_steps,
                    "status": plan.status,
                }
            }

        except Exception as e:
            logger.error(f"[edit_plan] Error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def set_current_model(self, model: str):
        """Set the current model for Coding Agent execution."""
        self._current_model = model

    def set_model_metadata(self, metadata: Dict[str, Any]):
        """Set model metadata for file attribution (model_name, model_id, provider, icons)."""
        self._model_metadata = metadata

    def get_model_metadata(self) -> Optional[Dict[str, Any]]:
        """Get the current model metadata."""
        return getattr(self, '_model_metadata', None)
