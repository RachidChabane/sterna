"""MCP client implementation for WebSocket, stdio, and HTTP transports."""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from .exceptions import (
    MCPAuthenticationError,
    MCPConnectionError,
    MCPInvalidParametersError,
    MCPServerError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)
from .protocol import (
    MCPMessageType,
    MCPPromptDefinition,
    MCPRequest,
    MCPResourceDefinition,
    MCPResponse,
    MCPToolCallResult,
    MCPToolDefinition,
)
from .sse import parse_sse_response
from .versioning import negotiate_handshake_version

logger = logging.getLogger(__name__)

# Client identity sent with every `initialize` request.
DEFAULT_CLIENT_INFO: Dict[str, Any] = {
    "name": "Sterna MCP Client",
    "version": "1.0.0",
}


class MCPClientBase(ABC):
    """Abstract base class for MCP clients."""

    def __init__(
        self,
        timeout: float = 120.0,
        auth_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize MCP client.

        Args:
            timeout: Timeout for operations in seconds (default: 2 minutes for long-running MCP tools)
            auth_config: Authentication configuration
        """
        self.timeout = timeout
        self.auth_config = auth_config or {}
        self.is_connected = False
        self._message_id = 0
        # Set once `handshake()` negotiates a version with the server;
        # None means no version has been negotiated yet (handshake was
        # skipped or has not completed).
        self.negotiated_protocol_version: Optional[str] = None

    def _generate_message_id(self) -> str:
        """Generate a unique message ID."""
        self._message_id += 1
        return str(self._message_id)

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to MCP server."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to MCP server."""
        pass

    @abstractmethod
    async def _send_request(self, request: MCPRequest) -> MCPResponse:
        """Send request and wait for response.

        Args:
            request: MCP request to send

        Returns:
            MCP response

        Raises:
            MCPTimeoutError: If request times out
            MCPServerError: If server returns an error
        """
        pass

    async def handshake(
        self,
        client_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Perform MCP handshake.

        Args:
            client_info: Client information to send

        Returns:
            Server capabilities and information

        Raises:
            MCPConnectionError: If handshake fails
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server")

        client_info = client_info or DEFAULT_CLIENT_INFO

        async def send_initialize(version: str) -> MCPResponse:
            request = MCPRequest(
                id=self._generate_message_id(),
                method=MCPMessageType.INITIALIZE,
                params={
                    "protocolVersion": version,
                    "clientInfo": client_info,
                    "capabilities": {},
                },
            )
            return await self._send_request(request)

        try:
            response, negotiated = await negotiate_handshake_version(send_initialize)
            self.negotiated_protocol_version = negotiated

            # Send initialized notification (fire-and-forget: no id, so _send_request won't await a response)
            initialized_notification = MCPRequest(method=MCPMessageType.INITIALIZED, params={})
            await self._send_request(initialized_notification)

            return response.result or {}

        except asyncio.TimeoutError:
            raise MCPTimeoutError("Handshake timed out")
        except MCPConnectionError:
            raise
        except Exception as e:
            raise MCPConnectionError(f"Handshake failed: {str(e)}")

    async def list_tools(self) -> List[MCPToolDefinition]:
        """List available tools from the MCP server.

        Returns:
            List of tool definitions

        Raises:
            MCPConnectionError: If not connected
            MCPTimeoutError: If request times out
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server")

        request = MCPRequest(
            id=self._generate_message_id(),
            method=MCPMessageType.LIST_TOOLS,
            params={},
        )

        try:
            response = await self._send_request(request)
            if response.is_error():
                error_msg = (response.error or {}).get("message", "Unknown error")
                raise MCPServerError(
                    f"Failed to list tools: {error_msg}",
                    error_code=(response.error or {}).get("code"),
                )

            tools_data = (response.result or {}).get("tools", [])
            return [MCPToolDefinition.from_dict(tool) for tool in tools_data]

        except asyncio.TimeoutError:
            raise MCPTimeoutError("List tools request timed out")

    async def list_resources(self) -> List[MCPResourceDefinition]:
        """List available resources from the MCP server.

        Returns:
            List of resource definitions

        Raises:
            MCPConnectionError: If not connected
            MCPTimeoutError: If request times out
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server")

        request = MCPRequest(
            id=self._generate_message_id(),
            method=MCPMessageType.LIST_RESOURCES,
            params={},
        )

        try:
            response = await self._send_request(request)
            if response.is_error():
                error_msg = (response.error or {}).get("message", "Unknown error")
                raise MCPServerError(
                    f"Failed to list resources: {error_msg}",
                    error_code=(response.error or {}).get("code"),
                )

            resources_data = (response.result or {}).get("resources", [])
            return [MCPResourceDefinition.from_dict(res) for res in resources_data]

        except asyncio.TimeoutError:
            raise MCPTimeoutError("List resources request timed out")

    async def list_prompts(self) -> List[MCPPromptDefinition]:
        """List available prompts from the MCP server.

        Returns:
            List of prompt definitions

        Raises:
            MCPConnectionError: If not connected
            MCPTimeoutError: If request times out
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server")

        request = MCPRequest(
            id=self._generate_message_id(),
            method=MCPMessageType.LIST_PROMPTS,
            params={},
        )

        try:
            response = await self._send_request(request)
            if response.is_error():
                error_msg = (response.error or {}).get("message", "Unknown error")
                raise MCPServerError(
                    f"Failed to list prompts: {error_msg}",
                    error_code=(response.error or {}).get("code"),
                )

            prompts_data = (response.result or {}).get("prompts", [])
            return [MCPPromptDefinition.from_dict(prompt) for prompt in prompts_data]

        except asyncio.TimeoutError:
            raise MCPTimeoutError("List prompts request timed out")

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> MCPToolCallResult:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool call result

        Raises:
            MCPConnectionError: If not connected
            MCPToolNotFoundError: If tool doesn't exist
            MCPInvalidParametersError: If parameters are invalid
            MCPTimeoutError: If request times out
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server")

        request = MCPRequest(
            id=self._generate_message_id(),
            method=MCPMessageType.CALL_TOOL,
            params={
                "name": tool_name,
                "arguments": arguments,
            },
        )

        try:
            response = await self._send_request(request)
            if response.is_error():
                error = response.error or {}
                error_msg = error.get("message", "Unknown error")
                error_code = error.get("code")

                # Map error codes to specific exceptions
                if error_code == -32601:  # Method not found
                    raise MCPToolNotFoundError(f"Tool '{tool_name}' not found")
                elif error_code == -32602:  # Invalid params
                    raise MCPInvalidParametersError(f"Invalid parameters: {error_msg}")
                else:
                    raise MCPServerError(
                        f"Tool call failed: {error_msg}",
                        error_code=error_code,
                    )

            return MCPToolCallResult.from_dict(response.result or {})

        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"Tool call '{tool_name}' timed out")


class MCPWebSocketClient(MCPClientBase):
    """MCP client using WebSocket transport."""

    def __init__(
        self,
        url: str,
        timeout: float = 120.0,
        auth_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize WebSocket MCP client.

        Args:
            url: WebSocket URL (ws:// or wss://)
            timeout: Timeout for operations in seconds (default: 2 minutes for long-running MCP tools)
            auth_config: Authentication configuration
        """
        super().__init__(timeout=timeout, auth_config=auth_config)
        self.url = url
        self.websocket: Optional[ClientConnection] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        """Establish WebSocket connection to MCP server.

        Raises:
            MCPConnectionError: If connection fails
        """
        try:
            # Add auth headers if configured
            additional_headers = {}
            if "api_key" in self.auth_config:
                additional_headers["Authorization"] = f"Bearer {self.auth_config['api_key']}"

            self.websocket = await websockets.connect(
                self.url,
                additional_headers=additional_headers if additional_headers else None,
            )
            self.is_connected = True
            logger.info(f"Connected to MCP server at {self.url}")

            # Start background task to handle incoming messages
            asyncio.create_task(self._receive_messages())

        except Exception as e:
            raise MCPConnectionError(f"Failed to connect to {self.url}: {str(e)}")

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.is_connected = False
        logger.info("Disconnected from MCP server")

    async def _receive_messages(self) -> None:
        """Background task to receive and route messages."""
        if not self.websocket:
            return
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    response = MCPResponse.from_dict(data)

                    # Route response to waiting request
                    if response.id in self._pending_requests:
                        future = self._pending_requests.pop(response.id)
                        future.set_result(response)
                    else:
                        logger.warning(f"Received response for unknown request: {response.id}")

                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received: {message!r}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.is_connected = False
            logger.warning("WebSocket connection closed")

    async def _send_request(self, request: MCPRequest) -> MCPResponse:
        """Send request and wait for response.

        Args:
            request: MCP request to send

        Returns:
            MCP response

        Raises:
            MCPConnectionError: If not connected
            MCPTimeoutError: If request times out
        """
        if not self.websocket:
            raise MCPConnectionError("Not connected to MCP server")

        # Create future for response
        future: "asyncio.Future[MCPResponse]" = asyncio.Future()
        if request.id:
            self._pending_requests[request.id] = future

        # Send request
        try:
            message = json.dumps(request.to_dict())
            await self.websocket.send(message)

            # Wait for response (only if we expect one)
            if request.id:
                response = await asyncio.wait_for(future, timeout=self.timeout)
                return response
            else:
                # Notification - no response expected
                return MCPResponse(jsonrpc="2.0", id="", result={})

        except asyncio.TimeoutError:
            # Clean up pending request
            if request.id in self._pending_requests:
                self._pending_requests.pop(request.id)
            raise MCPTimeoutError(f"Request {request.method} timed out")
        except Exception as e:
            # Clean up pending request
            if request.id in self._pending_requests:
                self._pending_requests.pop(request.id)
            raise MCPConnectionError(f"Failed to send request: {str(e)}")


class MCPStdioClient(MCPClientBase):
    """MCP client using stdio transport (subprocess)."""

    def __init__(
        self,
        command: str,
        working_directory: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 120.0,
        auth_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize stdio MCP client.

        Args:
            command: Command to run (e.g., "npx -y @modelcontextprotocol/server-github")
            working_directory: Working directory for the subprocess
            env: Environment variables to pass to the subprocess
            timeout: Timeout for operations in seconds (default: 2 minutes for long-running MCP tools)
            auth_config: Authentication configuration
        """
        super().__init__(timeout=timeout, auth_config=auth_config)
        self.command = command
        self.working_directory = working_directory
        self.env = env or {}
        self.process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        """Start the subprocess and establish stdio connection.

        Raises:
            MCPConnectionError: If process fails to start
        """
        try:
            # Prepare environment
            import os
            process_env = os.environ.copy()
            process_env.update(self.env)

            # Start subprocess
            self.process = await asyncio.create_subprocess_shell(
                self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
                env=process_env,
            )
            self.is_connected = True
            logger.info(f"Started MCP server process: {self.command}")

            # Start background tasks to read messages and errors
            self._reader_task = asyncio.create_task(self._receive_messages())
            self._stderr_task = asyncio.create_task(self._log_stderr())

        except Exception as e:
            raise MCPConnectionError(f"Failed to start process '{self.command}': {str(e)}")

    async def disconnect(self) -> None:
        """Stop the subprocess."""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            self.process = None

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._stderr_task:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

        self.is_connected = False
        logger.info("Stopped MCP server process")

    async def _receive_messages(self) -> None:
        """Background task to read messages from stdout."""
        try:
            while self.process and self.process.stdout:
                line = await self.process.stdout.readline()
                if not line:
                    break

                try:
                    data = json.loads(line.decode())
                    response = MCPResponse.from_dict(data)

                    # Route response to waiting request
                    if response.id in self._pending_requests:
                        future = self._pending_requests.pop(response.id)
                        future.set_result(response)
                    else:
                        logger.warning(f"Received response for unknown request: {response.id}")

                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from subprocess: {line!r}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in message reader: {e}")
            self.is_connected = False

    async def _log_stderr(self) -> None:
        """Background task to log stderr from subprocess."""
        try:
            while self.process and self.process.stderr:
                line = await self.process.stderr.readline()
                if not line:
                    break
                stderr_msg = line.decode().strip()
                if stderr_msg:
                    logger.warning(f"MCP process stderr: {stderr_msg}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading stderr: {e}")

    async def _send_request(self, request: MCPRequest) -> MCPResponse:
        """Send request via stdin and wait for response.

        Args:
            request: MCP request to send

        Returns:
            MCP response

        Raises:
            MCPConnectionError: If not connected
            MCPTimeoutError: If request times out
        """
        if not self.process or not self.process.stdin:
            raise MCPConnectionError("Not connected to MCP server process")

        # Create future for response
        future: "asyncio.Future[MCPResponse]" = asyncio.Future()
        if request.id:
            self._pending_requests[request.id] = future

        try:
            # Send request
            message = json.dumps(request.to_dict()) + "\n"
            self.process.stdin.write(message.encode())
            await self.process.stdin.drain()

            # Wait for response (only if we expect one)
            if request.id:
                response = await asyncio.wait_for(future, timeout=self.timeout)
                return response
            else:
                # Notification - no response expected
                return MCPResponse(jsonrpc="2.0", id="", result={})

        except asyncio.TimeoutError:
            # Clean up pending request
            if request.id in self._pending_requests:
                self._pending_requests.pop(request.id)
            raise MCPTimeoutError(f"Request {request.method} timed out")
        except Exception as e:
            # Clean up pending request
            if request.id in self._pending_requests:
                self._pending_requests.pop(request.id)
            raise MCPConnectionError(f"Failed to send request: {str(e)}")


class MCPRemoteHTTPClient(MCPClientBase):
    """MCP client using HTTP/SSE transport for remote servers.

    This is the transport used by Claude.ai integrations (Zapier, Atlassian, etc.)
    Remote MCP servers expose HTTP endpoints for JSON-RPC communication.
    """

    # Endpoint path candidates tried, in order, until the MCP endpoint is
    # discovered and cached on `_pinned_endpoint`.
    _ENDPOINT_CANDIDATES: Tuple[str, ...] = ("", "/rpc", "/message", "/mcp")

    def __init__(
        self,
        url: str,
        timeout: float = 120.0,
        auth_config: Optional[Dict[str, Any]] = None,
        auth_type: str = "none",
        auth_header: str = "Authorization",
    ):
        """Initialize HTTP MCP client.

        Args:
            url: Base URL of the remote MCP server (e.g., "https://mcp.zapier.com/api/mcp")
            timeout: Timeout for operations in seconds (default: 2 minutes)
            auth_config: Authentication configuration containing 'token', 'api_key', etc.
            auth_type: Type of authentication ('none', 'api_key', 'bearer', 'oauth')
            auth_header: HTTP header name for authentication (default: 'Authorization')
        """
        super().__init__(timeout=timeout, auth_config=auth_config)
        self.url = url.rstrip('/')
        self.auth_type = auth_type
        self.auth_header = auth_header
        self.client: Optional[httpx.AsyncClient] = None
        self.server_info: Optional[Dict[str, Any]] = None
        self.session_id: Optional[str] = None  # MCP Streamable HTTP session ID
        # The MCP endpoint path (relative to self.url) that answered the
        # first request, cached so later calls POST straight to it
        # instead of re-running endpoint discovery every time. The spec
        # defines a single, fixed MCP endpoint for the life of the
        # connection.
        self._pinned_endpoint: Optional[str] = None

    def _build_auth_headers(self, include_session: bool = True) -> Dict[str, str]:
        """Build authentication headers based on auth type.

        Args:
            include_session: Whether to include the Mcp-Session-Id header if available
        """
        # MCP Streamable HTTP requires Accept header for both JSON and SSE
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        # Include session ID if we have one (required for all requests after initialize)
        if include_session and self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        # Required on every request once a version has been negotiated
        # (never on the `initialize` request itself, which is what
        # negotiates it).
        if self.negotiated_protocol_version:
            headers["MCP-Protocol-Version"] = self.negotiated_protocol_version

        if self.auth_type == "none" or not self.auth_config:
            return headers

        # Get the auth value from auth_config
        auth_value = self.auth_config.get('token') or self.auth_config.get('api_key') or self.auth_config.get('value')

        if not auth_value:
            return headers

        if self.auth_type == "bearer":
            headers[self.auth_header] = f"Bearer {auth_value}"
        elif self.auth_type == "api_key":
            headers[self.auth_header] = auth_value
        elif self.auth_type == "oauth":
            headers[self.auth_header] = f"Bearer {auth_value}"

        return headers

    async def connect(self) -> None:
        """Initialize HTTP client and perform MCP handshake.

        Raises:
            MCPConnectionError: If connection or handshake fails
        """
        try:
            headers = self._build_auth_headers()
            # Don't use base_url - we'll construct full URLs manually
            # to avoid trailing slash issues with MCP endpoints
            self.client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
            )
            self.is_connected = True
            logger.info(f"Initialized HTTP client for MCP server at {self.url}")

        except Exception as e:
            raise MCPConnectionError(f"Failed to initialize HTTP client for {self.url}: {str(e)}")

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
        self.is_connected = False
        # A future connect() starts a new session: forget what this one
        # negotiated and discovered.
        self.session_id = None
        self._pinned_endpoint = None
        self.negotiated_protocol_version = None
        self.server_info = None
        logger.info(f"Disconnected from MCP server at {self.url}")

    async def _send_request(self, request: MCPRequest, capture_session_id: bool = False) -> MCPResponse:
        """Send JSON-RPC request via HTTP POST.

        Args:
            request: MCP request to send
            capture_session_id: If True, capture Mcp-Session-Id from response headers

        Returns:
            MCP response

        Raises:
            MCPConnectionError: If not connected or request fails
            MCPTimeoutError: If request times out
        """
        if not self.client:
            raise MCPConnectionError("HTTP client not initialized")

        try:
            # Once discovered, the MCP endpoint is fixed for the life of
            # the connection: reuse it instead of re-running discovery
            # on every request. Only guess among the candidates before
            # that first success.
            endpoints_to_try: Tuple[str, ...] = (
                (self._pinned_endpoint,)
                if self._pinned_endpoint is not None
                else self._ENDPOINT_CANDIDATES
            )

            # Build headers for this request (includes session ID if available)
            # For initialize request, don't include session ID yet
            include_session = not capture_session_id
            request_headers = self._build_auth_headers(include_session=include_session)

            last_error = None
            for endpoint in endpoints_to_try:
                try:
                    # Construct full URL (don't use base_url to avoid trailing slash issues)
                    full_url = self.url + endpoint
                    logger.debug(f"Trying endpoint: {full_url}")
                    # Use streaming to handle SSE responses
                    async with self.client.stream(
                        "POST",
                        full_url,
                        json=request.to_dict(),
                        headers=request_headers,
                    ) as response:
                        logger.debug(f"Response status: {response.status_code}, content-type: {response.headers.get('content-type')}")

                        # Try next endpoint on 404 (Not Found) or 405 (Method Not Allowed)
                        if response.status_code in (404, 405, 406):
                            logger.debug(f"Endpoint {endpoint} returned {response.status_code}, trying next")
                            continue

                        if response.status_code == 401:
                            raise MCPAuthenticationError("Authentication failed - check your credentials")

                        if response.status_code == 403:
                            raise MCPAuthenticationError("Access forbidden - insufficient permissions")

                        response.raise_for_status()

                        # This endpoint answered successfully: pin it so
                        # later requests skip discovery entirely.
                        if self._pinned_endpoint is None:
                            self._pinned_endpoint = endpoint

                        # Capture session ID from initialize response
                        if capture_session_id:
                            session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
                            if session_id:
                                logger.info(f"Captured MCP session ID: {session_id[:20]}...")
                                self.session_id = session_id

                        content_type = response.headers.get("content-type", "")

                        # Handle SSE (Server-Sent Events) responses
                        if "text/event-stream" in content_type:
                            logger.debug("Parsing SSE response")
                            return await parse_sse_response(response)

                        # Handle regular JSON responses
                        content = await response.aread()
                        data = json.loads(content)
                        return MCPResponse.from_dict(data)

                except httpx.HTTPStatusError as e:
                    logger.debug(f"HTTPStatusError for {endpoint}: {e.response.status_code}")
                    if e.response.status_code in (404, 405, 406):
                        continue
                    last_error = e
                    break
                except Exception as e:
                    logger.debug(f"Exception for {endpoint}: {type(e).__name__}: {e}")
                    raise

            if last_error:
                raise MCPConnectionError(f"HTTP request failed: {last_error}")

            raise MCPConnectionError(f"No valid MCP endpoint found at {self.url}")

        except httpx.TimeoutException:
            raise MCPTimeoutError(f"Request {request.method} timed out")
        except MCPAuthenticationError:
            raise
        except MCPConnectionError:
            raise
        except Exception as e:
            raise MCPConnectionError(f"Failed to send request: {str(e)}")

    async def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call any method on the MCP server.

        Args:
            method: The JSON-RPC method name (e.g., "tools/list")
            params: Optional parameters for the method

        Returns:
            The result from the server response

        Raises:
            MCPConnectionError: If not connected or request fails
        """
        request = MCPRequest(
            id=self._generate_message_id(),
            method=method,
            params=params or {},
        )
        response = await self._send_request(request)

        if response.is_error():
            error_msg = (response.error or {}).get("message", "Unknown error")
            raise MCPConnectionError(f"Method {method} failed: {error_msg}")

        return response.result or {}

    async def _send_notification(self, notification: MCPRequest) -> None:
        """Send a JSON-RPC notification via HTTP POST (no response expected).

        For MCP Streamable HTTP, notifications are fire-and-forget.
        Some servers may return an empty response, others may not.

        Args:
            notification: MCP notification to send (must have no id)
        """
        if not self.client:
            raise MCPConnectionError("HTTP client not initialized")

        try:
            # Build headers including session ID if available
            request_headers = self._build_auth_headers(include_session=True)

            # Use the pinned MCP endpoint if one was already discovered;
            # otherwise fall back to the base URL.
            full_url = self.url + (self._pinned_endpoint or "")

            # For notifications, just POST and ignore the response
            response = await self.client.post(
                full_url,
                json=notification.to_dict(),
                headers=request_headers,
            )
            # Log but don't fail on non-success status for notifications
            if response.status_code >= 400:
                logger.debug(f"Notification {notification.method} returned {response.status_code}")

        except Exception as e:
            # Don't fail for notification errors - they're not critical
            logger.debug(f"Notification {notification.method} error: {e}")

    async def handshake(
        self,
        client_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Perform MCP handshake for HTTP transport.

        This override captures the Mcp-Session-Id header from the server
        which is required for all subsequent requests.

        Args:
            client_info: Client information to send

        Returns:
            Server capabilities and information

        Raises:
            MCPConnectionError: If handshake fails
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server")

        client_info = client_info or DEFAULT_CLIENT_INFO

        async def send_initialize(version: str) -> MCPResponse:
            request = MCPRequest(
                id=self._generate_message_id(),
                method=MCPMessageType.INITIALIZE,
                params={
                    "protocolVersion": version,
                    "clientInfo": client_info,
                    "capabilities": {},
                },
            )
            # Session ID is minted on this call, so it can't be sent yet.
            return await self._send_request(request, capture_session_id=True)

        try:
            response, negotiated = await negotiate_handshake_version(send_initialize)
            self.negotiated_protocol_version = negotiated

            logger.info(
                f"MCP handshake successful (protocol {negotiated}), "
                f"session_id captured: {self.session_id is not None}"
            )

            # Send initialized notification (no response expected)
            initialized_notification = MCPRequest(
                method=MCPMessageType.INITIALIZED,
                params={},
            )
            await self._send_notification(initialized_notification)

            return response.result or {}

        except asyncio.TimeoutError:
            raise MCPTimeoutError("Handshake timed out")
        except MCPConnectionError:
            raise
        except Exception as e:
            raise MCPConnectionError(f"Handshake failed: {str(e)}")

    async def health_check(self) -> Dict[str, Any]:
        """Check if the remote server is reachable.

        Returns:
            Health status dict with 'healthy' boolean and optional 'error'
        """
        if not self.client:
            return {"healthy": False, "error": "Client not initialized"}

        try:
            # Try a simple ping or list_tools to verify connectivity
            tools = await self.list_tools()
            return {
                "healthy": True,
                "tool_count": len(tools),
                "url": self.url,
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "url": self.url,
            }


def create_mcp_client(
    transport_type: str = "websocket",
    url: Optional[str] = None,
    command: Optional[str] = None,
    working_directory: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 120.0,
    auth_config: Optional[Dict[str, Any]] = None,
    auth_type: str = "none",
    auth_header: str = "Authorization",
) -> MCPClientBase:
    """Factory function to create an MCP client.

    Args:
        transport_type: Type of transport ("websocket", "stdio", "http", or "sandboxed")
        url: URL for WebSocket or HTTP transport
        command: Command to run (required for stdio transport)
        working_directory: Working directory for stdio subprocess
        env: Environment variables for stdio subprocess
        timeout: Timeout for operations in seconds (default: 2 minutes for long-running MCP tools)
        auth_config: Authentication configuration
        auth_type: Authentication type for HTTP ('none', 'api_key', 'bearer', 'oauth')
        auth_header: HTTP header name for authentication

    Returns:
        MCP client instance (WebSocket, stdio, or HTTP)

    Raises:
        ValueError: If required parameters are missing for the transport type
    """
    if transport_type == "websocket":
        if not url:
            raise ValueError("URL is required for WebSocket transport")
        return MCPWebSocketClient(url=url, timeout=timeout, auth_config=auth_config)

    elif transport_type == "stdio":
        if not command:
            raise ValueError("Command is required for stdio transport")
        return MCPStdioClient(
            command=command,
            working_directory=working_directory,
            env=env,
            timeout=timeout,
            auth_config=auth_config,
        )

    elif transport_type == "http":
        if not url:
            raise ValueError("URL is required for HTTP transport")
        return MCPRemoteHTTPClient(
            url=url,
            timeout=timeout,
            auth_config=auth_config,
            auth_type=auth_type,
            auth_header=auth_header,
        )

    elif transport_type == "sandboxed":
        # Sandboxed transport is handled via the orchestrator, not a direct client
        # This branch is for compatibility - actual sandboxed servers use HTTP to the container
        raise ValueError(
            "Sandboxed transport should be accessed via the sandbox orchestrator, "
            "not directly through the MCP client"
        )

    else:
        raise ValueError(f"Unknown transport type: {transport_type}")

