"""
Agent Tool Handlers

Workspace, coding-agent, and plan tools bound to a V2 chat agent,
each a LangChain tool over the sandboxed workspace this request owns.
"""

import json
import logging
import httpx
import asyncio
import threading
import contextvars
from typing import Optional, Callable, Dict, List
from langchain_core.tools import tool

from sterna.middleware.request_id import request_id_headers
from llm.services.coding_agent_billing import (
    check_code_session_budget,
    quota_exceeded_error,
    run_and_settle,
)

logger = logging.getLogger(__name__)

# ContextVar for async-safe context lookup
# This ensures each async task gets its own context, even when sharing the same thread
_current_context_key: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'file_tools_context_key', default=None
)


class FileToolsContext:
    """Context for file tools execution - holds user/conversation info and model metadata"""

    def __init__(
            self,
            user_id: str,
            conversation_id: str,
            chat_id: str,
            auth_token: str,
            orchestrator_url: str = "http://orchestrator:8003",
            model_name: Optional[str] = None,
            model_id: Optional[str] = None,
            provider: Optional[str] = None,
            model_icon_slug: Optional[str] = None,
            model_icon_url: Optional[str] = None,
            provider_icon_slug: Optional[str] = None,
            provider_icon_url: Optional[str] = None,
            message_id: Optional[str] = None,
            is_cancelled_callback: Optional[Callable[[], bool]] = None,
            uploaded_files: Optional[List[Dict[str, str]]] = None,
            api_key: Optional[str] = None,  # OpenRouter API key for Coding Agent
            spark_ignite_request: Optional[Dict] = None,
    ):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.chat_id = chat_id
        self.auth_token = auth_token
        self.orchestrator_url = orchestrator_url
        self.model_name = model_name
        self.model_id = model_id
        self.provider = provider
        self.model_icon_slug = model_icon_slug
        self.model_icon_url = model_icon_url
        self.provider_icon_slug = provider_icon_slug
        self.provider_icon_url = provider_icon_url
        self.message_id = message_id
        self.is_cancelled_callback = is_cancelled_callback
        self.uploaded_files = uploaded_files or []
        self.api_key = api_key  # OpenRouter API key for Coding Agent
        self.spark_ignite_request = spark_ignite_request
        # Stores the full result from the last coding agent execution (steps, files, etc.)
        # Used by the heartbeat loop to enrich the SSE result with coding_agent_data
        self.last_coding_agent_result: Optional[Dict] = None
        # Resolved workspace chat_id (set by _resolve_workspace_chat_id).
        # May differ from chat_id when the repo was cloned in a different chat.
        self.workspace_chat_id: Optional[str] = None
        # Create a reusable HTTP client (will be closed when context is destroyed)
        self._http_client: Optional[httpx.AsyncClient] = None
        # Track in-flight requests for cancellation
        self._active_requests: Dict[str, asyncio.Task] = {}
        self._request_counter = 0

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (reusable across requests)"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close the HTTP client if it exists"""
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.warning(f"[FileTools] Error closing HTTP client: {e}")
            self._http_client = None

    async def _make_request(self, endpoint: str, data: dict, include_model_metadata: bool = False) -> dict:
        """Make authenticated async request to orchestrator with cancellation support"""
        # Generate unique request ID for tracking
        self._request_counter += 1
        request_id = f"req_{self._request_counter}_{endpoint.replace('/', '_')}"

        # Check if cancelled before starting request
        if self.is_cancelled_callback and self.is_cancelled_callback():
            logger.warning(f"[FileTools] Request {request_id} cancelled before execution")
            return {"success": False, "error": "Operation cancelled by user"}

        url = f"{self.orchestrator_url}{endpoint}"

        # Add context to request
        data.update({
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "chat_id": self.chat_id,
            "sync_mode": True
        })

        # Add model metadata for write operations
        if include_model_metadata and self.model_name:
            data["ai_metadata"] = {
                "model_name": self.model_name,
                "model_id": self.model_id,
                "provider": self.provider,
                "model_icon_slug": self.model_icon_slug,
                "model_icon_url": self.model_icon_url,
                "provider_icon_slug": self.provider_icon_slug,
                "provider_icon_url": self.provider_icon_url,
                "message_id": self.message_id
            }

        # Define the actual HTTP request as a cancellable async function
        async def do_request():
            """Execute the HTTP request - can be cancelled via task.cancel()"""
            try:
                # Check cancellation one more time before sending
                if self.is_cancelled_callback and self.is_cancelled_callback():
                    logger.warning(f"[FileTools] Request {request_id} cancelled before sending")
                    return {"success": False, "error": "Operation cancelled by user"}

                # Use the reusable HTTP client
                client = self._get_http_client()

                logger.info(f"[FileTools] Starting request {request_id} to {endpoint}")

                # Make the HTTP request - this can be cancelled mid-flight
                response = await client.post(
                    url,
                    json=data,
                    headers=request_id_headers({"Authorization": f"Bearer {self.auth_token}"}),
                    timeout=30.0  # Explicit timeout
                )
                response.raise_for_status()

                logger.info(f"[FileTools] Request {request_id} completed successfully")
                return response.json()

            except asyncio.CancelledError:
                # Task was cancelled - this is expected during user cancellation
                logger.warning(f"[FileTools] Request {request_id} cancelled mid-flight")
                raise  # Re-raise to propagate cancellation
            except Exception as e:
                logger.error(f"[FileTools] Request {request_id} failed: {e}")
                return {"success": False, "error": str(e)}

        # Create a tracked task for this request
        task = asyncio.create_task(do_request())
        self._active_requests[request_id] = task

        try:
            # Wait for the request to complete (or be cancelled)
            result = await task
            return result
        except asyncio.CancelledError:
            # Task was cancelled externally (via cancel_all_requests)
            logger.warning(f"[FileTools] Request {request_id} was cancelled")
            return {"success": False, "error": "Operation cancelled by user"}
        finally:
            # Always remove from active requests when done
            self._active_requests.pop(request_id, None)
            logger.debug(f"[FileTools] Request {request_id} removed from tracking ({len(self._active_requests)} active)")

    async def cancel_all_requests(self):
        """Cancel all in-flight HTTP requests immediately"""
        if not self._active_requests:
            logger.info("[FileTools] No active requests to cancel")
            return

        logger.warning(f"[FileTools] Cancelling {len(self._active_requests)} in-flight request(s)")

        # Cancel all active requests
        for request_id, task in list(self._active_requests.items()):
            if not task.done():
                logger.warning(f"[FileTools] Aborting in-flight request: {request_id}")
                task.cancel()
            else:
                logger.debug(f"[FileTools] Request {request_id} already completed")

        # Wait for all cancellations to complete (with timeout)
        if self._active_requests:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_requests.values(), return_exceptions=True),
                    timeout=2.0  # Give requests 2 seconds to abort
                )
                logger.info("[FileTools] All requests cancelled successfully")
            except asyncio.TimeoutError:
                logger.warning("[FileTools] Some requests did not cancel within timeout")

        # Clear the tracking dict
        self._active_requests.clear()


# Context management system using contextvars for proper async isolation
# ContextVars maintain separate values per async task, solving the race condition
# where multiple parallel requests on the same thread would overwrite each other's context
_contexts: Dict[str, FileToolsContext] = {}  # context_key -> FileToolsContext
_contexts_lock = threading.Lock()


def _make_context_key(user_id: str, conversation_id: str, chat_id: str) -> str:
    """Generate a unique key for a context based on user/conversation/chat IDs"""
    return f"{user_id}:{conversation_id}:{chat_id}"


def set_file_tools_context(context: FileToolsContext) -> str:
    """Set the context for file tools and return the context key"""
    # Generate context key from IDs
    context_key = _make_context_key(context.user_id, context.conversation_id, context.chat_id)

    # Store context in dict (protected by lock)
    with _contexts_lock:
        _contexts[context_key] = context

    # Set context key in ContextVar for this async task
    # This is the key fix: ContextVar maintains separate values per async task,
    # so parallel requests don't overwrite each other's context
    _current_context_key.set(context_key)

    logger.info(f"[FileTools] Set context for key {context_key} (chat_id={context.chat_id})")
    return context_key


def clear_file_tools_context(context_key: str):
    """Clear the context for a specific key"""
    with _contexts_lock:
        if context_key in _contexts:
            del _contexts[context_key]
            logger.info(f"[FileTools] Cleared context for key {context_key}")

    # Clear the contextvar if it matches (optional, for cleanup)
    if _current_context_key.get() == context_key:
        _current_context_key.set(None)


def _get_context() -> Optional[FileToolsContext]:
    """Get the current execution context using ContextVar for async-safe isolation"""
    # Get the context key from the ContextVar (async task-specific)
    context_key = _current_context_key.get()

    if context_key:
        with _contexts_lock:
            context = _contexts.get(context_key)
            if context:
                logger.debug(f"[FileTools] Retrieved context via contextvar, key={context_key}, chat_id={context.chat_id}")
                return context
            else:
                logger.warning(f"[FileTools] Context key {context_key} found in contextvar, but context not in dict")

    # No contextvar set - this shouldn't happen in normal operation
    logger.warning(
        f"[FileTools] No context key in contextvar. "
        f"Active contexts: {len(_contexts)}"
    )

    # Fallback for single context (safe in non-parallel scenarios)
    with _contexts_lock:
        if len(_contexts) == 1:
            context = list(_contexts.values())[0]
            logger.warning(f"[FileTools] Using single available context as fallback (chat_id={context.chat_id})")
            return context

        # Multiple contexts with no contextvar set - cannot safely determine which to use
        logger.error(f"[FileTools] Cannot determine context - {len(_contexts)} active contexts but no contextvar set")
        return None


@tool
async def list_files(path: str = "/workspace") -> str:
    """List files and directories."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    result = await context._make_request("/fs/list", {"path": path})

    if result.get("success"):
        files = result.get("files", [])
        return json.dumps({"success": True, "files": files, "count": len(files)})
    else:
        return json.dumps({"success": False, "error": result.get("error", "Unknown error")})


@tool
async def read_file(
    path: str,
    max_lines: Optional[int] = None,
    from_end: Optional[bool] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    summary_only: Optional[bool] = None
) -> str:
    """Read file contents from workspace. For LARGE files (100+ lines), use max_lines or line ranges to save tokens.

    Args:
        path: The file path to read (relative to workspace)
        max_lines: Maximum number of lines to return. Use this for large files.
        from_end: If true with max_lines, read last N lines instead of first N (like tail)
        start_line: Start line number (1-indexed). Use with end_line for specific ranges.
        end_line: End line number (1-indexed, inclusive). Use with start_line for specific ranges.
        summary_only: If true, return only file structure (functions, classes, imports) without code.
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    # Build request payload with optional parameters
    payload = {"path": path}
    if max_lines is not None:
        payload["max_lines"] = max_lines
    if from_end is not None:
        payload["from_end"] = from_end
    if start_line is not None:
        payload["start_line"] = start_line
    if end_line is not None:
        payload["end_line"] = end_line
    if summary_only is not None:
        payload["summary_only"] = summary_only

    result = await context._make_request("/fs/read", payload)

    if result.get("success"):
        content = result.get("content", "")
        response = {"success": True, "content": content, "path": path}
        # Include line info if partial read
        if result.get("line_info"):
            response["line_info"] = result.get("line_info")
        if result.get("total_lines"):
            response["total_lines"] = result.get("total_lines")
        return json.dumps(response)
    else:
        return json.dumps({"success": False, "error": result.get("error", "Unknown error")})


@tool
async def write_file(path: str, content: str) -> str:
    """Create new file. Use relative paths."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    # Include model metadata for tracking file creation
    result = await context._make_request("/fs/write", {"path": path, "content": content}, include_model_metadata=True)

    if result.get("success"):
        response = {
            "success": True,
            "path": result.get("path", path)
        }

        # If file was renamed, include detailed information
        if result.get("renamed"):
            response["renamed"] = True
            response["original_path"] = result.get("original_path", path)
            response["message"] = result.get("message", f"File created as '{response['path']}'")
        else:
            response["message"] = "File written successfully"

        return json.dumps(response)
    else:
        return json.dumps({"success": False, "error": result.get("error", "Unknown error")})


@tool
async def create_directory(path: str) -> str:
    """Create directory. Parent dirs auto-created."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    # Include model metadata for tracking directory creation
    result = await context._make_request("/fs/mkdir", {"path": path}, include_model_metadata=True)

    if result.get("success"):
        return json.dumps({"success": True, "path": path, "message": "Directory created successfully"})
    else:
        return json.dumps({"success": False, "error": result.get("error", "Unknown error")})


@tool
async def delete_file(path: str) -> str:
    """Delete file or directory."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    result = await context._make_request("/fs/delete", {"path": path})

    if result.get("success"):
        return json.dumps({"success": True, "path": path, "message": "Deleted successfully"})
    else:
        return json.dumps({"success": False, "error": result.get("error", "Unknown error")})


@tool
async def edit_file(path: str, old_content: str, new_content: str) -> str:
    """Replace exact text in file. Read file first to get exact match."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    result = await context._make_request("/fs/edit", {
        "path": path,
        "old_content": old_content,
        "new_content": new_content
    })

    if result.get("success"):
        response = {
            "success": True,
            "path": path,
            "message": f"Successfully edited {path}"
        }
        # Include diff if available for UI display
        if "diff" in result:
            response["diff"] = result["diff"]
        return json.dumps(response)
    else:
        return json.dumps({"success": False, "error": result.get("error", "Unknown error")})


@tool
async def rename_file(old_path: str, new_path: str) -> str:
    """Rename or move file."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    result = await context._make_request("/fs/rename", {"old_path": old_path, "new_path": new_path})

    if result.get("success"):
        return json.dumps({"success": True, "old_path": old_path, "new_path": new_path, "message": "Renamed successfully"})
    else:
        return json.dumps({"success": False, "error": result.get("error", "Unknown error")})


@tool
async def execute_code(code: str, language: str = "python") -> str:
    """Run Python/JS/Bash. Has pandas, numpy, matplotlib. Relative paths. savefig() for plots.
    NEVER use this to start a dev server or HTTP server — use start_preview instead."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    # Validate language
    valid_languages = ["python", "javascript", "bash", "shell"]
    if language not in valid_languages:
        return json.dumps({
            "success": False,
            "error": f"Invalid language '{language}'. Must be one of: {', '.join(valid_languages)}"
        })

    # Normalize shell/bash
    if language == "shell":
        language = "bash"

    # Prepare request data
    data = {
        "code": code,
        "language": language,
        "timeout": 30,  # 30 seconds timeout
        "sync_mode": True
    }

    # Note: Uploaded files are now copied to workspace immediately upon message receipt,
    # so we don't need to pass them here anymore. They're already in the workspace.

    # Make request to /execute endpoint
    result = await context._make_request("/execute", data)

    # Format response
    if "output" in result or "error" in result:
        # Successful execution (even if code had errors)
        return json.dumps({
            "success": result.get("exit_code", 1) == 0,
            "output": result.get("output", ""),
            "error": result.get("error", ""),
            "exit_code": result.get("exit_code", 1),
            "execution_time": result.get("execution_time", 0),
            "artifacts": result.get("artifacts", [])
        })
    else:
        # Request failed
        return json.dumps({
            "success": False,
            "error": result.get("error", "Unknown execution error")
        })


@tool
async def run_bash(command: str, timeout: int = 120) -> str:
    """Execute bash command. Use for: npm/pip install, tests, builds, git commands. Max 5 min timeout."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    # Clamp timeout to max 300 seconds (5 minutes)
    timeout = min(timeout, 300)

    # Make request to /fs/bash endpoint
    result = await context._make_request("/fs/bash", {
        "command": command,
        "timeout": timeout
    })

    if result.get("success"):
        return json.dumps({
            "success": True,
            "command": command,
            "output": result.get("output", ""),
            "exit_code": result.get("exit_code", 0),
            "execution_time": result.get("execution_time", 0)
        })
    else:
        return json.dumps({
            "success": False,
            "command": command,
            "output": result.get("output", ""),
            "error": result.get("error", "Command failed"),
            "exit_code": result.get("exit_code", 1),
            "execution_time": result.get("execution_time", 0)
        })


@tool
async def start_preview(command: str, port: int = 3000, cwd: str = "") -> str:
    """Start a dev server and open a live preview for the user.

    ALWAYS use this tool (not execute_code) when the user wants to run a server,
    start a dev server, serve files, preview a page, or run any long-running process.
    After calling, a preview panel opens automatically in the UI.

    Args:
        command: Server start command (e.g. 'npm run dev', 'python -m http.server 8000').
        port: Port the server listens on (3000-9999, default 3000).
        cwd: Working directory relative to workspace (e.g. 'spark-app-xxx'). If empty, uses workspace root.
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    if port < 3000 or port > 9999:
        return json.dumps({"success": False, "error": "Port must be between 3000 and 9999"})

    workspace_chat_id = await _resolve_workspace_chat_id(context)

    try:
        client = context._get_http_client()
        response = await client.post(
            f"{context.orchestrator_url}/processes/start",
            json={
                "user_id": context.user_id,
                "conversation_id": context.conversation_id,
                "chat_id": workspace_chat_id,
                "sync_mode": True,
                "command": command,
                "port": port,
                "cwd": cwd or None,
            },
            headers=request_id_headers({"Authorization": f"Bearer {context.auth_token}"}),
            timeout=15.0,
        )

        if response.status_code != 200:
            detail = response.json().get("detail", f"HTTP {response.status_code}")
            return json.dumps({"success": False, "error": detail, "command": command, "port": port})

        result = response.json()
        pid = result.get("pid")

        # Poll port readiness (up to 10s) to avoid showing blank iframe
        ready = False
        for _ in range(10):
            await asyncio.sleep(1.0)
            try:
                check = await client.get(
                    f"{context.orchestrator_url}/processes/health?user_id={context.user_id}&port={port}",
                    headers=request_id_headers({"Authorization": f"Bearer {context.auth_token}"}),
                    timeout=3.0,
                )
                if check.status_code == 200 and check.json().get("ready"):
                    ready = True
                    break
            except Exception:
                pass

        # Store last preview details on context for App record creation
        context.last_preview_command = command

        return json.dumps({
            "success": True,
            "pid": pid,
            "port": result.get("port", port),
            "command": command,
            "status": "running",
            "ready": ready,
            "message": f"Server started on port {port}." + ("" if ready else " Server is still starting up."),
        })

    except Exception as e:
        logger.error(f"[start_preview] Error: {e}")
        return json.dumps({"success": False, "error": str(e)})


@tool
async def stop_preview(port: int = 3000) -> str:
    """Stop a running preview server.

    Args:
        port: Port of the server to stop (default 3000).
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    try:
        client = context._get_http_client()
        response = await client.post(
            f"{context.orchestrator_url}/processes/stop-by-port",
            json={
                "user_id": context.user_id,
                "conversation_id": context.conversation_id,
                "port": port,
            },
            headers=request_id_headers({"Authorization": f"Bearer {context.auth_token}"}),
            timeout=10.0,
        )

        if response.status_code == 200:
            return json.dumps({"success": True, "port": port, "message": f"Server on port {port} stopped."})
        else:
            detail = response.json().get("detail", f"HTTP {response.status_code}")
            return json.dumps({"success": False, "error": detail})

    except Exception as e:
        logger.error(f"[stop_preview] Error: {e}")
        return json.dumps({"success": False, "error": str(e)})


@tool
async def list_processes() -> str:
    """List all running background processes (servers, dev servers, etc.) in the sandbox.

    Returns a list of processes with their PID, port, command, and status.
    Use this to check what's currently running before starting new servers.
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    workspace_chat_id = await _resolve_workspace_chat_id(context)

    try:
        client = context._get_http_client()
        response = await client.get(
            f"{context.orchestrator_url}/processes/{context.user_id}",
            params={"chat_id": workspace_chat_id},
            headers=request_id_headers({"Authorization": f"Bearer {context.auth_token}"}),
            timeout=10.0,
        )

        if response.status_code == 200:
            processes = response.json()
            if not processes:
                return json.dumps({"success": True, "processes": [], "message": "No running processes."})
            return json.dumps({"success": True, "processes": processes, "count": len(processes)})
        else:
            detail = response.json().get("detail", f"HTTP {response.status_code}")
            return json.dumps({"success": False, "error": detail})

    except Exception as e:
        logger.error(f"[list_processes] Error: {e}")
        return json.dumps({"success": False, "error": str(e)})


@tool
async def check_process_health(port: int) -> str:
    """Check if a process is running and responding on a given port.

    Use this to verify a server started successfully or is still alive.

    Args:
        port: Port number to check (3000-9999).
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    try:
        client = context._get_http_client()
        response = await client.get(
            f"{context.orchestrator_url}/processes/health",
            params={"user_id": context.user_id, "port": port},
            headers=request_id_headers({"Authorization": f"Bearer {context.auth_token}"}),
            timeout=5.0,
        )

        if response.status_code == 200:
            ready = response.json().get("ready", False)
            return json.dumps({
                "success": True,
                "port": port,
                "ready": ready,
                "message": f"Port {port} is {'responding' if ready else 'not responding'}.",
            })
        else:
            detail = response.json().get("detail", f"HTTP {response.status_code}")
            return json.dumps({"success": False, "error": detail})

    except Exception as e:
        logger.error(f"[check_process_health] Error: {e}")
        return json.dumps({"success": False, "error": str(e)})


@tool
async def update_todos(todos: list) -> str:
    """Update task list to track progress. Call at START to plan, update as you complete tasks."""
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

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

    return json.dumps({
        "success": True,
        "todos": validated_todos,
        "count": len(validated_todos)
    })


async def _resolve_workspace_chat_id(context) -> str:
    """Resolve the chat_id that owns the cloned workspace for this conversation.

    When a repo is cloned, it's placed in /workspace/chat-{CLONE_CHAT_ID}/repo.
    But when a user sends a message, the active chat may be different.
    This function looks up the ClonedRepository to find the original chat_id,
    ensuring the coding agent runs in the workspace where the repo actually lives.

    Falls back to context.chat_id if no cloned repo is found.
    The result is cached on context.workspace_chat_id for progress polling.
    """
    # Return cached value if already resolved
    if context.workspace_chat_id:
        return context.workspace_chat_id

    try:
        from code_sessions.models import ClonedRepository
        from asgiref.sync import sync_to_async
        import re

        cloned_repo = await sync_to_async(
            lambda: ClonedRepository.objects.filter(
                conversation_id=context.conversation_id
            ).first()
        )()

        if cloned_repo and cloned_repo.workspace_path:
            # workspace_path is like /workspace/chat-{chat_id}/repo
            match = re.search(r'/workspace/chat-([^/]+)/repo', cloned_repo.workspace_path)
            if match:
                clone_chat_id = match.group(1)
                if clone_chat_id != context.chat_id:
                    logger.info(
                        f"[workspace] Resolved clone chat_id={clone_chat_id} "
                        f"(active chat_id={context.chat_id})"
                    )
                context.workspace_chat_id = clone_chat_id
                return clone_chat_id
    except Exception as e:
        logger.warning(f"[workspace] Failed to resolve clone chat_id: {e}")

    context.workspace_chat_id = context.chat_id
    return context.chat_id


async def _ensure_repo_in_sandbox(context, workspace_chat_id: str) -> None:
    """Ensure the cloned repo exists in the sandbox, re-cloning if necessary.

    Delegates to the shared ensure_repo_in_sandbox() service which handles:
      1. Checking if .git exists in the sandbox
      2. Re-cloning from GitHub with branch fallback
      3. Force-restoring versioned files on top
      4. Reconciling git state (create branch, stage, commit)
    """
    try:
        from code_sessions.services.clone import ensure_repo_in_sandbox

        result = await ensure_repo_in_sandbox(
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            auth_token=context.auth_token,
            orchestrator_url=context.orchestrator_url,
        )

        if result.get("action") == "restored":
            logger.info(
                f"[workspace] Repo restored: branch={result.get('branch')}, "
                f"committed={result.get('committed')}"
            )
        elif not result.get("success"):
            logger.warning(f"[workspace] ensure_repo_in_sandbox failed: {result.get('error')}")

    except Exception as e:
        logger.warning(f"[workspace] Failed to ensure repo in sandbox: {e}")


async def _fetch_user_model_preferences(context) -> dict:
    """Fetch user's coding agent model preferences.

    Returns dict with fast_model_id, balanced_model_id, powerful_model_id.
    Uses get_model_for_tier() to resolve empty values to catalog defaults.
    Falls back to hardcoded defaults on error.
    """
    defaults = {
        "fast_model_id": "anthropic/claude-haiku-4.5",
        "balanced_model_id": "anthropic/claude-sonnet-4.5",
        "powerful_model_id": "anthropic/claude-opus-4.5",
    }
    try:
        from code_sessions.models import UserModelPreferences
        from asgiref.sync import sync_to_async

        prefs = await sync_to_async(UserModelPreferences.get_or_create_for_user)(
            await sync_to_async(lambda: __import__('django.contrib.auth', fromlist=['get_user_model']).get_user_model().objects.get(id=context.user_id))()
        )
        # Use get_model_for_tier() which handles empty values by resolving
        # from catalog, instead of returning raw "" from DB fields
        return {
            "fast_model_id": await sync_to_async(prefs.get_model_for_tier)("fast"),
            "balanced_model_id": await sync_to_async(prefs.get_model_for_tier)("balanced"),
            "powerful_model_id": await sync_to_async(prefs.get_model_for_tier)("powerful"),
        }
    except Exception as e:
        logger.warning(f"[model_prefs] Failed to fetch model preferences: {e}")
        return defaults


async def _fetch_user_sub_agents(context) -> tuple:
    """Fetch active sub-agents for the current user.

    Returns:
        (sub_agents_for_pipeline, sub_agent_descriptions) where:
        - sub_agents_for_pipeline: list of {name, markdown} dicts for sandbox injection
        - sub_agent_descriptions: list of {name, description} dicts for task augmentation
    """
    try:
        from code_sessions.models import SubAgent, MAX_SUB_AGENTS_PER_USER
        from asgiref.sync import sync_to_async

        agents = await sync_to_async(
            lambda: list(
                SubAgent.objects.filter(
                    user_id=context.user_id, is_active=True
                )[:MAX_SUB_AGENTS_PER_USER]
            )
        )()

        if not agents:
            return [], []

        pipeline = [{"name": a.name, "markdown": a.to_markdown()} for a in agents]
        descriptions = [{"name": a.name, "description": a.description} for a in agents]
        return pipeline, descriptions

    except Exception as e:
        logger.warning(f"[sub_agents] Failed to fetch sub-agents: {e}")
        return [], []


@tool
async def coding_agent(
    task: str,
    sub_agent: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    max_iterations: int = 20
) -> str:
    """Delegate complex coding tasks to the Coding Agent.

    Use this for tasks requiring multiple file operations, codebase exploration,
    or iterative development. The agent runs in your workspace sandbox with
    full access to read, write, edit files and run commands.

    Args:
        task: Clear description of the coding task to accomplish.
              Be specific about requirements and constraints.
              Examples:
              - "Implement user authentication with JWT tokens"
              - "Fix failing tests in tests/test_auth.py"
              - "Refactor database module to use connection pooling"
        sub_agent: Name of a specific sub-agent to run this task with (e.g.
                  "security-reviewer"). The task will be executed by that sub-agent
                  instead of the default coding agent.
        allowed_tools: Restrict which tools the agent can use.
                      Defaults to ["Read", "Write", "Edit", "Bash", "Glob", "Grep"].
                      Use ["Read", "Glob", "Grep"] for read-only exploration.
        max_iterations: Maximum agent iterations (1-100, default 20).
                       Increase for complex tasks.
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})

    if not task:
        return json.dumps({"success": False, "error": "Task description is required"})

    gate_denial, budget_usd = await check_code_session_budget(context)
    if gate_denial is not None:
        return gate_denial

    logger.info(f"[coding_agent] Starting execution, task: {task[:100]}...")

    try:
        # Import the service
        from .services import execute_coding_agent

        # Resolve the correct workspace chat_id (may differ from active chat)
        workspace_chat_id = await _resolve_workspace_chat_id(context)
        await _ensure_repo_in_sandbox(context, workspace_chat_id)

        # Write spark source code to workspace if this is an ignite request
        if context.spark_ignite_request and context.spark_ignite_request.get("spark_code"):
            spark_code = context.spark_ignite_request["spark_code"]
            spark_id = context.spark_ignite_request["spark_id"]
            try:
                await context._make_request("/fs/write", {
                    "path": f"spark-source-{spark_id}.tsx",
                    "content": spark_code
                })
                logger.info(f"[coding_agent] Pre-wrote spark source to spark-source-{spark_id}.tsx")
            except Exception as e:
                logger.warning(f"[coding_agent] Failed to pre-write spark source: {e}")

        # Get user's OpenRouter API key from context
        api_key = context.api_key
        if not api_key:
            return json.dumps({
                "success": False,
                "error": "No OpenRouter API key available. Please check your account settings."
            })

        # Use the model from context (chat's selected model)
        model = context.model_id or "anthropic/claude-sonnet-4"

        # Build model metadata for file attribution
        model_metadata = {
            "model_name": context.model_name,
            "model_id": context.model_id,
            "provider": context.provider,
            "model_icon_slug": context.model_icon_slug,
            "model_icon_url": context.model_icon_url,
            "provider_icon_slug": context.provider_icon_slug,
            "provider_icon_url": context.provider_icon_url,
            "message_id": context.message_id,
        }

        # Fetch user's active sub-agents and model preferences
        sub_agents, sub_agent_descs = await _fetch_user_sub_agents(context)
        user_model_prefs = await _fetch_user_model_preferences(context)

        if sub_agent and sub_agent_descs:
            # A specific sub-agent was requested — instruct the coding agent to delegate to it
            matching = [a for a in sub_agent_descs if a["name"] == sub_agent]
            if matching:
                task = (
                    f"You MUST delegate this task to the \"{sub_agent}\" sub-agent using the Task tool. "
                    f"Do NOT do the work yourself — spawn the \"{sub_agent}\" agent and pass it the following task.\n\n"
                    f"Task for {sub_agent}:\n{task}"
                )
            else:
                available = ", ".join(a["name"] for a in sub_agent_descs)
                return json.dumps({
                    "success": False,
                    "error": f"Sub-agent '{sub_agent}' not found. Available sub-agents: {available or 'none'}"
                })
        elif sub_agent_descs:
            agent_list = ", ".join(
                f"{a['name']} ({a['description'][:80]})" for a in sub_agent_descs
            )
            task = f"{task}\n\nAvailable sub-agents you can delegate to via the Task tool: {agent_list}"

        # Execute Coding Agent via the service, billed on completion
        # regardless of whether this request is still being listened to.
        result = await run_and_settle(
            context, model, context.chat_id or "",
            execute_coding_agent(
                user_id=context.user_id,
                chat_id=workspace_chat_id,
                task=task,
                model=model,
                api_key=api_key,
                auth_token=context.auth_token,
                allowed_tools=allowed_tools,
                max_iterations=max_iterations,
                conversation_id=context.conversation_id,
                model_metadata=model_metadata,
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
                budget_usd=budget_usd,
            ),
        )

        # Store full result on context so heartbeat loop can enrich SSE data
        context.last_coding_agent_result = result

        if result.get("result", {}).get("quota_exceeded"):
            return quota_exceeded_error(budget_usd)

        cost_usd = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)

        logger.info(f"[coding_agent] Post-execution: success={result.get('success')}, spark_ignite_request={bool(context.spark_ignite_request)}")
        build_verified = False
        if result.get("success"):
            # Mark spark as ignited if this was an ignite request
            if context.spark_ignite_request:
                spark_id = context.spark_ignite_request.get("spark_id")
                logger.info(f"[coding_agent] Ignite block entered: spark_id={spark_id}, user_id={context.user_id}, chat_id={context.chat_id}")
                if spark_id:
                    from asgiref.sync import sync_to_async

                    # Verify build completed successfully before igniting
                    try:
                        check_resp = await context._make_request("/fs/read", {
                            "path": f"spark-app-{spark_id}/.next/BUILD_ID",
                        })
                        build_verified = check_resp.get("success", False) and bool(check_resp.get("content", "").strip())
                        logger.info(f"[coding_agent] Build verification: BUILD_ID exists={build_verified}")
                    except Exception as e:
                        logger.warning(f"[coding_agent] Build verification failed: {e}")

                    if not build_verified:
                        logger.warning(f"[coding_agent] Skipping ignite — no valid BUILD_ID for spark {spark_id}")
                    else:
                        try:
                            from sparks.models import Spark
                            updated = await sync_to_async(
                                Spark.objects.filter(id=spark_id).update
                            )(is_ignited=True)
                            logger.info(f"[coding_agent] Spark.update(is_ignited=True) affected {updated} rows")
                        except Exception as e:
                            logger.warning(f"[coding_agent] Failed to mark spark ignited: {e}", exc_info=True)

                        # Create App record
                        try:
                            from sparks.models import App
                            from django.db.models import Max
                            from django.db.models.functions import Coalesce
                            from django.db import IntegrityError

                            spark = await sync_to_async(Spark.objects.get)(id=spark_id)
                            preview_command = getattr(context, 'last_preview_command', 'npm run dev')

                            for attempt in range(2):
                                next_version = await sync_to_async(
                                    lambda: (
                                        App.objects.filter(spark=spark, user_id=context.user_id)
                                        .aggregate(max_v=Coalesce(Max('version'), 0))
                                    )['max_v'] + 1
                                )()
                                try:
                                    await sync_to_async(App.objects.create)(
                                        spark=spark,
                                        user_id=context.user_id,
                                        chat_id=context.chat_id,
                                        title=spark.title,
                                        version=next_version,
                                        project_path=f"spark-app-{spark_id}",
                                        preview_command=preview_command,
                                    )
                                    logger.info(f"[coding_agent] Created App v{next_version} for spark {spark_id}")
                                    break
                                except IntegrityError:
                                    if attempt == 0:
                                        logger.info(f"[coding_agent] Version collision for spark {spark_id}, retrying")
                                        continue
                                    logger.warning(f"[coding_agent] Version collision persisted for spark {spark_id}")
                        except Exception as e:
                            logger.warning(f"[coding_agent] Failed to create App record: {e}", exc_info=True)

                        # Save workspace files to persistent storage so they survive container recycles
                        try:
                            save_resp = await context._make_request("/workspace/save", {
                                "chat_id": workspace_chat_id,
                            })
                            logger.info(
                                f"[coding_agent] Workspace save after ignite: "
                                f"success={save_resp.get('success')}, "
                                f"files_synced={save_resp.get('files_synced', 0)}"
                            )
                        except Exception as e:
                            logger.warning(f"[coding_agent] Workspace save after ignite failed: {e}")

            job_result = result.get("result", {})
            response_data = {
                "success": True,
                "job_id": result.get("job_id"),
                "status": result.get("status"),
                "summary": job_result.get("summary", "Task completed"),
                "files_modified": job_result.get("files_modified", []),
                "files_created": job_result.get("files_created", []),
                "steps_count": len(result.get("steps", [])),
                "duration_ms": result.get("duration_ms", 0),
                "cost_usd": cost_usd,
            }
            if context.spark_ignite_request:
                response_data["ignited"] = build_verified
                if not build_verified:
                    response_data["ignite_skipped_reason"] = "Build did not complete successfully (no .next/BUILD_ID)"
            return json.dumps(response_data)
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Coding Agent execution failed"),
                "job_id": result.get("job_id"),
                "status": result.get("status"),
                "cost_usd": cost_usd,
            })

    except ImportError as e:
        logger.error(f"[coding_agent] Import error: {e}")
        return json.dumps({
            "success": False,
            "error": "Coding Agent service not available"
        })
    except Exception as e:
        logger.error(f"[coding_agent] Error: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": f"Coding Agent execution failed: {str(e)}"
        })


# Export all tools as a list
FILE_TOOLS = [
    list_files,
    read_file,
    write_file,
    edit_file,  # IMPORTANT: This is the preferred way to modify existing files
    create_directory,
    delete_file,
    rename_file,
    execute_code,  # Execute Python/Node.js/Bash code in sandbox
    run_bash,  # Execute bash commands (same as code sessions)
    start_preview,  # Start dev server and open live preview
    stop_preview,  # Stop a running preview server
    list_processes,  # List running background processes
    check_process_health,  # Check if a process is responding on a port
    update_todos,  # Track task progress (same as code sessions)
]

# Coding Agent tool (separate export for feature-flag gating)
CODING_AGENT_TOOL = coding_agent

# All tool names that run the Coding Agent (used for timeout, progress polling, display)
CODING_AGENT_TOOL_NAMES = frozenset({
    'coding_agent', 'plan_implementation', 'implement_plan', 'edit_plan'
})


@tool
async def plan_implementation(
    task: str,
    issue_number: Optional[int] = None,
    issue_url: Optional[str] = None,
    issue_title: Optional[str] = None,
) -> str:
    """Create an implementation plan for a GitHub issue or task.

    Explores the codebase in read-only mode and produces a structured
    step-by-step implementation plan saved to the database.

    Args:
        task: Description of the feature/issue to plan.
        issue_number: GitHub issue number (if linked to an issue).
        issue_url: GitHub issue URL.
        issue_title: GitHub issue title.
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})
    if not task:
        return json.dumps({"success": False, "error": "Task description is required"})

    gate_denial, budget_usd = await check_code_session_budget(context)
    if gate_denial is not None:
        return gate_denial

    logger.info(f"[plan_implementation] Starting, task: {task[:100]}...")

    try:
        from .services import execute_coding_agent
        from asgiref.sync import sync_to_async

        # Resolve the correct workspace chat_id (may differ from active chat)
        workspace_chat_id = await _resolve_workspace_chat_id(context)
        await _ensure_repo_in_sandbox(context, workspace_chat_id)

        api_key = context.api_key
        if not api_key:
            return json.dumps({"success": False, "error": "No OpenRouter API key available"})

        model = context.model_id or "anthropic/claude-sonnet-4"
        model_metadata = {
            "model_name": context.model_name,
            "model_id": context.model_id,
            "provider": context.provider,
            "model_icon_slug": context.model_icon_slug,
            "model_icon_url": context.model_icon_url,
            "provider_icon_slug": context.provider_icon_slug,
            "provider_icon_url": context.provider_icon_url,
            "message_id": context.message_id,
        }

        # Fetch user's active sub-agents and model preferences
        sub_agents, sub_agent_descs = await _fetch_user_sub_agents(context)
        user_model_prefs = await _fetch_user_model_preferences(context)
        if sub_agent_descs:
            agent_list = ", ".join(
                f"{a['name']} ({a['description'][:80]})" for a in sub_agent_descs
            )
            task = f"{task}\n\nAvailable sub-agents you can delegate to via the Task tool: {agent_list}"

        result = await run_and_settle(
            context, model, context.chat_id or "",
            execute_coding_agent(
                user_id=context.user_id,
                chat_id=workspace_chat_id,
                task=task,
                model=model,
                api_key=api_key,
                auth_token=context.auth_token,
                allowed_tools=["Read", "Glob", "Grep", "Bash"],
                max_iterations=30,
                conversation_id=context.conversation_id,
                model_metadata=model_metadata,
                mode="plan",
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
                budget_usd=budget_usd,
            ),
        )

        # Store full result on context so heartbeat loop can enrich SSE data
        context.last_coding_agent_result = result

        if result.get("result", {}).get("quota_exceeded"):
            return quota_exceeded_error(budget_usd)

        if not result.get("success"):
            return json.dumps({"success": False, "error": result.get("error", "Planning failed")})

        plan_content = result.get("result", {}).get("plan_content", "")
        if not plan_content:
            plan_content = result.get("plan_content", "")
        if not plan_content:
            plan_content = result.get("result", {}).get("summary", "")

        if not plan_content:
            return json.dumps({"success": False, "error": "Agent completed but no plan was produced."})

        # Save plan to DB
        from conversations.models import Conversation, Chat
        from code_sessions.services.plan_service import create_plan_from_content

        conversation = await sync_to_async(Conversation.objects.get)(id=context.conversation_id)

        # Resolve target chat for chat-scoped plans
        target_chat = None
        if context.chat_id:
            target_chat = await sync_to_async(
                Chat.objects.filter(id=context.chat_id, conversation=conversation).first
            )()

        plan = await sync_to_async(create_plan_from_content)(
            plan_content=plan_content,
            conversation=conversation,
            task_description=task,
            issue_number=issue_number,
            issue_url=issue_url or "",
            issue_title=issue_title or "",
            chat=target_chat,
        )

        plan_cost = result.get("result", {}).get("total_cost_usd", 0.0)

        return json.dumps({
            "success": True,
            "data": {
                "plan_id": str(plan.id),
                "plan_title": plan.title,
                "total_steps": plan.total_steps,
                "status": plan.status,
            },
            "cost_usd": plan_cost,
        })

    except Exception as e:
        logger.error(f"[plan_implementation] Error: {e}", exc_info=True)
        # Try to extract partial cost from result if available
        partial_cost = 0.0
        try:
            if 'result' in dir() and isinstance(result, dict):
                partial_cost = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)
        except Exception:
            pass
        return json.dumps({"success": False, "error": str(e), "cost_usd": partial_cost})


@tool
async def implement_plan(
    plan_id: str,
) -> str:
    """Execute an approved implementation plan.

    Runs the coding agent to implement all steps in the plan,
    creating commits and optionally a pull request.

    Args:
        plan_id: UUID of the plan to implement.
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})
    if not plan_id:
        return json.dumps({"success": False, "error": "plan_id is required"})

    gate_denial, budget_usd = await check_code_session_budget(context)
    if gate_denial is not None:
        return gate_denial

    logger.info(f"[implement_plan] Starting, plan_id: {plan_id}")

    try:
        from .services import execute_coding_agent
        from code_sessions.models import AgentPlan, ClonedRepository, GitHubConnection
        from asgiref.sync import sync_to_async

        # Resolve the correct workspace chat_id (may differ from active chat)
        workspace_chat_id = await _resolve_workspace_chat_id(context)
        await _ensure_repo_in_sandbox(context, workspace_chat_id)

        # Load plan from DB
        try:
            plan = await sync_to_async(AgentPlan.objects.get)(
                id=plan_id, conversation__user_id=context.user_id
            )
        except AgentPlan.DoesNotExist:
            return json.dumps({"success": False, "error": f"Plan {plan_id} not found"})

        if plan.status not in (AgentPlan.Status.READY, AgentPlan.Status.FAILED):
            return json.dumps({"success": False, "error": f"Plan is not in a ready state (current: {plan.status})"})

        # Mark in progress
        plan.status = AgentPlan.Status.IN_PROGRESS
        await sync_to_async(plan.save)(update_fields=["status", "updated_at"])

        # --- Create implementation branch in sandbox ---
        branch_name = f"implement/{plan.slug}"
        repo_path = f"/workspace/chat-{workspace_chat_id}/repo"

        cloned_repo = await sync_to_async(
            lambda: ClonedRepository.objects.filter(conversation_id=context.conversation_id).first()
        )()
        github_conn = await sync_to_async(
            lambda: GitHubConnection.objects.filter(user_id=context.user_id).first()
        )()

        client = context._get_http_client()
        orchestrator_url = context.orchestrator_url
        headers = request_id_headers({"Authorization": f"Bearer {context.auth_token}", "Content-Type": "application/json"})

        # Create branch + set authenticated remote (git config already set in sandbox image)
        setup_cmds = [
            f"cd {repo_path} && git checkout -b {branch_name} || git checkout {branch_name}",
        ]
        if github_conn and github_conn.access_token and cloned_repo:
            auth_url = f"https://oauth2:{github_conn.access_token}@github.com/{cloned_repo.full_name}.git"
            setup_cmds.append(f"cd {repo_path} && git remote set-url origin '{auth_url}'")

        for cmd in setup_cmds:
            await client.post(
                f"{orchestrator_url}/fs/bash",
                json={
                    "user_id": context.user_id,
                    "conversation_id": context.conversation_id,
                    "chat_id": workspace_chat_id,
                    "sync_mode": True,
                    "command": cmd,
                    "timeout": 15,
                },
                headers=headers,
                timeout=20.0,
            )

        plan.implementation_branch = branch_name
        await sync_to_async(plan.save)(update_fields=["implementation_branch", "updated_at"])

        api_key = context.api_key
        if not api_key:
            return json.dumps({"success": False, "error": "No OpenRouter API key available"})

        model = context.model_id or "anthropic/claude-sonnet-4"
        model_metadata = {
            "model_name": context.model_name,
            "model_id": context.model_id,
            "provider": context.provider,
            "model_icon_slug": context.model_icon_slug,
            "model_icon_url": context.model_icon_url,
            "provider_icon_slug": context.provider_icon_slug,
            "provider_icon_url": context.provider_icon_url,
            "message_id": context.message_id,
        }

        # Fetch user's active sub-agents and model preferences
        sub_agents, _ = await _fetch_user_sub_agents(context)
        user_model_prefs = await _fetch_user_model_preferences(context)

        impl_task = plan.task_description
        result = await run_and_settle(
            context, model, context.chat_id or "",
            execute_coding_agent(
                user_id=context.user_id,
                chat_id=workspace_chat_id,
                task=impl_task,
                model=model,
                api_key=api_key,
                auth_token=context.auth_token,
                max_iterations=50,
                conversation_id=context.conversation_id,
                model_metadata=model_metadata,
                mode="implement",
                plan_id=str(plan.id),
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
                budget_usd=budget_usd,
            ),
        )

        # Store full result on context so heartbeat loop can enrich SSE data
        context.last_coding_agent_result = result

        if result.get("result", {}).get("quota_exceeded"):
            plan.status = AgentPlan.Status.FAILED
            await sync_to_async(plan.save)(update_fields=["status", "updated_at"])
            return quota_exceeded_error(budget_usd)

        # Update plan status
        plan.status = AgentPlan.Status.COMPLETED if result.get("success") else AgentPlan.Status.FAILED
        await sync_to_async(plan.save)(update_fields=["status", "updated_at"])

        # --- Push branch to GitHub after agent completes ---
        if result.get("success") and github_conn and github_conn.access_token:
            try:
                push_resp = await client.post(
                    f"{orchestrator_url}/fs/bash",
                    json={
                        "user_id": context.user_id,
                        "conversation_id": context.conversation_id,
                        "chat_id": workspace_chat_id,
                        "sync_mode": True,
                        "command": f"cd {repo_path} && git push -u origin {branch_name}",
                        "timeout": 120,
                    },
                    headers=headers,
                    timeout=150.0,
                )
                push_data = push_resp.json() if push_resp.status_code == 200 else {}
                if not push_data.get("success"):
                    logger.warning(f"[implement_plan] Push failed: {push_data.get('output', '')[:200]}")
            except Exception as push_err:
                logger.warning(f"[implement_plan] Push error: {push_err}")

        impl_cost = result.get("result", {}).get("total_cost_usd", 0.0)

        if result.get("success"):
            job_result = result.get("result", {})
            return json.dumps({
                "success": True,
                "data": {
                    "plan_id": str(plan.id),
                    "plan_status": plan.status,
                    "branch_name": branch_name,
                    "job_id": result.get("job_id"),
                    "summary": job_result.get("summary", "Implementation completed"),
                    "files_modified": job_result.get("files_modified", []),
                    "files_created": job_result.get("files_created", []),
                },
                "cost_usd": impl_cost,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Implementation failed"),
                "data": {"plan_id": str(plan.id), "plan_status": plan.status, "branch_name": branch_name},
                "cost_usd": impl_cost,
            })

    except Exception as e:
        logger.error(f"[implement_plan] Error: {e}", exc_info=True)
        partial_cost = 0.0
        try:
            if 'result' in dir() and isinstance(result, dict):
                partial_cost = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)
        except Exception:
            pass
        return json.dumps({"success": False, "error": str(e), "cost_usd": partial_cost})


@tool
async def edit_plan(
    plan_id: str,
    instructions: str,
) -> str:
    """Edit an existing implementation plan.

    Re-runs the coding agent in plan mode with existing plan content
    and edit instructions, then updates the plan in the database.

    Args:
        plan_id: UUID of the plan to edit.
        instructions: What to change about the plan.
    """
    context = _get_context()
    if not context:
        return json.dumps({"success": False, "error": "File tools context not initialized"})
    if not plan_id:
        return json.dumps({"success": False, "error": "plan_id is required"})
    if not instructions:
        return json.dumps({"success": False, "error": "instructions are required"})

    gate_denial, budget_usd = await check_code_session_budget(context)
    if gate_denial is not None:
        return gate_denial

    logger.info(f"[edit_plan] Starting, plan_id: {plan_id}")

    try:
        from .services import execute_coding_agent
        from code_sessions.models import AgentPlan
        from code_sessions.services.plan_service import update_plan_from_content
        from asgiref.sync import sync_to_async

        # Resolve the correct workspace chat_id (may differ from active chat)
        workspace_chat_id = await _resolve_workspace_chat_id(context)
        await _ensure_repo_in_sandbox(context, workspace_chat_id)

        # Load existing plan
        try:
            plan = await sync_to_async(AgentPlan.objects.get)(
                id=plan_id, conversation__user_id=context.user_id
            )
        except AgentPlan.DoesNotExist:
            return json.dumps({"success": False, "error": f"Plan {plan_id} not found"})

        api_key = context.api_key
        if not api_key:
            return json.dumps({"success": False, "error": "No OpenRouter API key available"})

        model = context.model_id or "anthropic/claude-sonnet-4"
        model_metadata = {
            "model_name": context.model_name,
            "model_id": context.model_id,
            "provider": context.provider,
            "model_icon_slug": context.model_icon_slug,
            "model_icon_url": context.model_icon_url,
            "provider_icon_slug": context.provider_icon_slug,
            "provider_icon_url": context.provider_icon_url,
            "message_id": context.message_id,
        }

        task = (
            f"Review and edit the following implementation plan.\n\n"
            f"**Edit Instructions:** {instructions}\n\n"
            f"**Current Plan:**\n\n{plan.plan_content}\n\n"
            f"Apply the requested changes and save the updated plan using ExitPlanMode. "
            f"Use the same structured format (# Implementation Plan: ..., ## Summary, "
            f"### Step N: ..., **Files:** etc). "
            f"You may re-explore the codebase if needed to improve the plan."
        )

        # Fetch user's active sub-agents and model preferences
        sub_agents, sub_agent_descs = await _fetch_user_sub_agents(context)
        user_model_prefs = await _fetch_user_model_preferences(context)
        if sub_agent_descs:
            agent_list = ", ".join(
                f"{a['name']} ({a['description'][:80]})" for a in sub_agent_descs
            )
            task = f"{task}\n\nAvailable sub-agents you can delegate to via the Task tool: {agent_list}"

        result = await run_and_settle(
            context, model, context.chat_id or "",
            execute_coding_agent(
                user_id=context.user_id,
                chat_id=workspace_chat_id,
                task=task,
                model=model,
                api_key=api_key,
                auth_token=context.auth_token,
                allowed_tools=["Read", "Glob", "Grep", "Bash"],
                max_iterations=30,
                conversation_id=context.conversation_id,
                model_metadata=model_metadata,
                mode="plan",
                sub_agents=sub_agents,
                user_model_preferences=user_model_prefs,
                budget_usd=budget_usd,
            ),
        )
        context.last_coding_agent_result = result

        if result.get("result", {}).get("quota_exceeded"):
            return quota_exceeded_error(budget_usd)

        if not result.get("success"):
            return json.dumps({"success": False, "error": result.get("error", "Plan editing failed")})

        plan_content = result.get("result", {}).get("plan_content", "")
        if not plan_content:
            plan_content = result.get("plan_content", "")
        if not plan_content:
            plan_content = result.get("result", {}).get("summary", "")

        if not plan_content:
            return json.dumps({"success": False, "error": "Agent completed but no updated plan was produced."})

        plan = await sync_to_async(update_plan_from_content)(plan, plan_content)

        edit_cost = result.get("result", {}).get("total_cost_usd", 0.0)

        return json.dumps({
            "success": True,
            "data": {
                "plan_id": str(plan.id),
                "plan_title": plan.title,
                "total_steps": plan.total_steps,
                "status": plan.status,
            },
            "cost_usd": edit_cost,
        })

    except Exception as e:
        logger.error(f"[edit_plan] Error: {e}", exc_info=True)
        partial_cost = 0.0
        try:
            if 'result' in dir() and isinstance(result, dict):
                partial_cost = result.get("result", {}).get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)
        except Exception:
            pass
        return json.dumps({"success": False, "error": str(e), "cost_usd": partial_cost})


# Plan tools (separate export for feature-flag gating with coding agent)
PLAN_TOOLS = [plan_implementation, implement_plan, edit_plan]

