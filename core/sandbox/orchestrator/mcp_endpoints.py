"""
MCP Server API Endpoints

FastAPI router for MCP server management.

MCP servers run as child processes inside the user's sandbox container,
managed by the MCP Gateway. This avoids creating separate containers per
MCP server, making it much more scalable.

Architecture:
    User Request → Orchestrator → Sandbox Container → MCP Gateway → MCP Server Process
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import logging

from auth import CurrentUser
from sandbox_executor import SandboxExecutor

logger = logging.getLogger(__name__)

# Router for MCP endpoints
router = APIRouter(prefix="/mcp", tags=["MCP Servers"])

# Global reference to sandbox executor (set during app initialization)
_sandbox_executor: Optional[SandboxExecutor] = None


def get_sandbox_executor() -> SandboxExecutor:
    """Dependency to get sandbox executor instance."""
    if _sandbox_executor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox executor not initialized"
        )
    return _sandbox_executor


def set_sandbox_executor(executor: SandboxExecutor):
    """Set the global sandbox executor instance."""
    global _sandbox_executor
    _sandbox_executor = executor


# --- Request/Response Models ---

class StartServerRequest(BaseModel):
    """Request to start an MCP server."""
    server_id: str = Field(..., description="Unique server identifier")
    npm_package: str = Field(..., description="NPM package name (e.g., '@brave/brave-search-mcp-server')")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables (API keys, tokens)")
    allowed_domains: Optional[List[str]] = Field(default=None, description="Domains to whitelist for network egress")


class StartServerResponse(BaseModel):
    """Response from starting an MCP server."""
    server_id: str
    npm_package: str
    status: str
    message: str


class ServerInfo(BaseModel):
    """Information about a running MCP server."""
    server_id: str = Field(..., alias="serverId")
    npm_package: str = Field(..., alias="npmPackage")
    running: bool
    pid: Optional[int] = None
    uptime_ms: Optional[int] = Field(default=None, alias="uptime")
    tools_count: Optional[int] = Field(default=None, alias="toolsCount")

    class Config:
        populate_by_name = True


class ToolCallRequest(BaseModel):
    """Request to call a tool on an MCP server."""
    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    timeout: int = Field(default=60, description="Execution timeout in seconds")


class ToolCallResponse(BaseModel):
    """Response from a tool call."""
    success: bool
    result: Optional[Any] = None
    error: Optional[Any] = None


class HealthResponse(BaseModel):
    """Health check response."""
    running: bool
    pid: Optional[int] = None
    npm_package: Optional[str] = Field(default=None, alias="npmPackage")
    uptime_ms: Optional[int] = Field(default=None, alias="uptime")
    tools_count: Optional[int] = Field(default=None, alias="toolsCount")
    error: Optional[str] = None

    class Config:
        populate_by_name = True


# --- API Endpoints ---

@router.post("/servers", response_model=StartServerResponse)
async def start_server(
    request: StartServerRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(get_sandbox_executor),
):
    """
    Start an MCP server inside the user's sandbox container.

    The server runs as a child process managed by the MCP Gateway,
    with network egress controlled via proxy.
    """
    logger.info(f"Starting MCP server: user={authenticated_user_id}, package={request.npm_package}")

    try:
        result = executor.start_mcp_server(
            user_id=str(authenticated_user_id),
            server_id=request.server_id,
            npm_package=request.npm_package,
            env_vars=request.env_vars,
            allowed_domains=request.allowed_domains,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to start server")
            )

        return StartServerResponse(
            server_id=request.server_id,
            npm_package=request.npm_package,
            status="running",
            message=result.get("message", "Server started successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/servers", response_model=List[ServerInfo])
async def list_servers(
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(get_sandbox_executor),
):
    """
    List all running MCP servers for the current user.
    """
    try:
        result = executor.list_mcp_servers(str(authenticated_user_id))

        if not result.get("success", True):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to list servers")
            )

        servers = result.get("servers", [])
        return [ServerInfo(**srv) for srv in servers]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list MCP servers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/servers/{server_id}")
async def stop_server(
    server_id: str,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(get_sandbox_executor),
):
    """
    Stop an MCP server running in the user's sandbox.
    """
    logger.info(f"Stopping MCP server: server={server_id}, user={authenticated_user_id}")

    try:
        result = executor.stop_mcp_server(
            user_id=str(authenticated_user_id),
            server_id=server_id,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to stop server")
            )

        return {"message": "Server stopped successfully", "server_id": server_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop MCP server: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/servers/{server_id}/health", response_model=HealthResponse)
async def check_health(
    server_id: str,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(get_sandbox_executor),
):
    """
    Check the health of an MCP server.
    """
    try:
        result = executor.mcp_server_status(
            user_id=str(authenticated_user_id),
            server_id=server_id,
        )

        return HealthResponse(**result)

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(running=False, error=str(e))


@router.get("/servers/{server_id}/tools", response_model=List[Dict[str, Any]])
async def discover_tools(
    server_id: str,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(get_sandbox_executor),
):
    """
    Discover tools available from an MCP server.
    """
    try:
        result = executor.discover_mcp_tools(
            user_id=str(authenticated_user_id),
            server_id=server_id,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to discover tools")
            )

        return result.get("tools", [])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool discovery failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/servers/{server_id}/tools/call", response_model=ToolCallResponse)
async def call_tool(
    server_id: str,
    request: ToolCallRequest,
    authenticated_user_id: str = Depends(CurrentUser),
    executor: SandboxExecutor = Depends(get_sandbox_executor),
):
    """
    Call a tool on an MCP server.
    """
    logger.info(f"Calling tool: server={server_id}, tool={request.tool_name}")

    try:
        result = executor.call_mcp_tool(
            user_id=str(authenticated_user_id),
            server_id=server_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            timeout=request.timeout,
        )

        return ToolCallResponse(**result)

    except Exception as e:
        logger.error(f"Tool call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


class CallToolByServerIdRequest(BaseModel):
    """Request to call a tool on an MCP server by server_id."""
    user_id: str = Field(..., description="User ID who owns the server")
    server_id: str = Field(..., description="Server ID from the database")
    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    timeout: int = Field(default=60, description="Execution timeout in seconds")
    # Server config for on-demand start
    npm_package: Optional[str] = Field(default=None, description="NPM package if server needs to be started")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables for the server")
    allowed_domains: Optional[List[str]] = Field(default=None, description="Allowed domains for egress")


@router.post("/call-tool", response_model=ToolCallResponse)
async def call_tool_by_server_id(
    request: CallToolByServerIdRequest,
    executor: SandboxExecutor = Depends(get_sandbox_executor),
):
    """
    Call a tool on an MCP server by server_id.

    This endpoint finds or starts the MCP server process for the given server_id,
    then calls the tool. Used by LangChain agent for MCP tool execution.

    If the server is not running and npm_package is provided, it will
    start the server on-demand.
    """
    logger.info(f"Calling tool by server_id: user={request.user_id}, server={request.server_id}, tool={request.tool_name}")

    try:
        # Check if server is running
        status_result = executor.mcp_server_status(
            user_id=request.user_id,
            server_id=request.server_id,
        )

        if not status_result.get("running"):
            # Server not running - try to start it if we have the config
            if request.npm_package:
                logger.info(f"Starting MCP server on-demand: {request.server_id}")
                start_result = executor.start_mcp_server(
                    user_id=request.user_id,
                    server_id=request.server_id,
                    npm_package=request.npm_package,
                    env_vars=request.env_vars,
                    allowed_domains=request.allowed_domains,
                )

                if not start_result.get("success"):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Failed to start server: {start_result.get('error', 'Unknown error')}"
                    )

                # Wait a moment for server to initialize
                import asyncio
                await asyncio.sleep(2)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Server {request.server_id} is not running and no npm_package provided to start it."
                )

        # Call the tool
        logger.info(f"[MCP] Calling tool: {request.tool_name} with arguments: {request.arguments}")
        result = executor.call_mcp_tool(
            user_id=request.user_id,
            server_id=request.server_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            timeout=request.timeout,
        )

        return ToolCallResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
