"""
Tool Executor for AI Assistant File Operations

Executes file system tool calls from AI assistants by interfacing with SandboxExecutor.
Also handles MCP-based tools (GitHub, etc.) when configured.
"""

import logging
from typing import Dict, Any, Optional
from .sandbox_executor import SandboxExecutor
from .mcp_tools import MCPToolExecutor

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tool calls from AI assistants."""

    def __init__(self, sandbox_executor: SandboxExecutor, github_token: Optional[str] = None):
        self.sandbox_executor = sandbox_executor
        self.github_token = github_token
        self._mcp_executor: Optional[MCPToolExecutor] = None

    @property
    def mcp_executor(self) -> Optional[MCPToolExecutor]:
        """Lazy-initialized MCP tool executor."""
        if self._mcp_executor is None and self.github_token:
            self._mcp_executor = MCPToolExecutor(github_token=self.github_token)
        return self._mcp_executor

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
            # Check if this is a GitHub MCP tool
            if tool_name.startswith('github_'):
                return self._handle_mcp_tool(tool_name, tool_arguments)

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
                "write_file": self._handle_write_file,
                "edit_file": self._handle_edit_file,
                "create_directory": self._handle_create_directory,
                "delete_file": self._handle_delete_file,
                "rename_file": self._handle_rename_file,
                "run_bash": self._handle_run_bash,
                "update_todos": self._handle_update_todos,
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

        try:
            result = self.sandbox_executor.list_files(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                path=path
            )

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

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_read_file(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Read file content."""
        path = args["path"]

        try:
            result = self.sandbox_executor.read_file(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                path=path
            )

            if result.get("success"):
                content = result.get("content", "")
                return {
                    "success": True,
                    "data": {
                        "path": path,
                        "content": content,
                        "size": len(content),
                        "lines": content.count('\n') + 1 if content else 0
                    }
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to read file")
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

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

        try:
            result = self.sandbox_executor.write_file(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                path=path,
                content=content
            )

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

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_edit_file(
        self,
        args: Dict[str, Any],
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool
    ) -> Dict[str, Any]:
        """Edit file by replacing old content with new content."""
        path = args["path"]
        old_content = args["old_content"]
        new_content = args["new_content"]

        try:
            result = self.sandbox_executor.edit_file(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                path=path,
                old_content=old_content,
                new_content=new_content
            )

            if result.get("success"):
                return {
                    "success": True,
                    "data": {
                        "path": path,
                        "message": f"Successfully edited {path}"
                    }
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to edit file")
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

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

        try:
            result = self.sandbox_executor.create_directory(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                path=path
            )

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

        except Exception as e:
            return {"success": False, "error": str(e)}

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

        try:
            result = self.sandbox_executor.delete_file(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                path=path
            )

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

        except Exception as e:
            return {"success": False, "error": str(e)}

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

        try:
            result = self.sandbox_executor.rename_file(
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                old_path=old_path,
                new_path=new_path
            )

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

        except Exception as e:
            return {"success": False, "error": str(e)}

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

        try:
            # Use execute_code with language='bash'
            output, error, exit_code, execution_time, artifacts = self.sandbox_executor.execute_code(
                code=command,
                language="bash",
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                sync_mode=sync_mode,
                timeout=timeout
            )

            # Combine stdout and stderr for display
            full_output = output
            if error:
                full_output = f"{output}\n{error}" if output else error

            return {
                "success": exit_code == 0,
                "data": {
                    "command": command,
                    "output": full_output.strip() if full_output else "(no output)",
                    "exit_code": exit_code,
                    "execution_time": round(execution_time, 2),
                    "artifacts": artifacts
                },
                "error": f"Command failed with exit code {exit_code}" if exit_code != 0 else None
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

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
        # Support both 'text' (our format) and 'content' (Coding Agent format) fields
        validated_todos = []
        for todo in todos:
            if isinstance(todo, dict) and "status" in todo:
                # Get text from either 'text' or 'content' field
                text = todo.get("text") or todo.get("content") or ""
                # Get id or generate one
                todo_id = str(todo.get("id", len(validated_todos) + 1))
                if text:
                    validated_todos.append({
                        "id": todo_id,
                        "text": str(text),
                        "status": todo["status"] if todo["status"] in ["pending", "in_progress", "completed"] else "pending"
                    })

        # Count by status
        completed = len([t for t in validated_todos if t["status"] == "completed"])
        in_progress = len([t for t in validated_todos if t["status"] == "in_progress"])
        pending = len([t for t in validated_todos if t["status"] == "pending"])

        return {
            "success": True,
            "data": {
                "todos": validated_todos,
                "summary": {
                    "total": len(validated_todos),
                    "completed": completed,
                    "in_progress": in_progress,
                    "pending": pending
                },
                "message": f"Updated {len(validated_todos)} tasks ({completed} completed, {in_progress} in progress, {pending} pending)"
            }
        }

    def _handle_mcp_tool(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle MCP-based tool calls (GitHub, etc.).

        Args:
            tool_name: Name of the MCP tool
            tool_arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if not self.mcp_executor:
            return {
                "success": False,
                "error": "MCP tools not configured. Please connect your GitHub account to use GitHub tools."
            }

        try:
            result = self.mcp_executor.execute(tool_name, tool_arguments)
            return result
        except Exception as e:
            logger.error(f"MCP tool execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"MCP tool failed: {str(e)}"
            }
