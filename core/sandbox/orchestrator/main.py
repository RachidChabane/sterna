"""
Orchestrator Service

Central orchestration layer that coordinates:
- Sandbox lifecycle management
- File system operations
- Artifact storage and retrieval
"""

from fastapi import FastAPI, HTTPException, status, Depends, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
import docker
import logging
from typing import Dict, Any, List, Optional
import re
import socket as _socket
from datetime import datetime
import os
import asyncio
import httpx

from sandbox_executor import SandboxExecutor, ARTIFACTS_DIR
from auth import CurrentUser, verify_jwt_token_from_query, generate_preview_token, verify_preview_token, PREVIEW_TOKEN_EXPIRY
from security_monitor import security_monitor
from mcp_endpoints import router as mcp_router, set_sandbox_executor
from workspace_client import get_workspace_client

# ArtifactStorage is optional - only initialize if S3/MinIO is configured
artifact_storage = None
try:
    # Only import and initialize if S3_ENDPOINT_URL is explicitly set
    if os.getenv('S3_ENDPOINT_URL') or os.getenv('R2_ENDPOINT'):
        from artifact_storage import ArtifactStorage
        artifact_storage = ArtifactStorage()
        logging.getLogger(__name__).info("ArtifactStorage initialized")
    else:
        logging.getLogger(__name__).info("ArtifactStorage disabled - no S3/R2 endpoint configured")
except Exception as e:
    logging.getLogger(__name__).warning(f"ArtifactStorage initialization failed: {e}")

from _observability import (  # noqa: E402,F401
    RequestIDMiddleware,
    current_request_id,
    init_observability,
)

init_observability(
    service="orchestrator",
    app_loggers=(
        "main", "sandbox_executor", "coding_agent_runner",
        "mcp_endpoints", "mcp_manager", "mcp_tools",
        "workspace_client", "file_tools", "tool_executor",
        "security_monitor", "artifact_storage",
        "excel_handler", "auth",
    ),
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sterna Orchestrator",
    description="Central orchestration service for sandbox operations",
    version="1.0.0"
)

# Configure CORS - SECURITY: Restrict to necessary origins, methods, and headers (CWE-942)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    # SECURITY: Only allow methods actually used by the API
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # SECURITY: Only allow headers needed for auth and content negotiation
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
    # SECURITY: Limit exposed headers
    expose_headers=["Content-Type", "Content-Length"],
    # SECURITY: Cache preflight for 10 minutes to reduce OPTIONS requests
    max_age=600,
)

# Read/mint X-Request-ID and expose it to the log filters (cross-service
# correlation with Django / api-gateway).
app.add_middleware(RequestIDMiddleware)

# Initialize Docker client (optional - may not be available in Kubernetes)
docker_client = None
try:
    docker_client = docker.from_env()
    logger.info("Docker client initialized successfully")
except Exception:
    logger.warning("orchestrator.docker_unavailable", exc_info=True)

# Sandbox configuration from environment
SANDBOX_IDLE_TIMEOUT = int(os.getenv("SANDBOX_IDLE_TIMEOUT", "300"))  # 5 minutes (reduced from 1 hour)
SANDBOX_CLEANUP_INTERVAL = int(os.getenv("SANDBOX_CLEANUP_INTERVAL", "60"))  # Check every minute

# Initialize sandbox executor
sandbox_executor = None
if docker_client:
    sandbox_executor = SandboxExecutor(
        docker_client=docker_client,
        inactivity_timeout=SANDBOX_IDLE_TIMEOUT,
        cleanup_interval=SANDBOX_CLEANUP_INTERVAL
    )
    logger.info(f"Sandbox executor initialized: timeout={SANDBOX_IDLE_TIMEOUT}s, cleanup_interval={SANDBOX_CLEANUP_INTERVAL}s")
else:
    logger.info("Sandbox executor disabled - Docker not available")

# Set sandbox executor for MCP endpoints (if available)
# MCP servers now run as child processes inside the user's sandbox container,
# managed by the MCP Gateway. This avoids creating separate containers per server.
if sandbox_executor:
    set_sandbox_executor(sandbox_executor)

# Include MCP router
app.include_router(mcp_router)


@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    # Directory already created before app.mount() - just log
    logger.info(f"Artifacts directory: {ARTIFACTS_DIR}")
    logger.info("Orchestrator service started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    logger.info("Shutting down orchestrator service")
    # Log final security summary
    logger.info(f"Total security events recorded: {len(security_monitor.events)}")


# --- Service Availability Dependencies ---

def require_sandbox_executor():
    """Dependency that ensures sandbox_executor is available."""
    if sandbox_executor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox executor not available. Docker is required for sandbox operations."
        )
    return sandbox_executor

def require_artifact_storage():
    """Dependency that ensures artifact_storage is available."""
    if artifact_storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Artifact storage not available. S3/MinIO endpoint not configured."
        )
    return artifact_storage


# --- Request/Response Models ---

class FSListRequest(BaseModel):
    """Request to list files in workspace."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    path: str = "/workspace"
    depth: int = 1  # How deep to recurse (1-5)


class FSReadRequest(BaseModel):
    """Request to read a file."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    path: str
    # New parameters for partial file reading
    max_lines: Optional[int] = None  # Maximum lines to return
    from_end: bool = False  # If true with max_lines, read from end
    start_line: Optional[int] = None  # Start line (1-indexed)
    end_line: Optional[int] = None  # End line (1-indexed, inclusive)
    summary_only: bool = False  # Return only structure (functions, classes)


class FSSearchRequest(BaseModel):
    """Request to search for patterns in files."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    pattern: str  # Regex pattern to search for
    path: str = "."  # Directory or file to search in
    include: Optional[str] = None  # Glob pattern to filter files (e.g., '*.py')
    context_lines: int = 0  # Lines of context around matches
    max_results: int = 50  # Maximum number of matches
    ignore_case: bool = False  # Case-insensitive search


class FSWriteRequest(BaseModel):
    """Request to write a file."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    path: str
    content: str
    ai_metadata: Optional[Dict[str, Any]] = None
    is_base64: bool = False  # If True, content will be decoded from base64
    # Versioning metadata
    source_type: Optional[str] = None  # file_tool, user_edit, coding_agent, etc.
    source_message_id: Optional[str] = None
    source_job_id: Optional[str] = None
    source_tool_name: Optional[str] = None


class FSEditRequest(BaseModel):
    """Request to edit a file by replacing specific content."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    path: str
    old_content: str
    new_content: str
    # Versioning metadata
    source_type: Optional[str] = None
    source_message_id: Optional[str] = None
    source_job_id: Optional[str] = None
    source_tool_name: Optional[str] = None


class FSDeleteRequest(BaseModel):
    """Request to delete a file or folder."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    path: str
    # Versioning metadata
    source_type: Optional[str] = None
    source_message_id: Optional[str] = None
    source_job_id: Optional[str] = None


class FSDeleteWorkspaceRequest(BaseModel):
    """Request to delete entire workspace for a chat or conversation."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None  # If None, deletes all workspaces for conversation
    sync_mode: bool = True
    scope: str = "chat"  # "chat" or "conversation"


class FSRenameRequest(BaseModel):
    """Request to rename a file or folder."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    old_path: str
    new_path: str


class FSMkdirRequest(BaseModel):
    """Request to create a directory."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    path: str
    ai_metadata: Optional[Dict[str, Any]] = None


class FSMetadataRequest(BaseModel):
    """Request to get file metadata."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    path: str


class FSBashRequest(BaseModel):
    """Request to execute a bash command."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    command: str
    timeout: int = 120


class WorkspaceSaveRequest(BaseModel):
    """Request to save workspace to persistent storage."""
    user_id: str
    chat_id: str


class WorkspaceRestoreRequest(BaseModel):
    """Request to restore workspace from persistent storage."""
    user_id: str
    chat_id: str
    force: bool = False  # Skip "already has files" check (e.g. after re-clone)


class WorkspaceSyncResponse(BaseModel):
    """Response from workspace sync operation."""
    success: bool
    files_synced: int = 0
    bytes_synced: int = 0
    files_deleted: int = 0
    errors: List[str] = []
    duration_ms: int = 0
    was_restored: bool = True  # True if files were actually restored from storage


class EnsureRepoRequest(BaseModel):
    """Request to check if a git repo exists in the sandbox workspace."""
    user_id: str
    chat_id: str


class EnsureRepoResponse(BaseModel):
    """Response from ensure-repo check."""
    needs_clone: bool
    repo_exists: bool
    has_git: bool


class ReconcileGitRequest(BaseModel):
    """Request to reconcile git state after re-clone + restore."""
    user_id: str
    chat_id: str
    target_branch: str
    default_branch: str = "main"


class ReconcileGitResponse(BaseModel):
    """Response from git reconciliation."""
    success: bool
    branch: str = ""
    commit_sha: str = ""
    committed: bool = False
    error: str = ""


class WorkspaceStatsRequest(BaseModel):
    """Request to get workspace resource usage stats."""
    user_id: str
    chat_id: str


class WorkspaceStatsResponse(BaseModel):
    """Response with workspace storage and memory usage."""
    success: bool
    storage_used_mb: float = 0
    storage_total_mb: float = 0
    storage_percent: float = 0
    memory_used_mb: float = 0
    memory_total_mb: float = 0
    memory_percent: float = 0
    error: str = ""


class ExcelReadRequest(BaseModel):
    """Request to read an Excel file with formulas."""
    user_id: str
    conversation_id: str
    chat_id: str
    sync_mode: bool = True
    path: str
    sheet_index: int = 0


class ExcelUpdateCellRequest(BaseModel):
    """Request to update an Excel cell."""
    user_id: str
    conversation_id: str
    chat_id: str
    sync_mode: bool = True
    path: str
    sheet_index: int
    row: int
    col: int
    value: Optional[str] = None
    formula: Optional[str] = None


class ExcelCellUpdate(BaseModel):
    """Single cell update for batch operations."""
    row: int
    col: int
    value: Optional[str] = None
    formula: Optional[str] = None


class ExcelBatchUpdateRequest(BaseModel):
    """Request to update multiple Excel cells in batch (much faster)."""
    user_id: str
    conversation_id: str
    chat_id: str
    sync_mode: bool = True
    path: str
    sheet_index: int
    updates: list[ExcelCellUpdate]


class ExecuteCodeRequest(BaseModel):
    """Request to execute code directly (for Code Editor)."""
    code: str
    language: str = Field(..., description="Language: python, javascript, or bash")
    user_id: str
    conversation_id: str = Field(..., description="Conversation ID for sandbox isolation")
    chat_id: Optional[str] = Field(None, description="Chat ID (used in independent mode)")
    sync_mode: bool = Field(True, description="Whether conversation is in sync mode")
    project_id: str = "default"
    timeout: int = Field(30, description="Execution timeout in seconds")
    execution_id: Optional[str] = Field(None, description="Unique ID for this execution (for cancellation)")
    uploaded_files: Optional[List[Dict[str, str]]] = Field(None, description="Files to copy into workspace before execution. Format: [{filename, content_base64}]")


class ExecuteCodeResponse(BaseModel):
    """Response from code execution."""
    output: str
    error: Optional[str] = None
    exit_code: int
    execution_time: float
    artifacts: List[Dict[str, Any]] = []


# --- Process Management Models ---

# SECURITY: Allowlist for safe command characters (replaces blocklist approach)
# Allows: letters, digits, spaces, tabs, hyphens, dots, slashes, equals, colons, commas, @, underscores, quotes
_ALLOWED_COMMAND_PATTERN = re.compile(r'^[a-zA-Z0-9 \t\-\./=:,@_"\']+$')
MAX_PROCESSES_PER_USER = 3

class StartProcessRequest(BaseModel):
    """Request to start a background process in sandbox."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    command: str = Field(..., description="Command to run (e.g. 'npm run dev')")
    port: int = Field(..., ge=3000, le=9999, description="Port the process listens on (3000-9999)")
    cwd: Optional[str] = Field(None, description="Working directory relative to workspace (e.g. 'spark-app-xxx')")

    @field_validator('command')
    @classmethod
    def validate_command(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Command cannot be empty')
        if len(v) > 500:
            raise ValueError('Command too long (max 500 chars)')
        if any(c in v for c in '\n\r\x00'):
            raise ValueError('Command contains disallowed control characters')
        if not _ALLOWED_COMMAND_PATTERN.match(v):
            raise ValueError('Command contains disallowed characters. Only letters, digits, spaces, hyphens, dots, slashes, equals, colons, commas, @, underscores, and quotes are allowed.')
        return v

    @field_validator('cwd')
    @classmethod
    def validate_cwd(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if '..' in v:
            raise ValueError('cwd must not contain ".."')
        if v.startswith('/') and not v.startswith('/workspace'):
            raise ValueError('cwd must be relative or under /workspace')
        if any(c in v for c in '\n\r\x00'):
            raise ValueError('cwd contains disallowed control characters')
        return v


class StopProcessRequest(BaseModel):
    """Request to stop a background process."""
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    pid: int


# In-memory port registry: {sandbox_id: [{pid, port, command, started_at}]}
_port_registry: Dict[str, List[dict]] = {}


class CodingAgentExecuteRequest(BaseModel):
    """Request to execute Coding Agent autonomous agent."""
    user_id: str
    conversation_id: str
    chat_id: str
    task: str = Field(..., description="Task description for Coding Agent to execute")
    model: str = Field(..., description="OpenRouter model ID to use")
    allowed_tools: List[str] = Field(
        default=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        description="Tools Coding Agent is allowed to use"
    )
    max_iterations: int = Field(default=20, ge=1, le=100, description="Maximum agent iterations")
    openrouter_api_key: str = Field(..., description="OpenRouter API key for the agent")
    model_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Model metadata for file attribution (model_name, model_id, provider, icons)"
    )
    mcp_servers: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="MCP server configurations to pass to Coding Agent CLI via --mcp-config"
    )
    mode: str = Field(
        default="auto",
        description="Agent mode: 'plan' (create plan), 'implement' (execute plan), or 'auto' (default)"
    )
    plan_id: Optional[str] = Field(default=None, description="Plan ID to implement (required when mode='implement')")
    sub_agents: Optional[List[Dict[str, Any]]] = Field(default=None, description="Sub-agent definitions as {name, markdown} dicts")
    user_model_preferences: Optional[Dict[str, str]] = Field(default=None, description="User's tier→model mapping: {fast_model_id, balanced_model_id, powerful_model_id}")
    budget_usd: Optional[float] = None  # Quota ceiling; the job stops once its running cost crosses it


class CodingAgentExecuteResponse(BaseModel):
    """Response from Coding Agent execution."""
    success: bool
    job_id: Optional[str] = None
    summary: Optional[str] = None
    files_modified: List[str] = []
    files_created: List[str] = []
    steps: List[Dict[str, Any]] = []
    error: Optional[str] = None
    duration_ms: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    quota_exceeded: bool = False


class CodingAgentProgressRequest(BaseModel):
    """Request for Coding Agent progress."""
    user_id: str
    chat_id: str
    job_id: Optional[str] = None  # Optional - will find most recent job if not provided


class CodingAgentProgressResponse(BaseModel):
    """Response with real-time progress data."""
    found: bool
    step_count: int = 0
    total_steps: int = 0
    completed: bool = False
    exit_code: Optional[int] = None
    files_created: List[str] = []
    files_modified: List[str] = []
    files_read: List[str] = []
    files_deleted: List[str] = []
    steps: List[Dict[str, Any]] = []  # All steps with full content
    error: Optional[str] = None
    summary: Optional[str] = None
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    pending_question: Optional[Dict[str, Any]] = None


# --- Ask-User MCP relay state ---
# Pending questions from coding agent MCP tool, keyed by "{user_id}:{chat_id}"
_pending_questions: Dict[str, Dict[str, Any]] = {}
ASK_USER_TIMEOUT = int(os.getenv("ASK_USER_TIMEOUT", "300"))


class AskUserRequest(BaseModel):
    """Request from MCP relay script to ask a question."""
    user_id: str
    chat_id: str
    job_token: str
    question: str
    options: Optional[List[Dict[str, str]]] = None


class AskUserResponse(BaseModel):
    """Response with user's answer."""
    answer: str
    timed_out: bool = False


class SubmitAnswerRequest(BaseModel):
    """Request from Django to submit an answer."""
    user_id: str
    chat_id: str
    answer: str


# --- Helper Functions ---

# --- API Endpoints ---

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "orchestrator",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "docker": docker_client is not None,
            "sandbox_executor": sandbox_executor is not None,
            "artifact_storage": artifact_storage is not None,
        }
    }


@app.post("/execute", response_model=ExecuteCodeResponse)
async def execute_code(request: ExecuteCodeRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """
    Execute code in isolated sandbox container.

    Uses ephemeral sandbox containers with intelligent lifecycle:
    - Creates sandbox on first execution
    - Reuses sandbox for same context (conversation/chat)
    - Destroys sandbox after 5 minutes of inactivity

    Requires JWT authentication via Authorization header.
    """
    # Verify that the authenticated user matches the request user_id
    if str(authenticated_user_id) != str(request.user_id):
        logger.warning(
            "orchestrator.user_id_mismatch",
            extra={
                "authenticated_user_id": str(authenticated_user_id),
                "requested_user_id": str(request.user_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only execute code for your own user account"
        )

    logger.info(f"Executing code: user={request.user_id}, conversation={request.conversation_id}, "
                f"chat={request.chat_id}, sync={request.sync_mode}, language={request.language}")

    # Log command for security monitoring
    project_id = request.chat_id or request.conversation_id
    command_preview = request.code[:200] if len(request.code) > 200 else request.code
    security_monitor.log_command(
        user_id=request.user_id,
        project_id=project_id,
        command=f"[{request.language}] {command_preview}",
        source="api"
    )

    try:
        # Note: Uploaded files are now copied to workspace immediately upon message receipt,
        # not during execute_code. The files should already be in the workspace.

        # Execute code in sandbox (run in thread to not block event loop)
        output, error, exit_code, execution_time, artifacts = await asyncio.to_thread(
            sandbox_executor.execute_code,
            code=request.code,
            language=request.language,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            chat_id=request.chat_id,
            sync_mode=request.sync_mode,
            timeout=request.timeout,
            execution_id=request.execution_id
        )

        return ExecuteCodeResponse(
            output=output,
            error=error,
            exit_code=exit_code,
            execution_time=execution_time,
            artifacts=artifacts
        )

    except Exception as e:
        logger.error(
            "orchestrator.execute_failed",
            extra={
                "user_id": str(request.user_id),
                "conversation_id": str(request.conversation_id),
                "chat_id": str(request.chat_id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/cancel/{execution_id}")
async def cancel_execution(execution_id: str, authenticated_user_id: str = Depends(CurrentUser)):
    """
    Cancel a running code execution.

    Requires JWT authentication via Authorization header.
    """
    logger.info(f"Cancelling execution: execution_id={execution_id}, user={authenticated_user_id}")

    try:
        cancelled = sandbox_executor.cancel_execution(execution_id)

        if cancelled:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Execution cancelled successfully", "execution_id": execution_id}
            )
        else:
            # Execution not in active list - likely already completed/timed out
            # This is not an error from user perspective - the execution is not running
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Execution already completed or timed out", "execution_id": execution_id}
            )

    except Exception as e:
        logger.error(
            "orchestrator.cancel_failed",
            extra={"execution_id": execution_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/fs/list")
async def fs_list(request: FSListRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """List files in workspace directory."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.list_files,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        depth=request.depth
    )
    return result


@app.post("/fs/read")
async def fs_read(request: FSReadRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Read file content with optional partial reading."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.read_file,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        max_lines=request.max_lines,
        from_end=request.from_end,
        start_line=request.start_line,
        end_line=request.end_line,
        summary_only=request.summary_only,
    )
    return result


@app.post("/fs/search")
async def fs_search(request: FSSearchRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Search for patterns in files using regex."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.search_code,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        pattern=request.pattern,
        path=request.path,
        include=request.include,
        context_lines=request.context_lines,
        max_results=request.max_results,
        ignore_case=request.ignore_case,
    )
    return result


@app.post("/fs/write")
async def fs_write(request: FSWriteRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Write file content."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    # SECURITY AUDIT: Log file write operations
    content_size = len(request.content) if request.content else 0
    logger.info(
        "orchestrator.fs_write",
        extra={
            "user_id": str(request.user_id),
            "chat_id": str(request.chat_id),
            "path": request.path,
            "size": content_size,
            "is_base64": request.is_base64,
        },
    )

    # For base64 content (binary files), pass as-is to write_file
    # write_file will handle the base64 decoding
    content = request.content

    result = await asyncio.to_thread(
        sandbox_executor.write_file,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        content=content,
        model_metadata=request.ai_metadata,
        is_base64=request.is_base64
    )

    # Create version if write was successful and versioning info provided
    if result.get("success") and request.source_type and request.chat_id:
        try:
            # Get content as bytes for versioning
            if request.is_base64:
                import base64
                version_content = base64.b64decode(content)
            else:
                version_content = content.encode('utf-8') if content else b''

            # Normalize path to relative (strip /workspace/ prefix)
            version_path = request.path
            if version_path.startswith('/workspace/'):
                version_path = version_path[len('/workspace/'):]

            workspace_client = get_workspace_client()
            await asyncio.to_thread(
                workspace_client.create_version,
                user_id=request.user_id,
                chat_id=request.chat_id,
                path=version_path,
                content=version_content,
                source_type=request.source_type,
                source_message_id=request.source_message_id,
                source_job_id=request.source_job_id,
                source_tool_name=request.source_tool_name or 'Write',
            )
        except Exception:
            logger.warning(
                "orchestrator.fs_write_version_failed",
                extra={"path": request.path},
                exc_info=True,
            )

    return result


@app.post("/fs/edit")
async def fs_edit(request: FSEditRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Edit file content by replacing specific text."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.edit_file,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        old_content=request.old_content,
        new_content=request.new_content
    )

    # Create version if edit was successful and versioning info provided
    if result.get("success") and request.source_type and request.chat_id:
        try:
            # Read the edited file content for versioning
            read_result = await asyncio.to_thread(
                sandbox_executor.read_file,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                chat_id=request.chat_id,
                sync_mode=request.sync_mode,
                path=request.path,
            )
            if read_result.get("success"):
                version_content = read_result.get("content", "").encode('utf-8')

                # Normalize path
                version_path = request.path
                if version_path.startswith('/workspace/'):
                    version_path = version_path[len('/workspace/'):]

                workspace_client = get_workspace_client()
                await asyncio.to_thread(
                    workspace_client.create_version,
                    user_id=request.user_id,
                    chat_id=request.chat_id,
                    path=version_path,
                    content=version_content,
                    source_type=request.source_type,
                    source_message_id=request.source_message_id,
                    source_job_id=request.source_job_id,
                    source_tool_name=request.source_tool_name or 'Edit',
                )
        except Exception:
            logger.warning(
                "orchestrator.fs_edit_version_failed",
                extra={"path": request.path},
                exc_info=True,
            )

    return result


@app.post("/fs/delete")
async def fs_delete(request: FSDeleteRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Delete file or directory."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    # SECURITY AUDIT: Log file delete operations (sensitive)
    logger.info(
        "orchestrator.fs_delete",
        extra={
            "user_id": str(request.user_id),
            "chat_id": str(request.chat_id),
            "path": request.path,
        },
    )

    result = await asyncio.to_thread(
        sandbox_executor.delete_file,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path
    )

    # Create deletion tombstone version if delete was successful and versioning info provided
    if result.get("success") and request.source_type and request.chat_id:
        try:
            # Normalize path
            version_path = request.path
            if version_path.startswith('/workspace/'):
                version_path = version_path[len('/workspace/'):]

            workspace_client = get_workspace_client()
            await asyncio.to_thread(
                workspace_client.create_version,
                user_id=request.user_id,
                chat_id=request.chat_id,
                path=version_path,
                content=b'',  # Empty content for deletion
                source_type=request.source_type,
                source_message_id=request.source_message_id,
                source_job_id=request.source_job_id,
                is_deleted=True,
            )
        except Exception:
            logger.warning(
                "orchestrator.fs_delete_version_failed",
                extra={"path": request.path},
                exc_info=True,
            )

    return result


@app.post("/fs/delete-workspace")
async def fs_delete_workspace(request: FSDeleteWorkspaceRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Delete entire workspace for a chat or conversation."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own workspaces"
        )

    # SECURITY AUDIT: Log workspace deletion (highly sensitive)
    logger.info(
        "orchestrator.fs_delete_workspace",
        extra={
            "user_id": str(request.user_id),
            "conversation_id": str(request.conversation_id),
            "chat_id": str(request.chat_id),
            "scope": request.scope,
        },
    )

    # Choose appropriate deletion method based on scope
    if request.scope == "conversation":
        result = await asyncio.to_thread(
            sandbox_executor.delete_conversation_workspaces,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            sync_mode=request.sync_mode
        )
    else:  # scope == "chat"
        if not request.chat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="chat_id is required when scope is 'chat'"
            )
        result = await asyncio.to_thread(
            sandbox_executor.delete_chat_workspace,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            chat_id=request.chat_id,
            sync_mode=request.sync_mode
        )
    return result


@app.post("/fs/rename")
async def fs_rename(request: FSRenameRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Rename file or directory."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    # SECURITY AUDIT: Log file rename operations
    logger.info(
        "orchestrator.fs_rename",
        extra={
            "user_id": str(request.user_id),
            "chat_id": str(request.chat_id),
            "old_path": request.old_path,
            "new_path": request.new_path,
        },
    )

    result = await asyncio.to_thread(
        sandbox_executor.rename_file,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        old_path=request.old_path,
        new_path=request.new_path
    )
    return result


@app.post("/fs/mkdir")
async def fs_mkdir(request: FSMkdirRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Create directory."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.create_directory,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        model_metadata=request.ai_metadata
    )
    return result


@app.post("/fs/metadata")
async def fs_metadata(request: FSMetadataRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Get file metadata (creation/modification info)."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.get_file_metadata,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path
    )
    return result


@app.post("/fs/bash")
async def fs_bash(request: FSBashRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Execute a bash command in the sandbox."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only execute commands in your own sandbox"
        )

    try:
        output, error, exit_code, execution_time, artifacts = await asyncio.to_thread(
            sandbox_executor.execute_code,
            code=request.command,
            language="bash",
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            chat_id=request.chat_id,
            sync_mode=request.sync_mode,
            timeout=min(request.timeout, 300)  # Cap at 5 minutes
        )

        # Combine stdout and stderr
        full_output = output
        if error:
            full_output = f"{output}\n{error}" if output else error

        return {
            "success": exit_code == 0,
            "output": full_output.strip() if full_output else "(no output)",
            "exit_code": exit_code,
            "execution_time": round(execution_time, 2),
            "artifacts": artifacts,
            "error": f"Command failed with exit code {exit_code}" if exit_code != 0 else None
        }

    except Exception as e:
        logger.error("orchestrator.bash_failed", exc_info=True)
        return {
            "success": False,
            "output": "",
            "exit_code": 1,
            "execution_time": 0,
            "error": str(e)
        }


# --- Workspace Persistence Endpoints ---

@app.post("/workspace/save", response_model=WorkspaceSyncResponse)
async def workspace_save(
    request: WorkspaceSaveRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor)
):
    """
    Save workspace files to persistent storage.

    This saves all files in the chat's workspace to PostgreSQL/R2,
    allowing them to persist after the container is destroyed.
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only save your own workspace"
        )

    try:
        # Get or create sandbox
        sandbox_id = executor._generate_sandbox_id(
            request.user_id, request.chat_id, request.chat_id, True
        )

        # Check if sandbox exists
        if sandbox_id not in executor.sandboxes:
            return WorkspaceSyncResponse(
                success=True,
                files_synced=0,
                bytes_synced=0,
                errors=["No active sandbox to save"]
            )

        container = executor.sandboxes[sandbox_id]['container']
        workspace_path = f"/workspace/chat-{request.chat_id}"

        # Use workspace client to save
        client = get_workspace_client()
        result = await asyncio.to_thread(
            client.save_workspace,
            container=container,
            user_id=request.user_id,
            chat_id=request.chat_id,
            workspace_path=workspace_path
        )

        return WorkspaceSyncResponse(
            success=result.success,
            files_synced=result.files_synced,
            bytes_synced=result.bytes_synced,
            files_deleted=result.files_deleted,
            errors=result.errors or [],
            duration_ms=result.duration_ms
        )

    except Exception as e:
        logger.error("orchestrator.workspace_save_failed", exc_info=True)
        return WorkspaceSyncResponse(
            success=False,
            errors=[str(e)]
        )


def _check_chat_directory_has_files(container, workspace_path: str) -> bool:
    """
    Check if the chat's workspace directory exists and has files.

    This is used to skip restore when files are already present in the container,
    avoiding unnecessary API calls and misleading "Restored x files" notifications.
    """
    try:
        # Check if directory exists AND has files (non-hidden files only, exclude marker files)
        # Using: test -d <path> && find <path> -maxdepth 1 -type f ! -name ".*" | head -1
        result = container.exec_run([
            "sh", "-c",
            f"test -d '{workspace_path}' && find '{workspace_path}' -maxdepth 2 -type f ! -name '.*' 2>/dev/null | head -1"
        ])
        # exit_code 0 means directory exists, output non-empty means has files
        stdout = result.output if result.output else b""
        return result.exit_code == 0 and len(stdout.strip()) > 0
    except Exception as e:
        logger.debug(f"Error checking directory {workspace_path}: {e}")
        return False


@app.post("/workspace/restore", response_model=WorkspaceSyncResponse)
async def workspace_restore(
    request: WorkspaceRestoreRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor)
):
    """
    Restore workspace files from persistent storage.

    This restores previously saved files to the sandbox container,
    allowing users to continue where they left off.

    Optimization: If the chat's workspace directory already has files,
    the restore is skipped (files are still present from previous session).
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only restore your own workspace"
        )

    try:
        # Get or create sandbox (this creates it if needed)
        sandbox_id = executor._generate_sandbox_id(
            request.user_id, request.chat_id, request.chat_id, True
        )
        container = executor._get_or_create_sandbox(sandbox_id)

        workspace_path = f"/workspace/chat-{request.chat_id}"

        # Check if chat directory already has files (container wasn't destroyed)
        # If files exist, skip restore - they're still in the container filesystem
        # force=True bypasses this check (used after re-cloning to overlay agent changes)
        if not request.force:
            has_files = await asyncio.to_thread(
                _check_chat_directory_has_files,
                container,
                workspace_path
            )

            if has_files:
                logger.info(f"Skipping restore for {workspace_path} - files already present in container")
                return WorkspaceSyncResponse(
                    success=True,
                    files_synced=0,
                    bytes_synced=0,
                    was_restored=False,  # Files were NOT restored from storage
                    duration_ms=0
                )

        # Directory doesn't exist or is empty - do actual restore from storage
        client = get_workspace_client()
        result = await asyncio.to_thread(
            client.restore_workspace,
            container=container,
            user_id=request.user_id,
            chat_id=request.chat_id,
            workspace_path=workspace_path
        )

        return WorkspaceSyncResponse(
            success=result.success,
            files_synced=result.files_synced,
            bytes_synced=result.bytes_synced,
            errors=result.errors or [],
            duration_ms=result.duration_ms,
            was_restored=True  # Files were actually restored from storage
        )

    except Exception as e:
        logger.error("orchestrator.workspace_restore_failed", exc_info=True)
        return WorkspaceSyncResponse(
            success=False,
            errors=[str(e)],
            was_restored=False
        )


@app.post("/workspace/ensure-repo", response_model=EnsureRepoResponse)
async def workspace_ensure_repo(
    request: EnsureRepoRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor)
):
    """Check if a git repo exists in the sandbox workspace.

    Returns whether the repo needs to be re-cloned (e.g. after container recycle).
    The actual cloning is done by the Django backend which has DB access.
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only check your own workspace"
        )

    try:
        sandbox_id = executor._generate_sandbox_id(
            request.user_id, request.chat_id, request.chat_id, True
        )
        container = executor._get_or_create_sandbox(sandbox_id)

        repo_path = f"/workspace/chat-{request.chat_id}/repo"

        # Check if repo directory and .git exist
        result = await asyncio.to_thread(
            container.exec_run,
            ["sh", "-c", f"test -d '{repo_path}' && echo REPO_EXISTS || echo REPO_MISSING; test -d '{repo_path}/.git' && echo GIT_EXISTS || echo GIT_MISSING"]
        )
        output = (result.output or b"").decode().strip()

        repo_exists = "REPO_EXISTS" in output
        has_git = "GIT_EXISTS" in output
        needs_clone = not has_git

        return EnsureRepoResponse(
            needs_clone=needs_clone,
            repo_exists=repo_exists,
            has_git=has_git,
        )
    except Exception:
        logger.error("orchestrator.ensure_repo_failed", exc_info=True)
        # If we can't check, assume it needs cloning
        return EnsureRepoResponse(
            needs_clone=True,
            repo_exists=False,
            has_git=False,
        )


@app.post("/workspace/reconcile-git", response_model=ReconcileGitResponse)
async def workspace_reconcile_git(
    request: ReconcileGitRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor)
):
    """Reconcile git state after re-clone + versioned file restore.

    After a container recycle, the repo is re-cloned (base state) and versioned
    files are overlaid on top. This leaves git in an inconsistent state:
    - Agent's local commits are lost
    - current_branch may not exist in the fresh clone
    - All agent changes show as uncommitted modifications

    This endpoint creates the target branch (if needed), stages all changes,
    and creates a restoration commit for a clean working tree.
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only reconcile your own workspace"
        )

    try:
        sandbox_id = executor._generate_sandbox_id(
            request.user_id, request.chat_id, request.chat_id, True
        )
        container = executor._get_or_create_sandbox(sandbox_id)

        repo_path = f"/workspace/chat-{request.chat_id}/repo"
        target_branch = request.target_branch

        # Run reconciliation as a single bash script
        reconcile_script = f"""
cd '{repo_path}' || exit 1

# Configure git for commits
git config user.email "agent@example.com"
git config user.name "Sterna Agent"

# Get current branch
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)

# Create and switch to target branch if different from current
TARGET_BRANCH='{target_branch}'
if [ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]; then
    git checkout -b "$TARGET_BRANCH" 2>/dev/null || git checkout "$TARGET_BRANCH" 2>/dev/null || true
fi

FINAL_BRANCH=$(git branch --show-current 2>/dev/null)

# Check if there are any changes to commit
if git diff --quiet HEAD 2>/dev/null && git diff --cached --quiet HEAD 2>/dev/null && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "RECONCILE_RESULT:no_changes:$FINAL_BRANCH:"
    exit 0
fi

# Stage all changes (modified, new, deleted)
git add -A

# Create restoration commit
git commit -m "chore: workspace restoration - reconcile agent changes

Files restored from version store after container recycle.
Previous commits were lost due to ephemeral workspace." 2>/dev/null

# Get new HEAD sha
NEW_SHA=$(git rev-parse HEAD 2>/dev/null)

echo "RECONCILE_RESULT:committed:$FINAL_BRANCH:$NEW_SHA"
"""

        result = await asyncio.to_thread(
            container.exec_run,
            ["sh", "-c", reconcile_script]
        )
        output = (result.output or b"").decode().strip()
        logger.info(f"Git reconciliation output: {output}")

        # Parse result
        for line in output.splitlines():
            if line.startswith("RECONCILE_RESULT:"):
                parts = line.split(":")
                status_str = parts[1] if len(parts) > 1 else ""
                branch = parts[2] if len(parts) > 2 else ""
                sha = parts[3] if len(parts) > 3 else ""

                return ReconcileGitResponse(
                    success=True,
                    branch=branch,
                    commit_sha=sha,
                    committed=(status_str == "committed"),
                )

        # If we didn't get a parseable result, still report what happened
        return ReconcileGitResponse(
            success=result.exit_code == 0,
            error=f"Unexpected output: {output[:200]}" if result.exit_code != 0 else "",
        )

    except Exception as e:
        logger.error("orchestrator.git_reconcile_failed", exc_info=True)
        return ReconcileGitResponse(
            success=False,
            error=str(e),
        )


@app.post("/workspace/stats", response_model=WorkspaceStatsResponse)
async def workspace_stats(
    request: WorkspaceStatsRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor)
):
    """Get workspace storage and memory usage for the sandbox container.

    Returns current storage (tmpfs /workspace) and RAM usage as percentages
    so the frontend can render progress bars.
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only check your own workspace"
        )

    try:
        sandbox_id = executor._generate_sandbox_id(
            request.user_id, request.chat_id, request.chat_id, True
        )
        container = executor._get_or_create_sandbox(sandbox_id)

        # Get storage usage (tmpfs /workspace) via df
        storage_script = "df -m /workspace 2>/dev/null | tail -1 | awk '{print $3,$2}'"
        storage_result = await asyncio.to_thread(
            container.exec_run, ["sh", "-c", storage_script]
        )
        storage_used_mb = 0.0
        storage_total_mb = float(os.getenv("SANDBOX_WORKSPACE_SIZE", "1024").rstrip("mMgG"))
        if storage_result.exit_code == 0:
            parts = (storage_result.output or b"").decode().strip().split()
            if len(parts) >= 2:
                try:
                    storage_used_mb = float(parts[0])
                    storage_total_mb = float(parts[1])
                except ValueError:
                    pass

        # Get memory usage from Docker container stats
        memory_used_mb = 0.0
        memory_total_mb = 512.0  # Default from SANDBOX_MEMORY_LIMIT
        try:
            stats = await asyncio.to_thread(container.stats, stream=False)
            mem_stats = stats.get("memory_stats", {})
            memory_used_mb = mem_stats.get("usage", 0) / (1024 * 1024)
            mem_limit = mem_stats.get("limit", 0)
            if mem_limit > 0:
                memory_total_mb = mem_limit / (1024 * 1024)
        except Exception as e:
            logger.debug(f"Failed to get container memory stats: {e}")

        storage_percent = (storage_used_mb / storage_total_mb * 100) if storage_total_mb > 0 else 0
        memory_percent = (memory_used_mb / memory_total_mb * 100) if memory_total_mb > 0 else 0

        return WorkspaceStatsResponse(
            success=True,
            storage_used_mb=round(storage_used_mb, 1),
            storage_total_mb=round(storage_total_mb, 1),
            storage_percent=round(storage_percent, 1),
            memory_used_mb=round(memory_used_mb, 1),
            memory_total_mb=round(memory_total_mb, 1),
            memory_percent=round(memory_percent, 1),
        )
    except Exception as e:
        logger.error("orchestrator.workspace_stats_failed", exc_info=True)
        return WorkspaceStatsResponse(
            success=False,
            error=str(e),
        )


@app.websocket("/ws/workspace/stats")
async def ws_workspace_stats(
    websocket: WebSocket,
    token: str = Query(default=""),
    user_id: str = Query(default=""),
    chat_id: str = Query(default=""),
):
    """WebSocket endpoint that streams workspace resource stats.

    Connect: ws://.../ws/workspace/stats?token=JWT&user_id=X&chat_id=Y
    Sends JSON frames every 5s with storage + memory usage.
    Client can send {"interval": N} to change the push interval (5-60s).
    """
    # Authenticate via query param JWT
    try:
        authenticated_user_id = verify_jwt_token_from_query(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    if str(authenticated_user_id) != str(user_id):
        await websocket.close(code=4003, reason="Forbidden")
        return

    executor = sandbox_executor
    if not executor:
        await websocket.close(code=4500, reason="Sandbox executor not available")
        return

    await websocket.accept()
    interval = 5  # seconds

    try:
        sandbox_id = executor._generate_sandbox_id(user_id, chat_id, chat_id, True)
        container = executor._get_or_create_sandbox(sandbox_id)

        while True:
            # Check for client messages (non-blocking)
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
                if isinstance(msg, dict) and "interval" in msg:
                    interval = max(5, min(60, int(msg["interval"])))
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            # Gather stats
            try:
                # Storage (tmpfs /workspace)
                storage_script = "df -m /workspace 2>/dev/null | tail -1 | awk '{print $3,$2}'"
                storage_result = await asyncio.to_thread(
                    container.exec_run, ["sh", "-c", storage_script]
                )
                storage_used_mb = 0.0
                storage_total_mb = float(os.getenv("SANDBOX_WORKSPACE_SIZE", "1024").rstrip("mMgG"))
                if storage_result.exit_code == 0:
                    parts = (storage_result.output or b"").decode().strip().split()
                    if len(parts) >= 2:
                        try:
                            storage_used_mb = float(parts[0])
                            storage_total_mb = float(parts[1])
                        except ValueError:
                            pass

                # Memory (Docker stats)
                memory_used_mb = 0.0
                memory_total_mb = 512.0
                try:
                    stats = await asyncio.to_thread(container.stats, stream=False)
                    mem_stats = stats.get("memory_stats", {})
                    memory_used_mb = mem_stats.get("usage", 0) / (1024 * 1024)
                    mem_limit = mem_stats.get("limit", 0)
                    if mem_limit > 0:
                        memory_total_mb = mem_limit / (1024 * 1024)
                except Exception:
                    pass

                storage_percent = (storage_used_mb / storage_total_mb * 100) if storage_total_mb > 0 else 0
                memory_percent = (memory_used_mb / memory_total_mb * 100) if memory_total_mb > 0 else 0

                await websocket.send_json({
                    "type": "stats",
                    "storage_used_mb": round(storage_used_mb, 1),
                    "storage_total_mb": round(storage_total_mb, 1),
                    "storage_percent": round(storage_percent, 1),
                    "memory_used_mb": round(memory_used_mb, 1),
                    "memory_total_mb": round(memory_total_mb, 1),
                    "memory_percent": round(memory_percent, 1),
                })
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.debug(f"Stats collection error: {e}")
                try:
                    await websocket.send_json({"type": "error", "message": str(e)})
                except Exception:
                    break

            await asyncio.sleep(interval)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket stats error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass


@app.get("/workspace/info/{user_id}/{chat_id}")
async def workspace_info(
    user_id: str,
    chat_id: str,
    authenticated_user_id: str = Depends(CurrentUser)
):
    """Get workspace information from persistent storage."""
    if str(authenticated_user_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own workspace"
        )

    try:
        client = get_workspace_client()
        info = await asyncio.to_thread(
            client.get_workspace_info,
            user_id=user_id,
            chat_id=chat_id
        )

        if info:
            return info
        else:
            return {"exists": False}

    except Exception as e:
        logger.error("orchestrator.workspace_info_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/excel/read")
async def excel_read(request: ExcelReadRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Read an Excel file with formulas using openpyxl in the sandbox."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.read_excel,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        sheet_index=request.sheet_index
    )
    return result


@app.post("/excel/update-cell")
async def excel_update_cell(request: ExcelUpdateCellRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Update an Excel cell with value or formula using openpyxl in the sandbox."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    result = await asyncio.to_thread(
        sandbox_executor.update_excel_cell,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        sheet_index=request.sheet_index,
        row=request.row,
        col=request.col,
        value=request.value,
        formula=request.formula
    )
    return result


@app.post("/excel/batch-update")
async def excel_batch_update(request: ExcelBatchUpdateRequest, authenticated_user_id: str = Depends(CurrentUser)):
    """Update multiple Excel cells in batch (MUCH faster than multiple update-cell calls)."""
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own files"
        )

    # Convert Pydantic models to dict for sandbox_executor
    updates = [update.dict() for update in request.updates]

    result = await asyncio.to_thread(
        sandbox_executor.batch_update_excel_cells,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        path=request.path,
        sheet_index=request.sheet_index,
        updates=updates
    )
    return result


# --- Coding Agent Autonomous Agent Endpoint ---

@app.post("/coding-agent/execute", response_model=CodingAgentExecuteResponse)
async def execute_coding_agent(
    request: CodingAgentExecuteRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor)
):
    """
    Execute Coding Agent autonomous agent in user's sandbox.

    Coding Agent runs inside the sandbox container with access to the user's workspace,
    using the specified model and OpenRouter API key. It can autonomously explore,
    edit files, and run commands to complete complex coding tasks.

    The agent runs in an isolated `/agents/coding-agent-{job_id}/` directory with
    a symlink to the user's workspace for safety.
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only execute Coding Agent for your own user account"
        )

    logger.info(
        f"[CodingAgent] Execute request: user={request.user_id}, chat={request.chat_id}, "
        f"model={request.model}, mode={request.mode}, plan_id={request.plan_id}, "
        f"task={request.task[:100]}..."
    )

    try:
        # Import the runner
        from coding_agent_runner import CodingAgentRunner

        # Create runner instance
        runner = CodingAgentRunner(
            sandbox_executor=executor,
            user_id=request.user_id,
            chat_id=request.chat_id
        )

        # Execute Coding Agent
        result = await runner.execute(
            task=request.task,
            model=request.model,
            api_key=request.openrouter_api_key,
            allowed_tools=request.allowed_tools,
            max_iterations=request.max_iterations,
            conversation_id=request.conversation_id,
            model_metadata=request.model_metadata,
            mcp_servers=request.mcp_servers,
            mode=request.mode,
            plan_id=request.plan_id,
            sub_agents=request.sub_agents,
            user_model_preferences=request.user_model_preferences,
            budget_usd=request.budget_usd,
        )

        logger.info(
            f"[CodingAgent] Execution completed: success={result.get('success')}, "
            f"job_id={result.get('job_id')}"
        )

        return CodingAgentExecuteResponse(
            success=result.get("success", False),
            job_id=result.get("job_id"),
            summary=result.get("summary"),
            files_modified=result.get("files_modified", []),
            files_created=result.get("files_created", []),
            steps=result.get("steps", []),
            error=result.get("error"),
            duration_ms=result.get("duration_ms", 0),
            total_tokens=result.get("total_tokens", 0),
            total_cost_usd=result.get("total_cost_usd", 0.0),
            quota_exceeded=result.get("quota_exceeded", False),
        )

    except ImportError:
        logger.error("orchestrator.coding_agent_runner_unavailable", exc_info=True)
        return CodingAgentExecuteResponse(
            success=False,
            error="Coding Agent runner not available"
        )
    except Exception as e:
        logger.error("orchestrator.coding_agent_failed", exc_info=True)
        return CodingAgentExecuteResponse(
            success=False,
            error=str(e)
        )


@app.post("/coding-agent/progress", response_model=CodingAgentProgressResponse)
async def get_coding_agent_progress(
    request: CodingAgentProgressRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor)
):
    """
    Get real-time progress of a running Coding Agent job.

    Uses in-memory progress store (primary) with file-based fallback.
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only check progress for your own jobs"
        )

    try:
        # Primary: check in-memory progress store
        from coding_agent_runner import get_progress_from_store
        progress = get_progress_from_store(request.user_id, request.chat_id)

        if not progress:
            return CodingAgentProgressResponse(found=False)

        # Build pending_question from _pending_questions if present
        key = f"{request.user_id}:{request.chat_id}"
        pending_q = None
        if key in _pending_questions:
            pq = _pending_questions[key]
            pending_q = {"question": pq["question"]}
            if pq.get("options"):
                pending_q["options"] = pq["options"]

        return CodingAgentProgressResponse(
            found=True,
            step_count=progress.get("step_count", 0),
            total_steps=progress.get("total_steps", 0),
            completed=progress.get("completed", False),
            exit_code=progress.get("exit_code"),
            files_created=progress.get("files_created", []),
            files_modified=progress.get("files_modified", []),
            files_read=progress.get("files_read", []),
            files_deleted=progress.get("files_deleted", []),
            steps=progress.get("steps", []),
            error=progress.get("error"),
            summary=progress.get("summary"),
            total_cost_usd=progress.get("total_cost_usd", 0.0),
            total_tokens=progress.get("total_tokens", 0),
            pending_question=pending_q,
        )

    except Exception:
        logger.error("orchestrator.coding_agent_progress_read_failed", exc_info=True)
        return CodingAgentProgressResponse(found=False)


@app.post("/mcp/ask-user", response_model=AskUserResponse)
async def mcp_ask_user(request: AskUserRequest):
    """
    MCP relay endpoint: blocks until the user answers or timeout.

    Called by the MCP stdio relay script inside the sandbox.
    Validates job_token against the stored token in _progress_store.
    """
    from coding_agent_runner import _progress_store

    key = f"{request.user_id}:{request.chat_id}"

    # Validate job token
    store_entry = _progress_store.get(key)
    if not store_entry:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active coding agent job found for this user/chat"
        )

    expected_token = store_entry.get("_job_token")
    if not expected_token or request.job_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid job token"
        )

    # Create event for blocking
    event = asyncio.Event()
    _pending_questions[key] = {
        "question": request.question,
        "options": request.options,
        "event": event,
        "answer": None,
    }

    logger.info(f"[AskUser] Question pending for {key}: {request.question[:100]}")

    try:
        await asyncio.wait_for(event.wait(), timeout=ASK_USER_TIMEOUT)
        answer = _pending_questions[key]["answer"]
        logger.info(f"[AskUser] Answer received for {key}: {str(answer)[:100]}")
        return AskUserResponse(answer=answer, timed_out=False)
    except asyncio.TimeoutError:
        logger.warning("orchestrator.ask_user_timeout", extra={"key": key})
        return AskUserResponse(
            answer="The user did not respond within the timeout period. Proceed with your best judgment based on the available information.",
            timed_out=True,
        )
    finally:
        _pending_questions.pop(key, None)


@app.post("/coding-agent/answer")
async def submit_coding_agent_answer(
    request: SubmitAnswerRequest,
    authenticated_user_id: str = Depends(CurrentUser),
):
    """
    Submit an answer to a pending coding agent question.

    Called by Django when the user answers in the frontend.
    """
    if str(authenticated_user_id) != str(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only answer questions for your own jobs"
        )

    key = f"{request.user_id}:{request.chat_id}"
    entry = _pending_questions.get(key)

    if not entry:
        return {"success": False, "error": "No pending question"}

    entry["answer"] = request.answer
    entry["event"].set()
    logger.info(f"[AskUser] Answer submitted for {key}")
    return {"success": True}


@app.get("/artifacts/{user_id}/{project_id}")
async def list_artifacts(user_id: str, project_id: str):
    """
    List all artifacts for a user×project.
    """
    artifacts = await artifact_storage.list_artifacts(user_id, project_id)
    return {"artifacts": artifacts, "total": len(artifacts)}


@app.get("/artifacts/{user_id}/{project_id}/{artifact_name}/download")
async def get_artifact_download_url(user_id: str, project_id: str, artifact_name: str):
    """
    Get signed download URL for an artifact.
    """
    url = await artifact_storage.get_download_url(user_id, project_id, artifact_name)
    return {"download_url": url, "expires_in": 3600}


# --- Security Monitoring Endpoints ---

class LogCommandRequest(BaseModel):
    """Request to log a command execution."""
    user_id: str
    project_id: str
    command: str
    source: str = "terminal"  # terminal, api


@app.post("/security/log-command")
async def log_command(request: LogCommandRequest):
    """
    Log a command execution for security monitoring.

    This endpoint should be called by:
    - Terminal sessions before executing commands
    - Code execution endpoints
    """
    allowed, reason = security_monitor.log_command(
        user_id=request.user_id,
        project_id=request.project_id,
        command=request.command,
        source=request.source
    )

    return {
        "allowed": allowed,
        "reason": reason,
        "message": "Command logged successfully"
    }


@app.get("/security/metrics/{user_id}/{project_id}")
async def get_security_metrics(user_id: str, project_id: str):
    """
    Get security metrics and summary for a user/project sandbox.

    Returns:
    - Command counts
    - Rate limit violations
    - Recent security events
    - Resource usage statistics
    """
    container_name = f"sandbox-ide-{user_id}-{project_id}"

    # Check resource usage
    resource_event = security_monitor.check_resource_usage(
        user_id=user_id,
        project_id=project_id,
        container_name=container_name
    )

    # Get summary
    summary = security_monitor.get_security_summary(user_id, project_id)

    # Add resource alert if present
    if resource_event:
        summary["latest_alert"] = {
            "type": resource_event.event_type,
            "severity": resource_event.severity,
            "details": resource_event.details
        }

    return summary


@app.post("/security/check-resources/{user_id}/{project_id}")
async def check_container_resources(user_id: str, project_id: str):
    """
    Manually trigger resource usage check for a container.

    Useful for:
    - On-demand monitoring
    - Alert validation
    - Admin panels
    """
    container_name = f"sandbox-ide-{user_id}-{project_id}"

    event = security_monitor.check_resource_usage(
        user_id=user_id,
        project_id=project_id,
        container_name=container_name
    )

    if event:
        return {
            "status": "alert",
            "event": {
                "type": event.event_type,
                "severity": event.severity,
                "timestamp": event.timestamp.isoformat(),
                "details": event.details
            }
        }

    return {"status": "ok", "message": "No resource alerts detected"}


@app.post("/security/cleanup")
async def cleanup_security_data():
    """
    Cleanup old security monitoring data.

    Should be called periodically (e.g., daily cron job).
    Removes events older than 7 days.
    """
    security_monitor.cleanup_old_data()
    return {"status": "success", "message": "Security data cleaned up"}


# --- Process Management Endpoints ---

@app.post("/processes/start")
async def start_process(
    request: StartProcessRequest,
    user: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor),
):
    """Start a background process and register its port."""
    # SECURITY: User isolation
    if str(user) != str(request.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User mismatch")

    sandbox_id = f"sandbox-exec-{request.user_id}"

    # Enforce max processes per user
    existing = _port_registry.get(sandbox_id, [])
    if len(existing) >= MAX_PROCESSES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {MAX_PROCESSES_PER_USER} concurrent processes allowed",
        )

    # Check for duplicate port
    if any(p["port"] == request.port for p in existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Port {request.port} is already registered",
        )

    chat_workspace = executor._get_chat_workspace_path(request.chat_id, request.conversation_id)

    # Resolve effective working directory (cwd param overrides default chat_workspace)
    effective_cwd = chat_workspace
    if request.cwd:
        import os as os_module
        relative_cwd = request.cwd
        if relative_cwd.startswith("/workspace/"):
            relative_cwd = relative_cwd.replace("/workspace/", "", 1)
        elif relative_cwd.startswith("/workspace"):
            relative_cwd = relative_cwd.replace("/workspace", "", 1).lstrip("/")
        relative_cwd = relative_cwd.lstrip("/")
        candidate = os_module.path.normpath(f"{chat_workspace}/{relative_cwd}")
        if not candidate.startswith(chat_workspace):
            raise HTTPException(status_code=400, detail="cwd escapes workspace")
        effective_cwd = candidate

    try:
        result = await asyncio.to_thread(
            executor.start_background_process,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            chat_id=request.chat_id,
            sync_mode=request.sync_mode,
            command=request.command,
            chat_workspace=effective_cwd,
        )
    except Exception as e:
        logger.error("orchestrator.process_start_failed", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    entry = {
        "pid": result["pid"],
        "port": request.port,
        "command": request.command,
        "started_at": datetime.utcnow().isoformat(),
    }
    _port_registry.setdefault(sandbox_id, []).append(entry)

    return {**entry, "status": "running"}


# NOTE: /processes/health MUST be registered before /processes/{user_id}
# otherwise FastAPI matches "health" as a user_id path parameter.
@app.get("/processes/health")
async def process_health(
    user_id: str,
    port: int,
    user: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor),
):
    """Check if a process is listening on a port inside the sandbox (TCP check)."""
    if str(user) != str(user_id):
        raise HTTPException(status_code=403, detail="User mismatch")

    container_ip = executor.get_container_ip(user_id, "", None, True)
    if not container_ip:
        return {"ready": False}

    def tcp_check():
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.connect((container_ip, port))
            sock.close()
            return True
        except (ConnectionRefusedError, OSError, TimeoutError):
            return False

    ready = await asyncio.to_thread(tcp_check)
    return {"ready": ready}


@app.get("/processes/{user_id}")
async def list_processes(
    user_id: str,
    chat_id: str,
    user: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor),
):
    """List running processes with their registered ports."""
    if str(user) != str(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User mismatch")

    sandbox_id = f"sandbox-exec-{user_id}"

    # Get live process list from sandbox
    live_pids: set[int] = set()
    try:
        live = await asyncio.to_thread(
            executor.list_processes,
            user_id=user_id,
            conversation_id=chat_id,
            chat_id=chat_id,
            sync_mode=True,
        )
        live_pids = {p["pid"] for p in live}
    except Exception:
        logger.warning("orchestrator.list_live_processes_failed", exc_info=True)

    # Merge with port registry — remove dead entries
    registered = _port_registry.get(sandbox_id, [])
    alive = []
    for entry in registered:
        if entry["pid"] in live_pids:
            alive.append({**entry, "status": "running"})
        # else: process died, remove from registry
    _port_registry[sandbox_id] = [e for e in registered if e["pid"] in live_pids]

    return alive


@app.post("/processes/stop")
async def stop_process(
    request: StopProcessRequest,
    user: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor),
):
    """Stop a background process by PID."""
    if str(user) != str(request.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User mismatch")

    sandbox_id = f"sandbox-exec-{request.user_id}"

    success = await asyncio.to_thread(
        executor.stop_process,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=request.chat_id,
        sync_mode=request.sync_mode,
        pid=request.pid,
    )

    # Remove from registry
    registered = _port_registry.get(sandbox_id, [])
    _port_registry[sandbox_id] = [e for e in registered if e["pid"] != request.pid]

    if not success:
        raise HTTPException(status_code=404, detail="Process not found or already stopped")
    return {"success": True}


class StopByPortRequest(BaseModel):
    user_id: str
    conversation_id: str
    port: int


@app.post("/processes/stop-by-port")
async def stop_process_by_port(
    request: StopByPortRequest,
    user: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor),
):
    """Stop a background process by port (looks up PID from registry)."""
    if str(user) != str(request.user_id):
        raise HTTPException(status_code=403, detail="User mismatch")

    sandbox_id = f"sandbox-exec-{request.user_id}"
    registered = _port_registry.get(sandbox_id, [])
    entry = next((e for e in registered if e["port"] == request.port), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No process on port {request.port}")

    pid = entry["pid"]
    success = await asyncio.to_thread(
        executor.stop_process,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        chat_id=None,
        sync_mode=True,
        pid=pid,
    )
    _port_registry[sandbox_id] = [e for e in registered if e["port"] != request.port]

    if not success:
        raise HTTPException(status_code=500, detail="Failed to stop process")
    return {"success": True, "pid": pid, "port": request.port}


class RestartProcessRequest(BaseModel):
    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None
    sync_mode: bool = True
    command: str
    port: int = Field(..., ge=3000, le=9999)

    @field_validator('command')
    @classmethod
    def validate_command(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Command cannot be empty')
        if len(v) > 500:
            raise ValueError('Command too long')
        if any(c in v for c in '\n\r\x00'):
            raise ValueError('Disallowed control characters')
        if not _ALLOWED_COMMAND_PATTERN.match(v):
            raise ValueError('Disallowed characters in command')
        return v


@app.post("/processes/restart")
async def restart_process(
    request: RestartProcessRequest,
    user: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(require_sandbox_executor),
):
    """Atomic restart: stop existing process on port, wait for release, start new one."""
    if str(user) != str(request.user_id):
        raise HTTPException(status_code=403, detail="User mismatch")

    sandbox_id = f"sandbox-exec-{request.user_id}"

    # 1. Stop existing process on this port (if any)
    registered = _port_registry.get(sandbox_id, [])
    old_entry = next((e for e in registered if e["port"] == request.port), None)
    if old_entry:
        await asyncio.to_thread(
            executor.stop_process,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            chat_id=request.chat_id,
            sync_mode=True,
            pid=old_entry["pid"],
        )
        _port_registry[sandbox_id] = [e for e in registered if e["port"] != request.port]

    # 2. Wait for port to be released then start (up to 5 retries)
    chat_workspace = executor._get_chat_workspace_path(request.chat_id, request.conversation_id)
    last_error = None
    for attempt in range(5):
        await asyncio.sleep(1.0)
        try:
            result = await asyncio.to_thread(
                executor.start_background_process,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                chat_id=request.chat_id,
                sync_mode=request.sync_mode,
                command=request.command,
                chat_workspace=chat_workspace,
            )
            entry = {
                "pid": result["pid"],
                "port": request.port,
                "command": request.command,
                "started_at": datetime.utcnow().isoformat(),
            }
            _port_registry.setdefault(sandbox_id, []).append(entry)
            return {**entry, "status": "running"}
        except Exception as e:
            last_error = e
            continue

    raise HTTPException(status_code=500, detail=f"Restart failed after 5 attempts: {last_error}")


@app.post("/preview/token")
async def create_preview_token(
    user_id: str,
    port: int,
    user: str = Depends(CurrentUser),
):
    """Mint a short-lived, scope-limited preview token. Requires real JWT (Bearer header)."""
    if str(user) != str(user_id):
        raise HTTPException(status_code=403, detail="User mismatch")
    if not (3000 <= port <= 9999):
        raise HTTPException(status_code=400, detail="Port must be between 3000 and 9999")
    token = generate_preview_token(user_id, port)
    return {"token": token, "expires_in": PREVIEW_TOKEN_EXPIRY}


@app.api_route("/preview/{user_id}/{port}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def preview_proxy(
    user_id: str,
    port: int,
    path: str,
    request: Request,
    token: Optional[str] = None,
    executor: SandboxExecutor = Depends(require_sandbox_executor),
):
    """Reverse proxy to a port inside the sandbox container.
    Accepts auth via query param ?token=<preview_token> (for iframe usage)."""
    from urllib.parse import urlencode, parse_qs

    # SECURITY: Use scoped preview token instead of main JWT
    claims = verify_preview_token(token)
    if str(claims["user_id"]) != str(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User mismatch")
    if claims["port"] != 0 and claims["port"] != port:  # port=0 for dev tokens
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token not valid for this port")

    # Validate port range
    if not (3000 <= port <= 9999):
        raise HTTPException(status_code=400, detail="Port must be between 3000 and 9999")

    # Get container IP
    container_ip = await asyncio.to_thread(
        executor.get_container_ip,
        user_id=user_id,
        conversation_id=user_id,  # Sandbox is per-user
        chat_id=None,
        sync_mode=True,
    )
    if not container_ip:
        raise HTTPException(status_code=502, detail="Sandbox container not reachable")

    # SECURITY: Build target URL — strip auth token from query before forwarding (CWE-598)
    target_url = f"http://{container_ip}:{port}/{path}"
    raw_query = str(request.url.query)
    if raw_query:
        params = parse_qs(raw_query, keep_blank_values=True)
        params.pop("token", None)  # Don't leak auth token to sandbox process
        clean_query = urlencode(params, doseq=True)
        if clean_query:
            target_url += f"?{clean_query}"

    # Forward headers (strip host)
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ('host', 'authorization')
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            proxied = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=await request.body(),
            )
            # Build response headers, stripping hop-by-hop
            resp_headers = {
                k: v for k, v in proxied.headers.items()
                if k.lower() not in ('transfer-encoding', 'connection', 'keep-alive')
            }
            # SECURITY: Add security headers to prevent token leaks and content sniffing
            resp_headers["Referrer-Policy"] = "no-referrer"
            resp_headers["X-Content-Type-Options"] = "nosniff"
            # NOTE: X-Frame-Options omitted — preview is loaded in an iframe from a different origin
            # (frontend on :5173, proxy on :8003). CSP frame-ancestors would be the modern alternative
            # but is not needed here since auth is handled via scoped preview tokens.
            return Response(
                content=proxied.content,
                status_code=proxied.status_code,
                headers=resp_headers,
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Could not connect to process — is it running?")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request to sandbox process timed out")


# Mount static files for artifacts (images, plots) - MUST be at the end to avoid route conflicts
# Using /artifact-files/ to avoid conflict with existing /artifacts/ endpoints
# Files are accessed via /artifact-files/{user_id}/{chat_id}/{filename}
# Ensure directory exists before mounting (StaticFiles requires it)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artifact-files", StaticFiles(directory=str(ARTIFACTS_DIR)), name="artifact-files")


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions."""
    logger.error(
        "orchestrator.http_exception",
        extra={"status_code": exc.status_code, "detail": str(exc.detail)},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
