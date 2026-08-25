"""
Unified MCP Registry

Loads a user's active MCPServer rows and manages sandboxed npm-package, WebSocket, and remote HTTP servers built from them, keeping connection and instance state in process memory rather than the database; for remote HTTP servers configured with OAuth, it refreshes the stored token itself when it needs refresh, before use.
registry.py loads and connects to a user's active MCPServer rows independently of this module (over WebSocket, HTTP, and STDIO-via-command), persisting connection status and discovered tools to the database.

Design Principles:
- Per-user isolation: Each user's servers are independent
- Lazy loading: Servers start on-demand
- Transport abstraction: WebSocket and Sandboxed Stdio share same interface
- Secure defaults: All stdio servers run in sandboxes
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import threading

import httpx
from django.conf import settings

from .client import MCPWebSocketClient, MCPRemoteHTTPClient
from .exceptions import MCPConnectionError, MCPTimeoutError

logger = logging.getLogger(__name__)


class ServerTransport(str, Enum):
    """Transport types for MCP servers."""
    WEBSOCKET = "websocket"      # User-hosted, direct WebSocket connection
    SANDBOXED_STDIO = "stdio"    # npm package, sandboxed container
    REMOTE_HTTP = "http"         # Remote HTTP/SSE server (like Zapier, etc.)


class ServerSource(str, Enum):
    """Where the server configuration comes from."""
    PRECONFIGURED = "preconfigured"  # System-wide preconfigured server
    CUSTOM = "custom"                 # User-created MCPServer


class ServerStatus(str, Enum):
    """Runtime status of a server."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class MCPServerInfo:
    """
    Unified representation of an MCP server.

    Supports:
    - Preconfigured servers (is_preconfigured=True)
    - Custom user servers (is_preconfigured=False)
    - Remote HTTP servers (Zapier, Atlassian, etc.)
    """
    # Identity
    server_id: str              # Unique ID (format: "connector:{slug}" or "custom:{id}")
    name: str
    description: str
    source: ServerSource

    # Transport
    transport: ServerTransport

    # For WebSocket
    url: Optional[str] = None
    auth_headers: Optional[Dict[str, str]] = None

    # For Sandboxed Stdio
    npm_package: Optional[str] = None
    command_args: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    allowed_domains: List[str] = field(default_factory=list)

    # For Remote HTTP
    remote_url: Optional[str] = None
    auth_type: str = "none"  # 'none', 'api_key', 'bearer', 'oauth'
    auth_header_name: str = "Authorization"
    auth_config: Optional[Dict[str, Any]] = None

    # Status
    status: ServerStatus = ServerStatus.STOPPED
    last_error: Optional[str] = None

    # Runtime (set when server is running)
    container_id: Optional[str] = None
    endpoint_url: Optional[str] = None
    started_at: Optional[datetime] = None


@dataclass
class MCPToolInfo:
    """Discovered tool from an MCP server."""
    tool_id: str           # Format: "{server_id}.{tool_name}"
    server_id: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None


@dataclass
class MCPServerInstance:
    """Runtime instance of a server for a specific user."""
    info: MCPServerInfo
    user_id: str

    # Connection state
    container_id: Optional[str] = None
    websocket_client: Optional[MCPWebSocketClient] = None
    http_client: Optional[MCPRemoteHTTPClient] = None

    # Cached tools
    tools: List[MCPToolInfo] = field(default_factory=list)
    tools_discovered_at: Optional[datetime] = None

    # Metrics
    request_count: int = 0
    error_count: int = 0


class UnifiedMCPRegistry:
    """
    Single registry managing ALL MCP servers.

    Responsibilities:
    - Load server configurations from database
    - Manage server lifecycle (start, stop, health check)
    - Route tool discovery and execution to correct transport
    - Cache tools per user
    - Handle errors gracefully

    Usage:
        registry = get_mcp_registry()

        # Get all servers for a user
        servers = await registry.get_user_servers(user_id)

        # Get all tools for a user
        tools = await registry.get_user_tools(user_id)

        # Execute a tool
        result = await registry.execute_tool(user_id, tool_id, arguments)
    """

    def __init__(
        self,
        orchestrator_url: str = None,
        tool_cache_ttl_seconds: int = 300,  # 5 minutes
    ):
        self.orchestrator_url = orchestrator_url or getattr(
            settings, 'ORCHESTRATOR_URL', 'http://sterna-orchestrator:8003'
        )
        self.tool_cache_ttl = timedelta(seconds=tool_cache_ttl_seconds)

        # Per-user server instances
        # Structure: {user_id: {server_id: MCPServerInstance}}
        self._instances: Dict[str, Dict[str, MCPServerInstance]] = {}
        self._lock = threading.RLock()

        # HTTP client for orchestrator communication
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(f"[UnifiedMCPRegistry] Initialized with orchestrator: {self.orchestrator_url}")

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=100),
            )
        return self._http_client

    async def close(self):
        """Close resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ─────────────────────────────────────────────────────────────────────
    # Server Configuration Loading
    # ─────────────────────────────────────────────────────────────────────

    async def get_user_servers(self, user_id: str) -> List[MCPServerInfo]:
        """
        Get all MCP servers available to a user.

        Args:
            user_id: User identifier

        Returns:
            List of MCPServerInfo objects
        """
        from .models import MCPServer

        servers = []

        # Load servers
        try:
            custom_servers = await asyncio.to_thread(
                lambda: list(
                    MCPServer.objects.filter(
                        user_id=user_id,
                        is_active=True,
                    )
                )
            )

            for server in custom_servers:
                # Use server_type property if available, otherwise fall back to transport_type
                server_type = getattr(server, 'server_type', None)

                if server_type == 'remote_http' or (server_type is None and server.transport_type == 'http'):
                    # Remote HTTP server
                    # Build auth_config with OAuth token if using OAuth
                    auth_config = server.auth_config if server.auth_config else {}
                    auth_type = getattr(server, 'auth_type', 'none')

                    if auth_type == 'oauth':
                        # For OAuth, check if token needs refresh first
                        if server.oauth_needs_refresh and server.oauth_refresh_token:
                            logger.info(f"[UnifiedMCPRegistry] Token expired for {server.name}, refreshing...")
                            refresh_success = await self._refresh_oauth_token(server)
                            if refresh_success:
                                # Reload the server to get the new token
                                await asyncio.to_thread(server.refresh_from_db)

                        # Use the oauth_access_token
                        oauth_token = getattr(server, 'oauth_access_token', None)
                        if oauth_token:
                            auth_config = {'token': oauth_token}
                        else:
                            logger.warning(f"OAuth server {server.name} has no access token")

                    servers.append(MCPServerInfo(
                        server_id=f"custom:{server.id}",
                        name=server.name,
                        description=server.description or "",
                        source=ServerSource.CUSTOM,
                        transport=ServerTransport.REMOTE_HTTP,
                        remote_url=getattr(server, 'remote_url', None) or server.url,
                        auth_type=auth_type,
                        auth_header_name=getattr(server, 'auth_header_name', 'Authorization'),
                        auth_config=auth_config,
                    ))
                elif server_type == 'remote_websocket' or (server_type is None and server.transport_type == 'websocket'):
                    # WebSocket server
                    servers.append(MCPServerInfo(
                        server_id=f"custom:{server.id}",
                        name=server.name,
                        description=server.description or "",
                        source=ServerSource.CUSTOM,
                        transport=ServerTransport.WEBSOCKET,
                        url=server.url,
                        auth_headers=server.auth_config.get('headers', {}) if server.auth_config else {},
                    ))
                else:
                    # Local/sandboxed server (npm package)
                    # Get npm_package from either the dedicated field or command field
                    npm_package = getattr(server, 'npm_package', None) or server.command
                    env_vars = {}
                    if server.auth_config:
                        env_vars = server.auth_config.get('env_vars', {})
                    # Also check for env_vars field directly
                    if hasattr(server, 'env_vars') and server.env_vars:
                        env_vars.update(server.env_vars)

                    allowed_domains = getattr(server, 'allowed_domains', []) or []

                    servers.append(MCPServerInfo(
                        server_id=f"custom:{server.id}",
                        name=server.name,
                        description=server.description or "",
                        source=ServerSource.CUSTOM,
                        transport=ServerTransport.SANDBOXED_STDIO,
                        npm_package=npm_package,
                        env_vars=env_vars,
                        allowed_domains=allowed_domains,
                    ))
        except Exception as e:
            logger.warning(f"[UnifiedMCPRegistry] Failed to load custom servers for user {user_id}: {e}")

        return servers

    def get_user_servers_sync(self, user_id: str) -> List[MCPServerInfo]:
        """Synchronous wrapper for get_user_servers."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new thread to run the async function
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.get_user_servers(user_id)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(self.get_user_servers(user_id))
        except Exception as e:
            logger.error(f"[UnifiedMCPRegistry] Sync get_user_servers failed: {e}")
            return []

    async def _refresh_oauth_token(self, server) -> bool:
        """
        Refresh OAuth token for an MCP server.

        Args:
            server: MCPServer model instance

        Returns:
            True if refresh succeeded, False otherwise
        """
        try:
            from .oauth import DynamicOAuthManager
            oauth_manager = DynamicOAuthManager()
            success = await oauth_manager.refresh_server_token(server)
            if success:
                logger.info(f"[UnifiedMCPRegistry] Token refreshed for server {server.id}")
            else:
                logger.warning(f"[UnifiedMCPRegistry] Token refresh failed for server {server.id}")
            return success
        except Exception as e:
            logger.error(f"[UnifiedMCPRegistry] Token refresh error for server {server.id}: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────
    # Server Lifecycle Management
    # ─────────────────────────────────────────────────────────────────────

    async def start_server(
        self,
        user_id: str,
        server_id: str,
    ) -> MCPServerInstance:
        """
        Start an MCP server for a user.

        For WebSocket: Establishes connection
        For Stdio: Requests sandbox container from orchestrator

        Args:
            user_id: User identifier
            server_id: Server identifier

        Returns:
            MCPServerInstance with connection established
        """
        # Get server info
        servers = await self.get_user_servers(user_id)
        server_info = next((s for s in servers if s.server_id == server_id), None)

        if not server_info:
            raise ValueError(f"Server not found: {server_id}")

        # Check if already running
        with self._lock:
            user_instances = self._instances.setdefault(user_id, {})
            if server_id in user_instances:
                instance = user_instances[server_id]
                if instance.info.status == ServerStatus.RUNNING:
                    # For OAuth servers, update auth_config in case token was refreshed
                    if server_info.auth_type == 'oauth' and instance.http_client:
                        # Update the HTTP client's auth config with fresh token
                        instance.http_client.auth_config = server_info.auth_config
                        instance.info.auth_config = server_info.auth_config
                    return instance

        # Create instance
        instance = MCPServerInstance(info=server_info, user_id=user_id)
        instance.info.status = ServerStatus.STARTING

        try:
            if server_info.transport == ServerTransport.WEBSOCKET:
                await self._start_websocket_server(instance)
            elif server_info.transport == ServerTransport.REMOTE_HTTP:
                await self._start_remote_http_server(instance)
            else:
                await self._start_sandboxed_server(instance)

            instance.info.status = ServerStatus.RUNNING
            instance.info.started_at = datetime.utcnow()

        except Exception as e:
            instance.info.status = ServerStatus.ERROR
            instance.info.last_error = str(e)
            logger.error(f"[UnifiedMCPRegistry] Failed to start {server_id}: {e}")
            raise

        # Cache instance
        with self._lock:
            self._instances.setdefault(user_id, {})[server_id] = instance

        logger.info(f"[UnifiedMCPRegistry] Started {server_id} for user {user_id}")
        return instance

    async def _start_websocket_server(self, instance: MCPServerInstance):
        """Start a WebSocket-based MCP server."""
        if not instance.info.url:
            raise MCPConnectionError("WebSocket URL is required")

        client = MCPWebSocketClient(
            url=instance.info.url,
            auth_config=instance.info.auth_headers or {},
        )

        await client.connect()
        await client.handshake()

        instance.websocket_client = client

    async def _start_sandboxed_server(self, instance: MCPServerInstance):
        """Start a sandboxed stdio MCP server via orchestrator."""
        if not instance.info.npm_package:
            raise MCPConnectionError("NPM package is required for sandboxed server")

        client = await self._get_http_client()

        # Request container from orchestrator
        try:
            response = await client.post(
                f"{self.orchestrator_url}/mcp/servers",
                json={
                    "server_id": instance.info.server_id,
                    "npm_package": instance.info.npm_package,
                    "env_vars": instance.info.env_vars or None,
                    "allowed_domains": None,  # TODO: Add allowed_domains to MCPServerInfo
                },
                timeout=60.0,  # Container startup can take time
            )
            response.raise_for_status()
            result = response.json()

            instance.container_id = result.get("container_id")
            instance.info.endpoint_url = result.get("endpoint_url")

            logger.info(f"[UnifiedMCPRegistry] Started sandboxed server: container={instance.container_id}")

        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_detail = e.response.json().get("detail", str(e))
            except Exception:
                error_detail = str(e)
            raise MCPConnectionError(f"Failed to start sandboxed server: {error_detail}")
        except httpx.RequestError as e:
            raise MCPConnectionError(f"Failed to connect to orchestrator: {e}")

    async def _start_remote_http_server(self, instance: MCPServerInstance):
        """Start a remote HTTP MCP server connection."""
        if not instance.info.remote_url:
            raise MCPConnectionError("Remote URL is required for HTTP server")

        client = MCPRemoteHTTPClient(
            url=instance.info.remote_url,
            auth_config=instance.info.auth_config or {},
            auth_type=instance.info.auth_type,
            auth_header=instance.info.auth_header_name,
        )

        await client.connect()

        # Optionally perform handshake
        try:
            await client.handshake()
        except Exception as e:
            # Some servers may not require handshake, log but continue
            logger.debug(f"[UnifiedMCPRegistry] Remote server handshake optional: {e}")

        instance.http_client = client
        instance.info.endpoint_url = instance.info.remote_url

        logger.info(f"[UnifiedMCPRegistry] Connected to remote HTTP server: {instance.info.remote_url}")

    async def stop_server(self, user_id: str, server_id: str):
        """Stop an MCP server for a user."""
        with self._lock:
            if user_id not in self._instances:
                return
            if server_id not in self._instances[user_id]:
                return
            instance = self._instances[user_id][server_id]

        instance.info.status = ServerStatus.STOPPING

        try:
            if instance.websocket_client:
                await instance.websocket_client.disconnect()

            if instance.http_client:
                await instance.http_client.disconnect()

            if instance.container_id:
                client = await self._get_http_client()
                try:
                    await client.delete(
                        f"{self.orchestrator_url}/mcp/servers/{instance.container_id}",
                        timeout=10.0,
                    )
                except Exception as e:
                    logger.warning(f"[UnifiedMCPRegistry] Failed to stop container: {e}")
        except Exception as e:
            logger.error(f"[UnifiedMCPRegistry] Error stopping {server_id}: {e}")

        instance.info.status = ServerStatus.STOPPED

        with self._lock:
            if user_id in self._instances and server_id in self._instances[user_id]:
                del self._instances[user_id][server_id]

        logger.info(f"[UnifiedMCPRegistry] Stopped {server_id} for user {user_id}")

    # ─────────────────────────────────────────────────────────────────────
    # Tool Discovery
    # ─────────────────────────────────────────────────────────────────────

    async def discover_tools(
        self,
        user_id: str,
        server_id: str,
        force_refresh: bool = False,
    ) -> List[MCPToolInfo]:
        """
        Discover tools from an MCP server.

        Starts the server if not running.
        Caches results for performance.

        Args:
            user_id: User identifier
            server_id: Server identifier
            force_refresh: Force refresh even if cached

        Returns:
            List of MCPToolInfo objects
        """
        # Get or start instance
        instance = await self.start_server(user_id, server_id)

        # Check cache
        if not force_refresh and instance.tools:
            if instance.tools_discovered_at:
                age = datetime.utcnow() - instance.tools_discovered_at
                if age < self.tool_cache_ttl:
                    return instance.tools

        # Discover tools via MCP protocol
        tools_response = []

        if instance.websocket_client:
            tool_defs = await instance.websocket_client.list_tools()
            tools_response = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
                for t in tool_defs
            ]
        elif instance.http_client:
            # Via remote HTTP client
            try:
                tool_defs = await instance.http_client.list_tools()
                tools_response = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema,
                    }
                    for t in tool_defs
                ]
            except Exception as e:
                raise MCPConnectionError(f"Remote tool discovery failed: {e}")
        else:
            # Via orchestrator (sandboxed container)
            client = await self._get_http_client()
            try:
                response = await client.post(
                    f"{self.orchestrator_url}/mcp/servers/{instance.container_id}/rpc",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 1,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

                if "error" in result:
                    raise MCPConnectionError(f"Tool discovery failed: {result['error']}")

                tools_response = result.get("result", {}).get("tools", [])
            except httpx.HTTPStatusError as e:
                raise MCPConnectionError(f"Tool discovery request failed: {e}")

        # Convert to MCPToolInfo
        tools = []
        for tool in tools_response:
            tool_name = tool.get("name", "")
            if not tool_name:
                continue

            tools.append(MCPToolInfo(
                tool_id=f"{server_id}.{tool_name}",
                server_id=server_id,
                name=tool_name,
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", {}),
                output_schema=tool.get("outputSchema"),
            ))

        # Cache
        instance.tools = tools
        instance.tools_discovered_at = datetime.utcnow()

        logger.info(
            f"[UnifiedMCPRegistry] Discovered {len(tools)} tools "
            f"from {server_id} for user {user_id}"
        )

        return tools

    async def get_user_tools(
        self,
        user_id: str,
        server_ids: Optional[List[str]] = None,
    ) -> List[MCPToolInfo]:
        """
        Get all tools available to a user.

        Discovers tools from all configured servers.

        Args:
            user_id: User identifier
            server_ids: Optional filter to specific servers

        Returns:
            Combined list of tools from all servers
        """
        servers = await self.get_user_servers(user_id)

        if server_ids:
            servers = [s for s in servers if s.server_id in server_ids]

        all_tools = []

        for server in servers:
            try:
                tools = await self.discover_tools(user_id, server.server_id)
                all_tools.extend(tools)
            except Exception as e:
                logger.warning(
                    f"[UnifiedMCPRegistry] Failed to discover tools from "
                    f"{server.server_id}: {e}"
                )

        return all_tools

    def get_user_tools_sync(self, user_id: str) -> List[MCPToolInfo]:
        """Synchronous wrapper for get_user_tools."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, need to run in thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.get_user_tools(user_id)
                    )
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(self.get_user_tools(user_id))
        except Exception as e:
            logger.error(f"[UnifiedMCPRegistry] Sync get_user_tools failed: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────
    # Tool Execution
    # ─────────────────────────────────────────────────────────────────────

    async def execute_tool(
        self,
        user_id: str,
        tool_id: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool.

        Routes to the correct server based on tool_id prefix.

        Args:
            user_id: User identifier
            tool_id: Full tool ID (format: "{server_id}.{tool_name}")
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        # Parse tool ID - format is "server_type:server_id.tool_name"
        # e.g., "connector:github.create_issue" or "custom:123.search"
        if "." not in tool_id:
            return {"success": False, "error": f"Invalid tool ID: {tool_id}"}

        # Find the last dot to split server_id from tool_name
        last_dot = tool_id.rfind(".")
        server_id = tool_id[:last_dot]
        tool_name = tool_id[last_dot + 1:]

        if not server_id or not tool_name:
            return {"success": False, "error": f"Invalid tool ID format: {tool_id}"}

        # Get or start instance
        try:
            instance = await self.start_server(user_id, server_id)
        except Exception as e:
            return {"success": False, "error": f"Failed to start server: {e}"}

        # Execute tool
        try:
            if instance.websocket_client:
                result = await instance.websocket_client.call_tool(tool_name, arguments)
                instance.request_count += 1
                return {"success": True, "result": result.to_dict() if hasattr(result, 'to_dict') else result}
            elif instance.http_client:
                # Via remote HTTP client
                result = await instance.http_client.call_tool(tool_name, arguments)
                instance.request_count += 1

                # Result is MCPToolCallResult object
                if result.isError:
                    # Extract error message from content
                    error_msg = "Tool execution failed"
                    if result.content:
                        for item in result.content:
                            if item.get("type") == "text":
                                error_msg = item.get("text", error_msg)
                                break
                    return {
                        "success": False,
                        "error": error_msg,
                    }

                return {"success": True, "result": result.to_dict()}
            else:
                # Via orchestrator (sandboxed container)
                client = await self._get_http_client()
                response = await client.post(
                    f"{self.orchestrator_url}/mcp/servers/{instance.container_id}/rpc",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": arguments,
                        },
                        "id": 1,
                    },
                    timeout=120.0,  # Tool execution can take time
                )
                response.raise_for_status()
                rpc_result = response.json()

                if "error" in rpc_result:
                    return {
                        "success": False,
                        "error": rpc_result["error"].get("message", "Unknown error"),
                    }

                instance.request_count += 1
                return {"success": True, "result": rpc_result.get("result")}

        except MCPTimeoutError as e:
            instance.error_count += 1
            return {"success": False, "error": f"Tool execution timed out: {e}"}
        except Exception as e:
            instance.error_count += 1
            logger.error(f"[UnifiedMCPRegistry] Tool execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def execute_tool_by_name(
        self,
        user_id: str,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool by server_id and tool_name separately.

        Args:
            user_id: User identifier
            server_id: Server identifier
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        tool_id = f"{server_id}.{tool_name}"
        return await self.execute_tool(user_id, tool_id, arguments)

    # ─────────────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────────────

    def get_instance_status(
        self,
        user_id: str,
        server_id: str,
    ) -> Optional[ServerStatus]:
        """Get current status of a server instance."""
        with self._lock:
            if user_id not in self._instances:
                return None
            if server_id not in self._instances[user_id]:
                return None
            return self._instances[user_id][server_id].info.status

    async def health_check(self, user_id: str, server_id: str) -> bool:
        """Check if a server is healthy."""
        with self._lock:
            if user_id not in self._instances:
                return False
            if server_id not in self._instances[user_id]:
                return False
            instance = self._instances[user_id][server_id]

        if instance.info.status != ServerStatus.RUNNING:
            return False

        try:
            # Ping the server
            if instance.websocket_client:
                # For WebSocket, check if connected
                return instance.websocket_client.is_connected
            else:
                client = await self._get_http_client()
                response = await client.get(
                    f"{self.orchestrator_url}/mcp/servers/{instance.container_id}/health",
                    timeout=5.0,
                )
                response.raise_for_status()
                result = response.json()
                return result.get("healthy", False)
        except Exception:
            return False

    async def cleanup_idle_instances(self, max_idle_minutes: int = 30):
        """Stop instances that have been idle too long."""
        now = datetime.utcnow()
        idle_threshold = timedelta(minutes=max_idle_minutes)

        to_stop = []

        with self._lock:
            for user_id, servers in self._instances.items():
                for server_id, instance in servers.items():
                    if instance.info.started_at:
                        idle_time = now - instance.info.started_at
                        if idle_time > idle_threshold:
                            to_stop.append((user_id, server_id))

        for user_id, server_id in to_stop:
            await self.stop_server(user_id, server_id)

        if to_stop:
            logger.info(f"[UnifiedMCPRegistry] Cleaned up {len(to_stop)} idle instances")

    def get_running_instances(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get information about running instances."""
        result = []

        with self._lock:
            instances_to_check = self._instances
            if user_id:
                instances_to_check = {user_id: self._instances.get(user_id, {})}

            for uid, servers in instances_to_check.items():
                for server_id, instance in servers.items():
                    result.append({
                        "user_id": uid,
                        "server_id": server_id,
                        "name": instance.info.name,
                        "status": instance.info.status.value,
                        "transport": instance.info.transport.value,
                        "started_at": instance.info.started_at.isoformat() if instance.info.started_at else None,
                        "request_count": instance.request_count,
                        "error_count": instance.error_count,
                        "tools_count": len(instance.tools),
                    })

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Global Registry Instance
# ─────────────────────────────────────────────────────────────────────────────

_mcp_registry: Optional[UnifiedMCPRegistry] = None
_registry_lock = threading.Lock()


def get_mcp_registry() -> UnifiedMCPRegistry:
    """Get the global MCP registry instance."""
    global _mcp_registry

    if _mcp_registry is None:
        with _registry_lock:
            if _mcp_registry is None:
                _mcp_registry = UnifiedMCPRegistry()

    return _mcp_registry


def reset_mcp_registry():
    """Reset the global registry (for testing)."""
    global _mcp_registry
    with _registry_lock:
        if _mcp_registry:
            # Don't await close, just reset
            _mcp_registry = None
