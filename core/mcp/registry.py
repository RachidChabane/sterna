"""MCP Registry for managing a user's active MCP servers and their tools.

Connects to a user's active MCPServer rows over the WebSocket, HTTP, and
STDIO-via-command transports, persisting connection status and discovered
tools (MCPTool rows) to the database. Server-ownership verification runs
only in call_tool_by_name when a user is passed; call_tool performs no
ownership check, so its callers must pre-scope the MCPTool to the
requesting user. For HTTP servers configured with OAuth, it
sends the token already stored on the MCPServer row as a bearer credential;
it does not refresh that token.

unified_registry.py's UnifiedMCPRegistry also loads a user's active
MCPServer rows (for sandboxed npm-package, WebSocket, and remote HTTP
transports), keeping its own connection state in process memory rather
than the database, and independently refreshes OAuth tokens for the
remote HTTP servers it loads.
"""

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from .client import MCPClientBase, create_mcp_client
from .exceptions import MCPConnectionError, MCPError
from .models import MCPServer, MCPTool

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)


def _check_cached_tools_sync(server, cache_threshold):
    """Synchronous helper to check for cached tools."""
    cached_tools = server.tools.filter(last_refreshed__gte=cache_threshold)
    if cached_tools.exists():
        return list(cached_tools)
    return None


def _save_discovered_tools_sync(server, tool_definitions):
    """Synchronous helper to save discovered tools to database."""
    with transaction.atomic():
        # Delete old tools
        server.tools.all().delete()

        # Create new tools
        tools = []
        for tool_def in tool_definitions:
            tool = MCPTool.objects.create(
                server=server,
                name=tool_def.name,
                description=tool_def.description,
                input_schema=tool_def.inputSchema,
                metadata=tool_def.metadata or {},
            )
            tools.append(tool)
    return tools


def _get_active_servers_sync(user):
    """Synchronous helper to get active servers for a user."""
    return list(MCPServer.objects.filter(user=user, is_active=True))


def _get_server_tools_sync(server):
    """Synchronous helper to get all tools for a server."""
    return list(server.tools.all())


def _check_tool_cache_freshness_sync(tools, cache_threshold):
    """Synchronous helper to check if tool cache is fresh."""
    if tools:
        queryset = MCPTool.objects.filter(id__in=[t.id for t in tools])
        if queryset.exists():
            oldest_refresh = queryset.order_by("last_refreshed").first()
            if oldest_refresh and oldest_refresh.last_refreshed >= cache_threshold:
                return True
    return False


class MCPRegistry:
    """Registry for managing MCP servers and their tools.

    The registry maintains connections to MCP servers and manages
    tool discovery and caching.
    """

    def __init__(self):
        """Initialize the MCP registry."""
        self._active_clients: Dict[int, MCPClientBase] = {}
        self._cache_duration = timedelta(hours=1)  # Tool cache duration

    async def connect_server(self, server: MCPServer) -> MCPClientBase:
        """Connect to an MCP server.

        Args:
            server: MCPServer instance to connect to

        Returns:
            Connected MCP client

        Raises:
            MCPConnectionError: If connection fails
        """
        try:
            # Prepare environment variables for stdio servers
            env_vars = {}

            # For stdio servers, use auth_config as environment variables
            # auth_config contains OAuth tokens and other credentials
            if server.transport_type == MCPServer.TransportType.STDIO and server.auth_config:
                # auth_config is a dict like {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}
                # These become environment variables for the stdio process
                env_vars.update(server.auth_config)
                logger.info(f"Using auth_config for {server.name} with {len(env_vars)} env vars")
                # Log env var names (not values for security)
                logger.info(f"Environment variables set: {list(env_vars.keys())}")

            # Create appropriate client based on transport type
            if server.transport_type == MCPServer.TransportType.WEBSOCKET:
                client = create_mcp_client(
                    transport_type="websocket",
                    url=server.url,
                    timeout=120.0,  # 2 minutes for long-running MCP tools
                    auth_config=server.auth_config,
                )
            elif server.transport_type == MCPServer.TransportType.HTTP:
                # HTTP/SSE transport for remote MCP servers
                # Build auth config properly for OAuth servers
                http_auth_config = server.auth_config or {}
                http_auth_type = server.auth_type or "none"

                if http_auth_type == "oauth":
                    # For OAuth servers, use the stored access token as bearer
                    if not server.oauth_access_token:
                        raise MCPConnectionError(
                            f"OAuth server {server.name} requires authorization. Click 'Authorize' first."
                        )
                    http_auth_config = {"token": server.oauth_access_token}
                    http_auth_type = "bearer"  # OAuth tokens are sent as Bearer tokens

                client = create_mcp_client(
                    transport_type="http",
                    url=server.remote_url,
                    timeout=120.0,  # 2 minutes for long-running MCP tools
                    auth_config=http_auth_config,
                    auth_type=http_auth_type,
                )
            elif server.transport_type == MCPServer.TransportType.SANDBOXED:
                # Sandboxed NPM servers - handled via orchestrator
                raise MCPConnectionError(
                    "Sandboxed servers must be started via the orchestrator"
                )
            else:  # STDIO
                client = create_mcp_client(
                    transport_type="stdio",
                    command=server.command,
                    working_directory=server.working_directory or None,
                    env=env_vars,  # Pass OAuth token here
                    timeout=120.0,  # 2 minutes for long-running MCP tools
                    auth_config=server.auth_config,
                )

            # Connect and perform handshake
            await client.connect()
            await client.handshake()

            # Cache the client
            self._active_clients[server.id] = client

            # Mark server as connected (async-safe)
            await sync_to_async(server.mark_connected)()

            logger.info(f"Connected to MCP server: {server.name} (ID: {server.id})")
            return client

        except Exception as e:
            error_msg = str(e)
            # Mark error (async-safe)
            await sync_to_async(server.mark_error)(error_msg)
            logger.error(f"Failed to connect to MCP server {server.name}: {error_msg}")
            raise MCPConnectionError(f"Failed to connect to {server.name}: {error_msg}")

    async def disconnect_server(self, server_id: int) -> None:
        """Disconnect from an MCP server.

        Args:
            server_id: ID of the server to disconnect
        """
        if server_id in self._active_clients:
            client = self._active_clients.pop(server_id)
            await client.disconnect()
            logger.info(f"Disconnected from MCP server (ID: {server_id})")

    async def get_client(self, server: MCPServer) -> MCPClientBase:
        """Get a client for a server, connecting if necessary.

        Args:
            server: MCPServer instance

        Returns:
            Active MCP client

        Raises:
            MCPConnectionError: If connection fails
        """
        if server.id in self._active_clients:
            client = self._active_clients[server.id]
            if client.is_connected:
                return client
            else:
                # Client disconnected, remove it
                self._active_clients.pop(server.id)

        # Connect new client
        return await self.connect_server(server)

    async def discover_tools(
        self,
        server: MCPServer,
        force_refresh: bool = False,
    ) -> List[MCPTool]:
        """Discover tools from an MCP server and cache them.

        Args:
            server: MCPServer to discover tools from
            force_refresh: Force refresh even if cache is valid

        Returns:
            List of discovered tools

        Raises:
            MCPConnectionError: If connection fails
        """
        # Check cache (async-safe)
        if not force_refresh:
            cache_threshold = timezone.now() - self._cache_duration
            cached_tools = await sync_to_async(_check_cached_tools_sync)(server, cache_threshold)
            if cached_tools:
                logger.debug(f"Using cached tools for server {server.name}")
                return cached_tools

        # Discover tools from server
        client = None
        try:
            client = await self.get_client(server)
            tool_definitions = await client.list_tools()

            # Update database (async-safe)
            tools = await sync_to_async(_save_discovered_tools_sync)(server, tool_definitions)

            logger.info(f"Discovered {len(tools)} tools from {server.name}")
            return tools

        except Exception as e:
            logger.error(f"Failed to discover tools from {server.name}: {str(e)}")
            raise
        finally:
            # Disconnect stdio clients after use since they are short-lived processes
            if client and server.transport_type == MCPServer.TransportType.STDIO:
                try:
                    await self.disconnect_server(server.id)
                except Exception as disconnect_error:
                    logger.warning(f"Error disconnecting stdio client for {server.name}: {disconnect_error}")

    async def discover_all_tools(
        self,
        user: "User",
        force_refresh: bool = False,
    ) -> Dict[int, List[MCPTool]]:
        """Discover tools from all active servers for a user.

        Args:
            user: User to discover tools for
            force_refresh: Force refresh even if cache is valid

        Returns:
            Dictionary mapping server ID to list of tools
        """
        # Get servers (async-safe)
        servers = await sync_to_async(_get_active_servers_sync)(user)
        results = {}

        for server in servers:
            try:
                tools = await self.discover_tools(server, force_refresh=force_refresh)
                results[server.id] = tools
            except Exception as e:
                logger.error(f"Failed to discover tools from {server.name}: {str(e)}")
                results[server.id] = []

        return results

    async def get_available_tools(
        self,
        user: "User",
        refresh_if_stale: bool = True,
    ) -> List[MCPTool]:
        """Get all available tools for a user.

        Args:
            user: User to get tools for
            refresh_if_stale: Refresh stale caches automatically

        Returns:
            List of all available tools
        """
        # Get servers (async-safe)
        servers = await sync_to_async(_get_active_servers_sync)(user)
        all_tools = []

        cache_threshold = timezone.now() - self._cache_duration

        for server in servers:
            # Check if cache is stale (async-safe)
            tools = await sync_to_async(_get_server_tools_sync)(server)
            is_fresh = await sync_to_async(_check_tool_cache_freshness_sync)(tools, cache_threshold)

            if is_fresh:
                # Cache is fresh
                all_tools.extend(tools)
                continue

            # Cache is stale or empty
            if refresh_if_stale:
                try:
                    tools = await self.discover_tools(server, force_refresh=True)
                    all_tools.extend(tools)
                except Exception as e:
                    logger.error(f"Failed to refresh tools for {server.name}: {str(e)}")
            else:
                # Use stale cache
                all_tools.extend(tools)

        return all_tools

    async def call_tool(
        self,
        tool: MCPTool,
        arguments: Dict,
    ) -> Dict:
        """Call a tool on its MCP server.

        Args:
            tool: MCPTool to call
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            MCPError: If tool call fails
        """
        client = None
        try:
            client = await self.get_client(tool.server)
            result = await client.call_tool(tool.name, arguments)

            if result.isError:
                # Extract error message from content
                error_msg = "Tool execution failed"
                if result.content:
                    error_msg = str(result.content[0].get("text", error_msg))
                raise MCPError(error_msg)

            # Convert content to dictionary
            return {
                "content": result.content,
                "is_error": result.isError,
            }

        except Exception as e:
            logger.error(f"Failed to call tool {tool.name}: {str(e)}")
            raise
        finally:
            # Disconnect stdio clients after use since they are short-lived processes
            if client and tool.server.transport_type == MCPServer.TransportType.STDIO:
                try:
                    await self.disconnect_server(tool.server.id)
                except Exception as disconnect_error:
                    logger.warning(f"Error disconnecting stdio client for {tool.server.name}: {disconnect_error}")

    async def call_tool_by_name(
        self,
        tool_name: str,
        server_id: str,
        server_transport_type: str,
        arguments: Dict,
        user=None,  # Optional user for security verification
    ) -> Dict:
        """Call a tool by name on an MCP server.

        Args:
            tool_name: Name of the tool to call
            server_id: UUID of the MCPServer
            server_transport_type: Transport type ('websocket' or 'stdio')
            arguments: Tool arguments
            user: User object for security verification (defense-in-depth)

        Returns:
            Tool result

        Raises:
            MCPError: If tool call fails
            PermissionError: If user verification fails
        """
        from asgiref.sync import sync_to_async
        from .models import MCPServer

        client = None
        try:
            # Load server from database in async context
            server = await sync_to_async(MCPServer.objects.get)(id=server_id)

            # Defense-in-depth: Verify server belongs to user if provided
            if user is not None and server.user_id != user.id:
                raise PermissionError(
                    f"User {user.id} attempted to access server {server_id} owned by {server.user_id}"
                )

            client = await self.get_client(server)
            result = await client.call_tool(tool_name, arguments)

            if result.isError:
                # Extract error message from content
                error_msg = "Tool execution failed"
                if result.content:
                    error_msg = str(result.content[0].get("text", error_msg))
                raise MCPError(error_msg)

            # Convert content to dictionary
            return {
                "content": result.content,
                "is_error": result.isError,
            }

        except Exception as e:
            logger.error(f"Failed to call tool {tool_name}: {str(e)}")
            raise
        finally:
            # Disconnect stdio clients after use since they are short-lived processes
            if client and server_transport_type == 'stdio':
                try:
                    await self.disconnect_server(int(server_id))
                except Exception as disconnect_error:
                    logger.warning(f"Error disconnecting stdio client: {disconnect_error}")

    async def health_check(self, server: MCPServer, update_status: bool = True) -> bool:
        """Check if a server is healthy and optionally update its health status.

        Args:
            server: Server to check
            update_status: Whether to update server's health check fields in database

        Returns:
            True if server is healthy, False otherwise
        """
        client = None
        try:
            client = await self.get_client(server)
            # Try to list tools as a health check
            await client.list_tools()

            # Update health status in database if requested
            if update_status:
                await sync_to_async(server.mark_connected)()

            logger.info(f"Health check passed for {server.name}")
            return True
        except Exception as e:
            # Update health status in database if requested
            if update_status:
                error_msg = str(e)
                await sync_to_async(server.mark_error)(error_msg)

            logger.warning(f"Health check failed for {server.name}: {str(e)}")
            return False
        finally:
            # Disconnect stdio clients after use since they are short-lived processes
            if client and server.transport_type == MCPServer.TransportType.STDIO:
                try:
                    await self.disconnect_server(server.id)
                except Exception as disconnect_error:
                    logger.warning(f"Error disconnecting stdio client for {server.name}: {disconnect_error}")

    async def cleanup(self) -> None:
        """Disconnect all clients and clean up resources."""
        for server_id in list(self._active_clients.keys()):
            await self.disconnect_server(server_id)
        logger.info("MCP Registry cleaned up")

    def get_available_tools_sync(self, user):
        """Get available tools for a user (synchronous version for Django views).

        This method only retrieves cached tools from the database without
        making any network calls. Use this in synchronous contexts like Django views.

        IMPORTANT: Only returns tools from servers the user has actually connected to.
        Preconfigured servers are NOT included unless the user has a connected copy.
        Tool discovery (showing what's available to connect to) is handled separately
        by the Tool Catalog system.

        Args:
            user: User to get tools for

        Returns:
            List of MCPTool instances
        """
        from .models import MCPTool

        # Get only the user's own active servers
        # Do NOT include preconfigured servers - those are for discovery only
        # Users must explicitly connect to preconfigured servers to use their tools
        active_servers = MCPServer.objects.filter(
            user=user,
            is_active=True
        )

        # Get all cached tools from these servers
        tools = MCPTool.objects.filter(server__in=active_servers)

        logger.debug(f"Retrieved {tools.count()} cached tools for user {user.id}")
        return list(tools)


# Global registry instance
_registry: Optional[MCPRegistry] = None


def get_registry() -> MCPRegistry:
    """Get the global MCP registry instance.

    Returns:
        Global MCPRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry


async def cleanup_registry() -> None:
    """Clean up the global registry."""
    global _registry
    if _registry is not None:
        await _registry.cleanup()
        _registry = None
