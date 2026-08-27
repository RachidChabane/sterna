"""API views for MCP integration."""

import asyncio
import logging
import threading

from asgiref.sync import sync_to_async
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.views import View
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


from .exceptions import MCPError, MCPConnectionError
from .models import (
    MCPDiscoverySearch,
    MCPServer,
    MCPTool,
    MCPToolApproval,
    MCPToolExecution,
)
from .registry import get_registry
from .serializers import (
    ApproveToolRequestSerializer,
    CallToolRequestSerializer,
    DiscoverToolsRequestSerializer,
    MCPDiscoverySearchSerializer,
    MCPServerSerializer,
    MCPServerCreateSerializer,
    MCPToolApprovalSerializer,
    MCPToolExecutionSerializer,
    MCPToolSerializer,
    RejectToolRequestSerializer,
    TestConnectionRequestSerializer,
)

logger = logging.getLogger(__name__)


def run_async_in_new_thread(coro):
    """Run an async coroutine in a new thread with its own event loop.

    This is necessary because Django may have an existing event loop in some contexts,
    and async_to_sync() fails when called from an async context.

    Args:
        coro: Coroutine to run

    Returns:
        Result from the coroutine
    """
    result_container = {}
    exception_container = {}

    def run_in_thread():
        try:
            logger.debug("Creating new event loop in thread")
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                logger.debug("Running coroutine in new event loop")
                result_container['result'] = loop.run_until_complete(coro)
                logger.debug("Coroutine completed successfully")
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Exception in async thread: {str(e)}", exc_info=True)
            exception_container['exception'] = e

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()

    if 'exception' in exception_container:
        raise exception_container['exception']

    return result_container.get('result')


class MCPServerViewSet(viewsets.ModelViewSet):
    """ViewSet for managing MCP servers.

    Supports both OAuth-connected servers and custom npm-based servers.

    Custom servers can be created with:
    - npm_package: NPM package name (e.g., '@modelcontextprotocol/server-github')
    - env_vars: Environment variables (API keys, tokens)
    - allowed_domains: Custom domains for network egress whitelist
    """

    serializer_class = MCPServerSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """Use different serializers for create vs other actions."""
        if self.action == 'create':
            return MCPServerCreateSerializer
        return MCPServerSerializer

    def perform_create(self, serializer):
        """Create server and automatically discover tools.

        After creating the server, immediately triggers tool discovery
        so tools are available for the LLM to find.
        """
        server = serializer.save()
        logger.info(f"Created MCP server {server.name}, triggering tool discovery...")

        # Trigger tool discovery in background
        # This ensures tools are immediately available after server creation
        self._discover_tools_for_server(server, self.request)

    def _discover_tools_for_server(self, server, request):
        """Discover tools for a newly created server.

        This is called automatically after server creation to ensure
        tools are immediately available.
        """
        try:
            if server.npm_package:
                # NPM-based server - use orchestrator
                self._discover_npm_server_tools(server, request)
            elif server.remote_url:
                # Remote HTTP server
                self._discover_remote_server_tools(server)
            else:
                # WebSocket or other - use V1 registry
                self._discover_registry_tools(server)
        except Exception as e:
            logger.warning(f"Auto tool discovery failed for {server.name}: {e}")
            # Don't fail the creation - tools can be discovered later

    def _discover_npm_server_tools(self, server, request):
        """Discover tools from npm-based server via orchestrator.

        IMPORTANT: If this server is based on a preconfigured server (same npm_package),
        tools are saved to the PRECONFIGURED server globally, not the user's copy.
        This allows all users to see available tools without connecting.
        """
        import httpx
        from django.conf import settings
        from django.db import transaction

        orchestrator_url = getattr(settings, 'ORCHESTRATOR_URL', 'http://sterna-orchestrator:8003')
        auth_header = request.headers.get('Authorization', '')

        logger.info(f"Auto-discovering tools for npm server {server.name}")

        # Start server in sandbox
        start_response = httpx.post(
            f"{orchestrator_url}/mcp/servers",
            json={
                "server_id": str(server.id),
                "npm_package": server.npm_package,
                "env_vars": server.get_effective_env_vars(),
                "allowed_domains": server.allowed_domains or [],
            },
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

        if start_response.status_code != 200:
            logger.warning(f"Failed to start server for tool discovery: {start_response.text}")
            return

        server_id = start_response.json().get("server_id")

        # Discover tools
        tools_response = httpx.get(
            f"{orchestrator_url}/mcp/servers/{server_id}/tools",
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

        if tools_response.status_code != 200:
            logger.warning(f"Failed to discover tools: {tools_response.text}")
            return

        discovered_tools = tools_response.json()
        logger.info(f"Auto-discovered {len(discovered_tools)} tools from {server.name}")

        # Find preconfigured server with same npm_package
        # Tools are stored GLOBALLY on preconfigured server so all users can see them
        preconfigured_server = MCPServer.objects.filter(
            npm_package=server.npm_package,
            is_preconfigured=True,
        ).first()

        # Save tools to preconfigured server if found, otherwise to user's server
        target_server = preconfigured_server if preconfigured_server else server

        with transaction.atomic():
            # Clear existing tools and refresh
            target_server.tools.all().delete()

            for tool_data in discovered_tools:
                MCPTool.objects.create(
                    server=target_server,
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    metadata={},
                )

        if preconfigured_server:
            logger.info(
                f"Updated {len(discovered_tools)} tools globally on preconfigured server "
                f"'{preconfigured_server.name}' (triggered by user connecting)"
            )
        else:
            logger.info(f"Saved {len(discovered_tools)} tools to custom server {server.name}")

    def _discover_remote_server_tools(self, server):
        """Discover tools from remote HTTP server.

        IMPORTANT: If this server is based on a preconfigured server (same remote_url),
        tools are saved to the PRECONFIGURED server globally, not the user's copy.
        This allows all users to see available tools without connecting.
        """
        from .client import MCPRemoteHTTPClient
        from django.db import transaction

        logger.info(f"Auto-discovering tools for remote server {server.name}")

        async def discover():
            auth_config = server.auth_config or {}
            auth_type = server.auth_type or "none"

            if auth_type == "oauth" and server.oauth_access_token:
                auth_config = {"token": server.oauth_access_token}
                auth_type = "bearer"

            client = MCPRemoteHTTPClient(
                url=server.remote_url,
                timeout=60.0,
                auth_config=auth_config,
                auth_type=auth_type,
                auth_header=server.auth_header_name or "Authorization",
            )
            try:
                await client.connect()
                await client.handshake()
                tools_response = await client.call("tools/list", {})
                return tools_response.get("tools", [])
            finally:
                await client.disconnect()

        discovered_tools = run_async_in_new_thread(discover())
        logger.info(f"Auto-discovered {len(discovered_tools)} tools from {server.name}")

        # Find preconfigured server with same remote_url
        # Tools are stored GLOBALLY on preconfigured server so all users can see them
        preconfigured_server = MCPServer.objects.filter(
            remote_url=server.remote_url,
            is_preconfigured=True,
        ).first()

        # Save tools to preconfigured server if found, otherwise to user's server
        target_server = preconfigured_server if preconfigured_server else server

        with transaction.atomic():
            # Clear existing tools and refresh
            target_server.tools.all().delete()

            for tool_data in discovered_tools:
                MCPTool.objects.create(
                    server=target_server,
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    metadata={},
                )

        if preconfigured_server:
            logger.info(
                f"Updated {len(discovered_tools)} tools globally on preconfigured server "
                f"'{preconfigured_server.name}' (triggered by user connecting)"
            )
        else:
            logger.info(f"Saved {len(discovered_tools)} tools to custom server {server.name}")

        server.mark_connected()

    def _discover_registry_tools(self, server):
        """Discover tools using V1 registry."""
        registry = get_registry()
        run_async_in_new_thread(registry.discover_tools(server, force_refresh=True))

    def get_queryset(self):
        """Filter servers by current user (excludes preconfigured servers)."""
        queryset = MCPServer.objects.filter(user=self.request.user).order_by("-created_at")

        # Optional filter for custom servers only (those with npm_package)
        custom_only = self.request.query_params.get('custom_only')
        if custom_only and custom_only.lower() == 'true':
            queryset = queryset.exclude(npm_package='')

        # Optional filter for OAuth servers only
        oauth_only = self.request.query_params.get('oauth_only')
        if oauth_only and oauth_only.lower() == 'true':
            queryset = queryset.filter(npm_package='')

        return queryset

    def _get_server_or_preconfigured(self, pk):
        """Get server by ID, allowing both user-owned and preconfigured servers.

        For OAuth actions, we need to allow access to preconfigured servers
        because users need to discover OAuth config before creating their copy.

        Args:
            pk: Server primary key

        Returns:
            MCPServer instance

        Raises:
            Http404 if server not found or not accessible
        """
        from django.db.models import Q
        from django.shortcuts import get_object_or_404

        # Allow user's own servers OR preconfigured servers
        return get_object_or_404(
            MCPServer.objects.filter(
                Q(user=self.request.user) | Q(is_preconfigured=True)
            ),
            pk=pk
        )

    def _get_or_create_user_copy(self, preconfigured_server):
        """Get or create a user's copy of a preconfigured server.

        When a user wants to connect to a preconfigured server (like Notion),
        we create a copy for them that will store their OAuth tokens.

        Args:
            preconfigured_server: The preconfigured MCPServer instance

        Returns:
            MCPServer instance owned by the current user
        """
        # Check if user already has a copy (match by remote_url or npm_package)
        existing = None
        if preconfigured_server.remote_url:
            existing = MCPServer.objects.filter(
                user=self.request.user,
                remote_url=preconfigured_server.remote_url,
            ).first()
        elif preconfigured_server.npm_package:
            existing = MCPServer.objects.filter(
                user=self.request.user,
                npm_package=preconfigured_server.npm_package,
            ).first()

        if existing:
            logger.info(
                f"Found existing user copy of preconfigured server "
                f"'{preconfigured_server.name}' for user {self.request.user.id}"
            )
            return existing

        # Create a new user copy
        user_server = MCPServer.objects.create(
            user=self.request.user,
            name=preconfigured_server.name,
            description=preconfigured_server.description,
            icon_url=preconfigured_server.icon_url,
            icon_invert_in_dark_mode=preconfigured_server.icon_invert_in_dark_mode,
            docs_url=preconfigured_server.docs_url,
            category=preconfigured_server.category,
            transport_type=preconfigured_server.transport_type,
            url=preconfigured_server.url,
            npm_package=preconfigured_server.npm_package,
            remote_url=preconfigured_server.remote_url,
            auth_type=preconfigured_server.auth_type,
            auth_header_name=preconfigured_server.auth_header_name,
            oauth_metadata=preconfigured_server.oauth_metadata,
            allowed_domains=preconfigured_server.allowed_domains,
            is_active=True,
            is_preconfigured=False,  # User's copy is NOT preconfigured
        )

        logger.info(
            f"Created user copy (ID: {user_server.id}) of preconfigured server "
            f"'{preconfigured_server.name}' for user {self.request.user.id}"
        )

        return user_server

    def destroy(self, request, *args, **kwargs):
        """Delete a server and invalidate tool caches.

        When a server is deleted, we need to clear the tool catalog cache
        so stale tool IDs don't remain in the system.
        """
        instance = self.get_object()
        user_id = str(request.user.id)

        # Invalidate tool caches before deletion
        try:
            from llm.tool_catalog.registry import get_tool_catalog
            from mcp.tool_discovery_adapter import get_mcp_adapter

            # Clear tool catalog cache for this user
            catalog = get_tool_catalog()
            catalog.invalidate_user_tools_cache(user_id)

            # Clear MCP adapter cache for this user
            adapter = get_mcp_adapter()
            adapter.clear_user_cache(user_id)

            logger.info(f"[MCPServer] Invalidated tool caches for user {user_id} (server {instance.id} deleted)")
        except Exception as e:
            logger.warning(f"[MCPServer] Failed to invalidate caches on delete: {e}")

        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def preconfigured(self, request):
        """List all preconfigured MCP servers.

        GET /api/mcp/servers/preconfigured/

        Returns all preconfigured servers available to all users.
        No pagination - returns all servers for client-side filtering/grouping.
        """
        from .serializers import MCPServerPreconfiguredSerializer

        queryset = MCPServer.objects.filter(
            is_preconfigured=True,
            is_active=True,
        ).order_by('category', 'name')

        # Search filter
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        # Category filter
        category = request.query_params.get('category', '').strip()
        if category:
            queryset = queryset.filter(category=category)

        # Return all results without pagination for client-side grouping
        serializer = MCPServerPreconfiguredSerializer(queryset, many=True)
        return Response({
            "results": serializer.data,
            "count": len(serializer.data),
        })

    @action(detail=True, methods=["post"])
    def start_sandbox(self, request, pk=None):
        """Start the MCP server in a sandboxed container.

        POST /api/mcp/servers/{id}/start_sandbox/

        Only works for servers with npm_package configured.
        Returns container_id for the running server.
        """
        server = self.get_object()

        if not server.npm_package:
            return Response(
                {
                    "status": "error",
                    "message": "Only npm-based servers can be started in sandbox",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Call orchestrator to start the server
            import httpx
            from django.conf import settings

            orchestrator_url = getattr(settings, 'ORCHESTRATOR_URL', 'http://sterna-orchestrator:8003')

            # Get the JWT token for the request
            auth_header = request.headers.get('Authorization', '')

            response = httpx.post(
                f"{orchestrator_url}/mcp/servers",
                json={
                    "server_id": str(server.id),
                    "npm_package": server.npm_package,
                    "env_vars": server.get_effective_env_vars(),
                    "allowed_domains": server.allowed_domains or [],
                },
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )

            if response.status_code == 200:
                result = response.json()
                return Response({
                    "status": "success",
                    "message": "Server started in sandbox",
                    "container_id": result.get("container_id"),
                    "container_name": result.get("container_name"),
                })
            else:
                error_msg = response.json().get("detail", "Unknown error")
                return Response(
                    {
                        "status": "error",
                        "message": f"Failed to start server: {error_msg}",
                    },
                    status=response.status_code,
                )

        except Exception as e:
            logger.error(f"Failed to start sandbox for server {server.name}: {str(e)}")
            return Response(
                {
                    "status": "error",
                    "message": f"Failed to start sandbox: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def stop_sandbox(self, request, pk=None):
        """Stop the MCP server sandbox container.

        POST /api/mcp/servers/{id}/stop_sandbox/
        {
            "container_id": "..."
        }
        """
        server = self.get_object()
        container_id = request.data.get("container_id")

        if not container_id:
            return Response(
                {
                    "status": "error",
                    "message": "container_id is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            import httpx
            from django.conf import settings

            orchestrator_url = getattr(settings, 'ORCHESTRATOR_URL', 'http://sterna-orchestrator:8003')
            auth_header = request.headers.get('Authorization', '')

            response = httpx.delete(
                f"{orchestrator_url}/mcp/servers/{container_id}",
                headers={
                    "Authorization": auth_header,
                },
                timeout=30.0,
            )

            if response.status_code == 200:
                return Response({
                    "status": "success",
                    "message": "Server stopped",
                })
            else:
                error_msg = response.json().get("detail", "Unknown error")
                return Response(
                    {
                        "status": "error",
                        "message": f"Failed to stop server: {error_msg}",
                    },
                    status=response.status_code,
                )

        except Exception as e:
            logger.error(f"Failed to stop sandbox for server {server.name}: {str(e)}")
            return Response(
                {
                    "status": "error",
                    "message": f"Failed to stop sandbox: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def test_connection(self, request, pk=None):
        """Test connection to an MCP server.

        POST /api/mcp/servers/{id}/test_connection/
        """
        server = self.get_object()
        serializer = TestConnectionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            registry = get_registry()
            is_healthy = run_async_in_new_thread(registry.health_check(server, update_status=False))

            if is_healthy:
                return Response({
                    "status": "success",
                    "message": "Successfully connected to MCP server",
                })
            else:
                return Response(
                    {
                        "status": "error",
                        "message": "Failed to connect to MCP server",
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        except Exception as e:
            logger.error(f"Connection test failed for server {server.name}: {str(e)}")
            return Response(
                {
                    "status": "error",
                    "message": f"Connection test failed: {str(e)}",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=True, methods=["post"])
    def health_check(self, request, pk=None):
        """Perform health check and update connection status.

        POST /api/mcp/servers/{id}/health_check/

        This endpoint performs a health check on the MCP server and updates
        the last_health_check and connection_healthy fields. Use this to
        verify connection status and refresh the connection state.
        """
        server = self.get_object()

        try:
            registry = get_registry()
            is_healthy = run_async_in_new_thread(registry.health_check(server, update_status=True))

            # Refresh from database to get updated fields
            server.refresh_from_db()

            # Return updated server data
            return Response({
                "status": "success",
                "is_healthy": is_healthy,
                "server": MCPServerSerializer(server, context={'request': request}).data,
            })

        except Exception as e:
            logger.error(f"Health check failed for server {server.name}: {str(e)}")
            # Even on error, return the updated server state
            server.refresh_from_db()
            return Response(
                {
                    "status": "error",
                    "message": f"Health check failed: {str(e)}",
                    "is_healthy": False,
                    "server": MCPServerSerializer(server, context={'request': request}).data,
                },
                status=status.HTTP_200_OK,  # Still 200 because the endpoint worked
            )

    @action(detail=True, methods=["post"])
    def discover_tools(self, request, pk=None):
        """Discover tools from an MCP server.

        POST /api/mcp/servers/{id}/discover_tools/
        {
            "force_refresh": true
        }

        For npm-based servers (custom servers), this uses the sandbox orchestrator.
        For OAuth servers with command, this uses the local V1 registry.
        """
        server = self.get_object()
        serializer = DiscoverToolsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Check if this is an npm-based server (custom server)
            if server.npm_package:
                # Use sandbox orchestrator for npm-based servers
                import httpx
                from django.conf import settings
                from django.db import transaction

                orchestrator_url = getattr(settings, 'ORCHESTRATOR_URL', 'http://sterna-orchestrator:8003')
                auth_header = request.headers.get('Authorization', '')

                logger.info(f"Starting tool discovery for npm server {server.name} via sandbox orchestrator")

                # Step 1: Start the server in sandbox
                start_response = httpx.post(
                    f"{orchestrator_url}/mcp/servers",
                    json={
                        "server_id": str(server.id),
                        "npm_package": server.npm_package,
                        "env_vars": server.get_effective_env_vars(),
                        "allowed_domains": server.allowed_domains or [],
                    },
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": "application/json",
                    },
                    timeout=60.0,
                )

                if start_response.status_code != 200:
                    error_msg = start_response.json().get("detail", "Failed to start server")
                    return Response(
                        {"status": "error", "message": f"Failed to start server: {error_msg}"},
                        status=start_response.status_code,
                    )

                server_id = start_response.json().get("server_id")
                logger.info(f"Server started with server_id: {server_id}")

                # Step 2: Discover tools via tools endpoint
                tools_response = httpx.get(
                    f"{orchestrator_url}/mcp/servers/{server_id}/tools",
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": "application/json",
                    },
                    timeout=60.0,
                )

                if tools_response.status_code != 200:
                    error_msg = tools_response.json().get("detail", "Failed to discover tools")
                    return Response(
                        {"status": "error", "message": f"Failed to discover tools: {error_msg}"},
                        status=tools_response.status_code,
                    )

                # Tools endpoint returns array of tools directly
                discovered_tools = tools_response.json()
                logger.info(f"Discovered {len(discovered_tools)} tools from orchestrator")

                # Step 3: Save discovered tools to database
                # Find preconfigured server with same npm_package - save tools globally
                preconfigured_server = MCPServer.objects.filter(
                    npm_package=server.npm_package,
                    is_preconfigured=True,
                ).first()

                target_server = preconfigured_server if preconfigured_server else server

                with transaction.atomic():
                    target_server.tools.all().delete()

                    tools = []
                    for tool_data in discovered_tools:
                        tool = MCPTool.objects.create(
                            server=target_server,
                            name=tool_data.get("name", ""),
                            description=tool_data.get("description", ""),
                            input_schema=tool_data.get("inputSchema", {}),
                            metadata={},
                        )
                        tools.append(tool)

                if preconfigured_server:
                    logger.info(
                        f"Updated {len(tools)} tools globally on preconfigured server "
                        f"'{preconfigured_server.name}'"
                    )
                else:
                    logger.info(f"Successfully discovered {len(tools)} tools from npm server")

                return Response({
                    "status": "success",
                    "message": f"Discovered {len(tools)} tools",
                    "tools": MCPToolSerializer(tools, many=True).data,
                })
            elif server.remote_url:
                # Remote HTTP server - connect directly
                from .client import MCPRemoteHTTPClient
                from django.db import transaction

                logger.info(f"Starting tool discovery for remote HTTP server {server.name} at {server.remote_url}")

                async def discover_remote_tools():
                    # Build auth config - for OAuth, use the stored access token
                    auth_config = server.auth_config or {}
                    auth_type = server.auth_type or "none"

                    if auth_type == "oauth":
                        # For OAuth servers, use the stored access token as bearer
                        if not server.oauth_access_token:
                            raise MCPConnectionError("OAuth server requires authorization. Click 'Authorize' first.")

                        # Auto-refresh expired tokens before discovery
                        if server.oauth_needs_refresh:
                            logger.info(f"OAuth token expired for server {server.id}, attempting refresh...")
                            from .oauth import MCPDynamicOAuthFlow
                            oauth_flow = MCPDynamicOAuthFlow()
                            refresh_success = await oauth_flow.refresh_server_token(server)
                            if not refresh_success:
                                raise MCPConnectionError(
                                    "OAuth token expired and refresh failed. Please re-authorize the connection."
                                )
                            # Reload server to get the new token
                            await sync_to_async(server.refresh_from_db)()
                            logger.info(f"Token refreshed successfully for server {server.id}")

                        auth_config = {"token": server.oauth_access_token}
                        auth_type = "bearer"  # OAuth tokens are sent as Bearer tokens

                    client = MCPRemoteHTTPClient(
                        url=server.remote_url,
                        timeout=60.0,
                        auth_config=auth_config,
                        auth_type=auth_type,
                        auth_header=server.auth_header_name or "Authorization",
                    )
                    try:
                        await client.connect()
                        await client.handshake()
                        tools_response = await client.call("tools/list", {})
                        return tools_response.get("tools", [])
                    finally:
                        await client.disconnect()

                discovered_tools = run_async_in_new_thread(discover_remote_tools())
                logger.info(f"Discovered {len(discovered_tools)} tools from remote server")

                # Find preconfigured server with same remote_url - save tools globally
                preconfigured_server = MCPServer.objects.filter(
                    remote_url=server.remote_url,
                    is_preconfigured=True,
                ).first()

                target_server = preconfigured_server if preconfigured_server else server

                # Save discovered tools to database
                with transaction.atomic():
                    target_server.tools.all().delete()

                    tools = []
                    for tool_data in discovered_tools:
                        tool = MCPTool.objects.create(
                            server=target_server,
                            name=tool_data.get("name", ""),
                            description=tool_data.get("description", ""),
                            input_schema=tool_data.get("inputSchema", {}),
                            metadata={},
                        )
                        tools.append(tool)

                if preconfigured_server:
                    logger.info(
                        f"Updated {len(tools)} tools globally on preconfigured server "
                        f"'{preconfigured_server.name}'"
                    )

                # Mark server as connected
                server.mark_connected()

                return Response({
                    "status": "success",
                    "message": f"Discovered {len(tools)} tools",
                    "tools": MCPToolSerializer(tools, many=True).data,
                })
            else:
                # Use V1 registry for OAuth servers with command
                registry = get_registry()
                logger.info(f"Starting tool discovery for server {server.name}")
                tools = run_async_in_new_thread(
                    registry.discover_tools(
                        server,
                        force_refresh=serializer.validated_data["force_refresh"],
                    )
                )
                logger.info(f"Successfully discovered {len(tools)} tools")

                return Response({
                    "status": "success",
                    "message": f"Discovered {len(tools)} tools",
                    "tools": MCPToolSerializer(tools, many=True).data,
                })

        except Exception as e:
            logger.error(f"Tool discovery failed for server {server.name}: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "message": f"Tool discovery failed: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"])
    def discover_all(self, request):
        """Discover tools from all active servers.

        POST /api/mcp/servers/discover_all/
        {
            "force_refresh": false
        }
        """
        serializer = DiscoverToolsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            registry = get_registry()
            results = run_async_in_new_thread(
                registry.discover_all_tools(
                    request.user,
                    force_refresh=serializer.validated_data["force_refresh"],
                )
            )

            total_tools = sum(len(tools) for tools in results.values())

            return Response({
                "status": "success",
                "message": f"Discovered {total_tools} tools from {len(results)} servers",
                "results": {
                    str(server_id): MCPToolSerializer(tools, many=True).data
                    for server_id, tools in results.items()
                },
            })

        except Exception as e:
            logger.error(f"Bulk tool discovery failed: {str(e)}")
            return Response(
                {
                    "status": "error",
                    "message": f"Bulk tool discovery failed: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ========== Dynamic OAuth Endpoints ==========

    @action(detail=True, methods=["post"], url_path="oauth/discover")
    def oauth_discover(self, request, pk=None):
        """Discover OAuth configuration for a remote MCP server.

        POST /api/mcp/servers/{id}/oauth/discover/

        Fetches OAuth metadata from the server's /.well-known/oauth-authorization-server
        endpoint. Returns OAuth capabilities including whether dynamic client
        registration is supported.

        Note: This action allows access to preconfigured servers because users
        need to discover OAuth config before creating their connected copy.

        Returns:
            {
                "status": "success",
                "metadata": { ... OAuth metadata ... },
                "supports_dynamic_registration": bool,
                "requires_manual_client_id": bool
            }
        """
        # Use helper that allows preconfigured servers
        server = self._get_server_or_preconfigured(pk)

        if server.auth_type != 'oauth':
            return Response(
                {"error": "Server is not configured for OAuth authentication"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not server.remote_url:
            return Response(
                {"error": "Server must have a remote_url configured for OAuth"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .oauth import DynamicOAuthDiscoveryService

            discovery = DynamicOAuthDiscoveryService()
            metadata = run_async_in_new_thread(discovery.discover(server.remote_url))

            # Cache metadata on server
            server.oauth_metadata = metadata.to_dict()
            server.save(update_fields=['oauth_metadata'])

            return Response({
                "status": "success",
                "metadata": metadata.to_dict(),
                "supports_dynamic_registration": metadata.supports_dynamic_registration,
                "requires_manual_client_id": not metadata.supports_dynamic_registration,
            })

        except Exception as e:
            logger.error(f"OAuth discovery failed for server {server.name}: {str(e)}")
            return Response(
                {"error": f"OAuth discovery failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="oauth/authorize")
    def oauth_authorize(self, request, pk=None):
        """Start OAuth authorization flow for a server.

        POST /api/mcp/servers/{id}/oauth/authorize/
        {
            "client_id": "...",      // Required if server doesn't support dynamic registration
            "client_secret": "..."   // Optional
        }

        Returns authorization URL to redirect user to.

        Note: If authorizing on a preconfigured server, this will create a user
        copy first (or find an existing one) and authorize on that copy.

        Returns:
            {
                "status": "success",
                "authorization_url": "https://...",
                "state": "...",
                "server_id": int  // The user's server ID (may be different from pk if preconfigured)
            }
        """
        # Use helper that allows preconfigured servers
        server = self._get_server_or_preconfigured(pk)

        if server.auth_type != 'oauth':
            return Response(
                {"error": "Server is not configured for OAuth authentication"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # If this is a preconfigured server, create or find user's copy
        if server.is_preconfigured:
            user_server = self._get_or_create_user_copy(server)
            server = user_server

        client_id = request.data.get('client_id', '')
        client_secret = request.data.get('client_secret', '')

        try:
            from .oauth import MCPDynamicOAuthFlow, DynamicOAuthFlowError

            flow = MCPDynamicOAuthFlow()
            result = run_async_in_new_thread(
                flow.start_authorization(server, client_id, client_secret)
            )

            return Response({
                "status": "success",
                "authorization_url": result['authorization_url'],
                "state": result['state'],
                "server_id": server.id,  # Return user's server ID
            })

        except DynamicOAuthFlowError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"OAuth authorization failed for server {server.name}: {str(e)}")
            return Response(
                {"error": f"OAuth authorization failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="oauth/disconnect")
    def oauth_disconnect(self, request, pk=None):
        """Disconnect OAuth and clear tokens for a server.

        POST /api/mcp/servers/{id}/oauth/disconnect/

        Clears all OAuth tokens and metadata. User will need to re-authorize.
        """
        server = self.get_object()

        if server.auth_type != 'oauth':
            return Response(
                {"error": "Server is not configured for OAuth authentication"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        server.clear_oauth_tokens()

        return Response({
            "status": "success",
            "message": "OAuth tokens cleared. Re-authorization required.",
        })

    @action(detail=True, methods=["post"], url_path="oauth/refresh")
    def oauth_refresh(self, request, pk=None):
        """Manually refresh OAuth token for a server.

        POST /api/mcp/servers/{id}/oauth/refresh/

        Attempts to refresh the access token using the refresh token.
        """
        server = self.get_object()

        if server.auth_type != 'oauth':
            return Response(
                {"error": "Server is not configured for OAuth authentication"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not server.oauth_refresh_token:
            return Response(
                {"error": "No refresh token available. Re-authorization required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .oauth import MCPDynamicOAuthFlow

            flow = MCPDynamicOAuthFlow()
            success = run_async_in_new_thread(flow.refresh_server_token(server))

            if success:
                server.refresh_from_db()
                return Response({
                    "status": "success",
                    "message": "Token refreshed successfully",
                    "expires_at": server.oauth_token_expires_at.isoformat() if server.oauth_token_expires_at else None,
                })
            else:
                return Response(
                    {"error": "Token refresh failed. Re-authorization may be required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except Exception as e:
            logger.error(f"OAuth token refresh failed for server {server.name}: {str(e)}")
            return Response(
                {"error": f"Token refresh failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="config-help")
    def config_help(self, request):
        """Get configuration help for an MCP server.

        POST /api/mcp/servers/config-help/
        {
            "npm_package": "@modelcontextprotocol/server-github",  (for local servers)
            "remote_url": "https://mcp.zapier.com/api/mcp",  (for remote servers)
            "server_name": "GitHub",
            "github_url": "https://github.com/..."  (optional, for documentation)
        }

        Uses LLM to extract configuration requirements from the server's README or web search.
        Returns env vars needed, auth info, setup steps, etc.
        """
        from .config_helper import get_config_help

        npm_package = request.data.get("npm_package", "")
        remote_url = request.data.get("remote_url", "")
        server_name = request.data.get("server_name", npm_package or "MCP Server")
        github_url = request.data.get("github_url", "")

        if not npm_package and not github_url and not remote_url:
            return Response(
                {"error": "Please provide a package name or server URL"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            config_help = run_async_in_new_thread(
                get_config_help(
                    server_name=server_name,
                    npm_package=npm_package or None,
                    remote_url=remote_url or None,
                    github_url=github_url or None,
                    user=request.user,
                )
            )

            return Response({
                "server_name": config_help.server_name,
                "env_vars": [
                    {
                        "name": ev.name,
                        "label": ev.label,
                        "description": ev.description,
                        "required": ev.required,
                        "secret": ev.secret,
                        "example": ev.example,
                        "docs_url": ev.docs_url,
                    }
                    for ev in config_help.env_vars
                ],
                "auth_info": config_help.auth_info,
                "setup_steps": config_help.setup_steps or [],
                "docs_url": config_help.docs_url,
                "allowed_domains": config_help.allowed_domains or [],
                "auth_type": config_help.auth_type,
                "compatibility_warning": config_help.compatibility_warning,
            })

        except Exception as e:
            logger.error(f"Config help failed: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Failed to get configuration help: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="ai-discover")
    def ai_discover(self, request):
        """AI-powered MCP server discovery.

        Takes a user's description and searches for matching MCP servers.
        Returns both preconfigured servers (from our catalog) and external ones (from web).

        POST /api/mcp/servers/ai-discover/
        {
            "query": "I want to connect to GitHub"
        }
        """
        from .ai_discovery import discover_mcp_servers

        query = request.data.get("query", "").strip()

        if not query:
            return Response(
                {"error": "Please describe what you want to do"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(query) < 5:
            return Response(
                {"error": "Please provide a more detailed description"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get all preconfigured servers to search against
            preconfigured = MCPServer.objects.filter(
                is_preconfigured=True
            ).values(
                'id', 'name', 'description', 'category',
                'npm_package', 'remote_url', 'auth_type',
                'icon_url', 'icon_invert_in_dark_mode'
            )
            preconfigured_list = list(preconfigured)

            # Run discovery
            result = run_async_in_new_thread(
                discover_mcp_servers(query, preconfigured_list, user=request.user)
            )

            def serialize_server(s):
                return {
                    "name": s.name,
                    "description": s.description,
                    "npm_package": s.npm_package,
                    "remote_url": s.remote_url,
                    "github_url": s.github_url,
                    "server_type": s.server_type,
                    "auth_type": s.auth_type,
                    "confidence": s.confidence,
                    "source_url": s.source_url,
                    "preconfigured_id": s.preconfigured_id,
                    "icon_url": s.icon_url,
                    "icon_invert_in_dark_mode": s.icon_invert_in_dark_mode,
                }

            preconfigured_serialized = [serialize_server(s) for s in result.preconfigured]
            external_serialized = [serialize_server(s) for s in result.external]

            # Save to search history (update existing or create new)
            MCPDiscoverySearch.objects.update_or_create(
                user=request.user,
                query__iexact=query,
                defaults={
                    "query": query,
                    "preconfigured_results": preconfigured_serialized,
                    "external_results": external_serialized,
                }
            )

            # Keep only the 10 most recent searches per user
            old_searches = MCPDiscoverySearch.objects.filter(
                user=request.user
            ).order_by('-created_at')[10:]
            MCPDiscoverySearch.objects.filter(id__in=[s.id for s in old_searches]).delete()

            return Response({
                "query": query,
                "preconfigured": preconfigured_serialized,
                "external": external_serialized,
                "preconfigured_count": len(result.preconfigured),
                "external_count": len(result.external),
            })

        except Exception as e:
            logger.error(f"AI discovery failed: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Discovery failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="discovery-history")
    def discovery_history(self, request):
        """Get user's AI discovery search history.

        Returns the 10 most recent searches.

        GET /api/mcp/servers/discovery-history/
        """
        searches = MCPDiscoverySearch.objects.filter(
            user=request.user
        ).order_by('-created_at')[:10]

        serializer = MCPDiscoverySearchSerializer(searches, many=True)
        return Response(serializer.data)


class MCPToolViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing MCP tools (read-only).

    Tools are discovered automatically from servers.
    """

    serializer_class = MCPToolSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter tools by current user's servers and preconfigured servers."""
        from django.db.models import Q
        return MCPTool.objects.filter(
            Q(server__user=self.request.user, server__is_active=True) |
            Q(server__is_preconfigured=True, server__is_active=True)
        ).order_by("name")

    @action(detail=True, methods=["post"])
    def call(self, request, pk=None):
        """Call a tool with given arguments.

        This creates an approval request and returns it for user decision.

        POST /api/mcp/tools/{id}/call/
        {
            "arguments": {...},
            "session_id": "optional-session-id"
        }
        """
        tool = self.get_object()
        serializer = CallToolRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        arguments = serializer.validated_data["arguments"]
        session_id = serializer.validated_data.get("session_id", "")

        # Create approval request
        approval = MCPToolApproval.objects.create(
            user=request.user,
            tool=tool,
            session_id=session_id,
            proposed_arguments=arguments,
            status=MCPToolApproval.ApprovalStatus.PENDING,
        )

        return Response(
            {
                "status": "approval_required",
                "message": "Tool execution requires approval",
                "approval": MCPToolApprovalSerializer(approval).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class MCPToolApprovalViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tool approvals."""

    serializer_class = MCPToolApprovalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter approvals by current user."""
        queryset = MCPToolApproval.objects.filter(user=self.request.user).select_related('tool__server')

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by session
        session_id = self.request.query_params.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        return queryset.order_by("-requested_at")

    def _get_connector_slug_from_server(self, server):
        """Get connector slug from server.

        Note: The old connector system has been removed. This method now
        always returns None as servers no longer have associated connectors.

        Args:
            server: MCPServer instance

        Returns:
            None (connectors are no longer used)
        """
        return None

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve a tool execution.

        POST /api/mcp/approvals/{id}/approve/
        {
            "scope": "once" | "session" | "permanent"
        }
        """
        approval = self.get_object()

        if approval.status != MCPToolApproval.ApprovalStatus.PENDING:
            return Response(
                {
                    "status": "error",
                    "message": "Approval has already been decided",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ApproveToolRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        scope = serializer.validated_data["scope"]
        approval.approve(scope=scope)

        # Execute the tool
        try:
            # Extract tool and server info before entering async context
            tool = approval.tool
            tool_name = tool.name
            server_id = str(tool.server.id)
            server_transport_type = tool.server.transport_type

            execution = MCPToolExecution.objects.create(
                tool=tool,
                approval=approval,
                session_id=approval.session_id,
                arguments=approval.proposed_arguments,
                status=MCPToolExecution.ExecutionStatus.PENDING,
            )

            # Execute tool
            execution.mark_running()

            registry = get_registry()
            result = run_async_in_new_thread(
                registry.call_tool_by_name(
                    tool_name=tool_name,
                    server_id=server_id,
                    server_transport_type=server_transport_type,
                    arguments=approval.proposed_arguments,
                    user=request.user,  # Pass user for security verification
                )
            )

            execution.mark_success(result)

            return Response({
                "status": "success",
                "message": "Tool executed successfully",
                "approval": MCPToolApprovalSerializer(approval).data,
                "execution": MCPToolExecutionSerializer(execution).data,
            })

        except MCPError as e:
            error_msg = str(e)
            execution.mark_error(error_msg)

            # Get connector slug for context-aware error messages
            connector_slug = self._get_connector_slug_from_server(tool.server)

            # Transform technical error to user-friendly message
            from .error_handlers import get_user_friendly_error, get_http_status_code
            user_msg, status_category = get_user_friendly_error(error_msg, connector_slug)
            http_status = get_http_status_code(status_category)

            return Response(
                {
                    "status": "error",
                    "error": user_msg,
                    "message": user_msg,
                    "execution": MCPToolExecutionSerializer(execution).data,
                },
                status=http_status,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tool execution failed: {error_msg}")
            execution.mark_error(error_msg)

            # Get connector slug for context-aware error messages
            connector_slug = self._get_connector_slug_from_server(tool.server)

            # Transform technical error to user-friendly message
            from .error_handlers import get_user_friendly_error, get_http_status_code
            user_msg, status_category = get_user_friendly_error(error_msg, connector_slug)
            http_status = get_http_status_code(status_category)

            return Response(
                {
                    "status": "error",
                    "error": user_msg,
                    "message": user_msg,
                    "execution": MCPToolExecutionSerializer(execution).data,
                },
                status=http_status,
            )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Reject a tool execution.

        POST /api/mcp/approvals/{id}/reject/
        """
        approval = self.get_object()

        if approval.status != MCPToolApproval.ApprovalStatus.PENDING:
            return Response(
                {
                    "status": "error",
                    "message": "Approval has already been decided",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RejectToolRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval.reject()

        return Response({
            "status": "success",
            "message": "Tool execution rejected",
            "approval": MCPToolApprovalSerializer(approval).data,
        })

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Get all pending approvals for the current user.

        GET /api/mcp/approvals/pending/
        """
        pending_approvals = self.get_queryset().filter(
            status=MCPToolApproval.ApprovalStatus.PENDING
        )

        serializer = self.get_serializer(pending_approvals, many=True)
        return Response(serializer.data)


class MCPToolExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing tool executions (read-only)."""

    serializer_class = MCPToolExecutionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter executions by current user's tools."""
        queryset = MCPToolExecution.objects.filter(
            tool__server__user=self.request.user
        )

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by session
        session_id = self.request.query_params.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        # Filter by tool
        tool_id = self.request.query_params.get("tool_id")
        if tool_id:
            queryset = queryset.filter(tool_id=tool_id)

        return queryset.order_by("-started_at")

    @action(detail=False, methods=["get"])
    def recent(self, request):
        """Get recent executions (last 50).

        GET /api/mcp/executions/recent/
        """
        recent_executions = self.get_queryset()[:50]
        serializer = self.get_serializer(recent_executions, many=True)
        return Response(serializer.data)


# =============================================================================
# Dynamic OAuth Callback View (for arbitrary MCP servers)
# =============================================================================


class MCPDynamicOAuthCallbackView(View):
    """Handle OAuth callback for dynamically discovered MCP servers.

    GET /api/mcp/oauth/callback/?code=...&state=...

    This view handles the OAuth callback after user authorizes with the
    MCP server's OAuth provider. It exchanges the authorization code for
    tokens and redirects to the frontend.
    """

    def get(self, request):
        """Handle OAuth callback."""
        from django.conf import settings
        from .oauth import MCPDynamicOAuthFlow, DynamicOAuthCallbackError

        code = request.GET.get('code', '')
        state = request.GET.get('state', '')
        error = request.GET.get('error', '')
        error_description = request.GET.get('error_description', '')

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')

        # Handle error from OAuth provider
        if error:
            logger.error(f"OAuth callback error: {error} - {error_description}")
            return HttpResponseRedirect(
                f"{frontend_url}/connectors?oauth_error={error}&message={error_description}"
            )

        if not state:
            return HttpResponseRedirect(
                f"{frontend_url}/connectors?oauth_error=missing_state"
            )

        try:
            flow = MCPDynamicOAuthFlow()
            server = run_async_in_new_thread(
                flow.handle_callback(
                    state=state,
                    code=code,
                    error=error,
                    error_description=error_description,
                )
            )

            logger.info(f"OAuth callback successful for server {server.name}")

            # Invalidate tool cache for user to pick up new server
            try:
                if server.user_id:
                    from llm.tool_catalog.registry import get_tool_catalog
                    from mcp.tool_discovery_adapter import get_mcp_adapter

                    user_id = str(server.user_id)
                    catalog = get_tool_catalog()
                    catalog.invalidate_user_tools_cache(user_id)

                    adapter = get_mcp_adapter()
                    adapter.clear_user_cache(user_id)

                    logger.info(f"[OAuth] Invalidated tool caches for user {user_id} after connecting {server.name}")
            except Exception as e:
                logger.warning(f"[OAuth] Failed to invalidate caches: {e}")

            return HttpResponseRedirect(
                f"{frontend_url}/connectors?oauth_success=true&server_id={server.id}&server_name={server.name}"
            )

        except DynamicOAuthCallbackError as e:
            logger.error(f"OAuth callback failed: {str(e)}")
            return HttpResponseRedirect(
                f"{frontend_url}/connectors?oauth_error=callback_failed&message={str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected OAuth callback error: {str(e)}", exc_info=True)
            return HttpResponseRedirect(
                f"{frontend_url}/connectors?oauth_error=unexpected_error&message={str(e)}"
            )
