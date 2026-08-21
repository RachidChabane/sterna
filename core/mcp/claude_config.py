"""
Coding Agent MCP Configuration Serializer

Converts MCPServer model instances to the format expected by Coding Agent CLI's
--mcp-config flag. Handles different transport types and authentication methods.

Reference: https://docs.anthropic.com/en/docs/coding-agent/mcp
"""

import logging
from typing import Any

if True:  # TYPE_CHECKING equivalent that works at runtime
    from .models import MCPServer

logger = logging.getLogger(__name__)


def serialize_mcp_server_for_claude(server: "MCPServer") -> tuple[str, dict[str, Any]] | None:
    """
    Convert an MCPServer instance to Claude CLI --mcp-config format.

    Args:
        server: MCPServer model instance

    Returns:
        Tuple of (server_name, config_dict) or None if server cannot be serialized

    Raises:
        None - errors are logged and None is returned
    """
    try:
        transport = server.transport_type

        # Handle stdio/sandboxed (NPM packages)
        if transport in ("stdio", "sandboxed"):
            return _serialize_stdio_server(server)

        # Handle HTTP/SSE remote servers
        elif transport == "http":
            return _serialize_http_server(server)

        # Handle WebSocket servers
        elif transport == "websocket":
            return _serialize_websocket_server(server)

        else:
            logger.warning(
                f"[MCP-Claude] Unknown transport type '{transport}' for server '{server.name}'"
            )
            return None

    except Exception as e:
        logger.error(
            f"[MCP-Claude] Failed to serialize server '{server.name}': {e}",
            exc_info=True
        )
        return None


def _serialize_stdio_server(server: "MCPServer") -> tuple[str, dict[str, Any]] | None:
    """
    Serialize a stdio/sandboxed NPM server.

    Claude CLI format:
    {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "..."}
    }
    """
    npm_package = server.get_effective_npm_package()

    if not npm_package:
        logger.warning(
            f"[MCP-Claude] Stdio server '{server.name}' has no npm_package configured"
        )
        return None

    # Get environment variables (already decrypted by Django's EncryptedJSONField)
    env_vars = server.get_effective_env_vars()

    # Build the config
    config = {
        "command": "npx",
        "args": ["-y", npm_package],
    }

    # Only include env if there are variables
    if env_vars:
        config["env"] = env_vars

    # Sanitize server name for use as key (remove special chars, spaces)
    safe_name = _sanitize_server_name(server.name)

    logger.info(
        f"[MCP-Claude] Serialized stdio server '{server.name}' -> '{safe_name}' "
        f"(package: {npm_package}, env_vars: {len(env_vars)} keys)"
    )

    return (safe_name, config)


def _serialize_http_server(server: "MCPServer") -> tuple[str, dict[str, Any]] | None:
    """
    Serialize an HTTP/SSE remote server.

    Claude CLI format:
    {
        "url": "https://example.com/mcp",
        "transport": "sse",
        "headers": {"Authorization": "Bearer ..."}
    }
    """
    if not server.remote_url:
        logger.warning(
            f"[MCP-Claude] HTTP server '{server.name}' has no remote_url configured"
        )
        return None

    config: dict[str, Any] = {
        "url": server.remote_url,
        "transport": "sse",  # Claude CLI needs this for HTTP/SSE servers
    }

    # Add authentication headers based on auth_type
    headers = _build_auth_headers(server)
    if headers:
        config["headers"] = headers
    else:
        # OAuth servers without tokens shouldn't be included
        if server.auth_type == "oauth":
            logger.warning(
                f"[MCP-Claude] OAuth server '{server.name}' has no access token, skipping"
            )
            return None

    safe_name = _sanitize_server_name(server.name)

    logger.info(
        f"[MCP-Claude] Serialized HTTP server '{server.name}' -> '{safe_name}' "
        f"(url: {server.remote_url}, auth: {server.auth_type}, has_headers: {bool(headers)})"
    )

    return (safe_name, config)


def _serialize_websocket_server(server: "MCPServer") -> tuple[str, dict[str, Any]] | None:
    """
    Serialize a WebSocket server.

    Claude CLI format:
    {
        "url": "wss://example.com/mcp",
        "transport": "websocket"
    }
    """
    ws_url = server.url or server.remote_url

    if not ws_url:
        logger.warning(
            f"[MCP-Claude] WebSocket server '{server.name}' has no URL configured"
        )
        return None

    config: dict[str, Any] = {
        "url": ws_url,
        "transport": "websocket",
    }

    safe_name = _sanitize_server_name(server.name)

    logger.info(
        f"[MCP-Claude] Serialized WebSocket server '{server.name}' -> '{safe_name}' "
        f"(url: {ws_url})"
    )

    return (safe_name, config)


def _build_auth_headers(server: "MCPServer") -> dict[str, str]:
    """
    Build authentication headers based on server's auth configuration.

    Supports:
    - OAuth 2.0 (Bearer token from oauth_access_token)
    - Bearer token (from auth_config)
    - API Key (custom header from auth_config)
    """
    headers = {}
    auth_type = server.auth_type

    logger.debug(
        f"[MCP-Claude] Building auth headers for '{server.name}': "
        f"auth_type={auth_type}, has_oauth_token={bool(server.oauth_access_token)}"
    )

    if auth_type == "oauth":
        # Use OAuth access token if available
        if server.oauth_access_token:
            # Mask token for logging
            token = server.oauth_access_token
            masked = f"{token[:10]}...{token[-4:]}" if len(token) > 14 else "***"
            logger.info(
                f"[MCP-Claude] OAuth server '{server.name}' has access token: {masked}"
            )
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning(
                f"[MCP-Claude] OAuth server '{server.name}' has no access token"
            )

    elif auth_type == "bearer":
        # Get bearer token from auth_config
        auth_config = server.auth_config or {}
        token = auth_config.get("token") or auth_config.get("bearer_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    elif auth_type == "api_key":
        # Get API key from auth_config with custom header name
        auth_config = server.auth_config or {}
        api_key = auth_config.get("api_key") or auth_config.get("key")
        if api_key:
            header_name = server.auth_header_name or "X-API-Key"
            headers[header_name] = api_key

    return headers


def _sanitize_server_name(name: str) -> str:
    """
    Sanitize server name for use as a JSON key in MCP config.

    - Converts to lowercase
    - Replaces spaces and special chars with hyphens
    - Removes consecutive hyphens
    - Strips leading/trailing hyphens
    """
    import re

    # Convert to lowercase
    safe = name.lower()

    # Replace spaces and special chars with hyphens
    safe = re.sub(r"[^a-z0-9]+", "-", safe)

    # Remove consecutive hyphens
    safe = re.sub(r"-+", "-", safe)

    # Strip leading/trailing hyphens
    safe = safe.strip("-")

    # Ensure non-empty
    if not safe:
        safe = "mcp-server"

    return safe


def serialize_mcp_servers_for_claude(
    servers: list["MCPServer"],
) -> dict[str, dict[str, Any]]:
    """
    Serialize multiple MCPServer instances to Claude CLI mcpServers format.

    Args:
        servers: List of MCPServer model instances

    Returns:
        Dict suitable for {"mcpServers": result} in --mcp-config
    """
    result = {}

    for server in servers:
        serialized = serialize_mcp_server_for_claude(server)
        if serialized:
            name, config = serialized
            # Handle name collisions by appending number
            original_name = name
            counter = 1
            while name in result:
                name = f"{original_name}-{counter}"
                counter += 1
            result[name] = config

    logger.info(
        f"[MCP-Claude] Serialized {len(result)}/{len(servers)} MCP servers for Coding Agent"
    )

    return result
