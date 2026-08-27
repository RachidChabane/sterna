"""UnifiedMCPRegistry._refresh_oauth_token wiring (mcp/unified_registry.py).

Proves the registry's OAuth refresh path resolves and calls the real
``MCPDynamicOAuthFlow.refresh_server_token`` rather than a nonexistent
class name — a stale import here would raise before any HTTP call is
attempted, so a bare no-mock call already exercises the wiring end to
end for the graceful-failure case.
"""

from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync

from mcp.models import MCPServer
from mcp.oauth import DynamicOAuthTokenError, DynamicTokenResponse
from mcp.unified_registry import UnifiedMCPRegistry

from .conftest import make_server

pytestmark = pytest.mark.django_db


def test_refresh_oauth_token_returns_false_without_refresh_token(user_a):
    """No mocking: a stale `DynamicOAuthManager` import would raise
    ImportError here instead of returning False."""
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_access_token="expiring-token",
        oauth_refresh_token="",
    )

    registry = UnifiedMCPRegistry()
    result = async_to_sync(registry._refresh_oauth_token)(server)

    assert result is False


def test_refresh_oauth_token_succeeds_and_stores_new_access_token(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_access_token="stale-token",
        oauth_refresh_token="existing-refresh-token",
        oauth_client_id="client-id",
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
        },
    )

    registry = UnifiedMCPRegistry()
    with patch(
        "mcp.oauth.DynamicOAuthTokenManager.refresh_token",
        return_value=DynamicTokenResponse(
            access_token="refreshed-access-token",
            token_type="Bearer",
            expires_in=3600,
        ),
    ):
        result = async_to_sync(registry._refresh_oauth_token)(server)

    assert result is True
    server.refresh_from_db()
    assert server.oauth_access_token == "refreshed-access-token"
    assert server.oauth_refresh_token == "existing-refresh-token"


def test_refresh_oauth_token_returns_false_when_provider_rejects_refresh(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_access_token="stale-token",
        oauth_refresh_token="revoked-refresh-token",
        oauth_client_id="client-id",
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
        },
    )

    registry = UnifiedMCPRegistry()
    with patch(
        "mcp.oauth.DynamicOAuthTokenManager.refresh_token",
        side_effect=DynamicOAuthTokenError("invalid_grant"),
    ):
        result = async_to_sync(registry._refresh_oauth_token)(server)

    assert result is False
    server.refresh_from_db()
    assert server.oauth_access_token == "stale-token"
