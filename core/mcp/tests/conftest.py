"""Shared fixtures for mcp app tests."""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from authentication.jwt_utils import JWTManager
from authentication.models import User
from mcp.fields import EncryptedJSONField, EncryptedTextField
from mcp.models import MCPServer, MCPTool, MCPToolApproval

# Every encrypted field declared on MCPServer. Field instances are
# class-level singletons that cache a MultiFernet cipher built from
# settings at first access (see mcp/fields.py). Any test that rotates
# BYOK_ENCRYPTION_KEY / BYOK_ENCRYPTION_KEY_LEGACY via the `settings`
# fixture must not leak a stale cipher into tests that run after it in
# the same session — reset unconditionally after every test.
_ENCRYPTED_FIELD_NAMES = (
    "auth_config",
    "env_vars",
    "oauth_client_secret",
    "oauth_access_token",
    "oauth_refresh_token",
    "oauth_pkce_verifier",
)


@pytest.fixture(autouse=True)
def _reset_encrypted_field_ciphers():
    """Clear cached MultiFernet ciphers on MCPServer's encrypted fields.

    Runs after every test (not just key-rotation tests) so a cipher
    built from a test-rotated key can never be picked up by a later,
    unrelated test in the same pytest session.
    """
    yield
    for name in _ENCRYPTED_FIELD_NAMES:
        field = MCPServer._meta.get_field(name)
        assert isinstance(field, (EncryptedTextField, EncryptedJSONField))
        field._fernet = None


@pytest.fixture(autouse=True)
def _no_auto_tool_discovery():
    """Disable the real-network side effect `perform_create` triggers.

    MCPServerViewSet.perform_create() unconditionally calls
    `_discover_tools_for_server`, which (depending on server shape) makes
    a real httpx POST to the sandbox orchestrator or opens a real
    MCPRemoteHTTPClient connection to whatever `remote_url` the caller
    supplied — including, deliberately, internal/private URLs in the
    SSRF-gap tests. Exceptions there are swallowed by the view, so tests
    would still pass, but only after slow/non-deterministic real network
    attempts. Patch it to a no-op; CRUD/auth behavior under test doesn't
    depend on tool discovery actually running.
    """
    with patch(
        "mcp.views.MCPServerViewSet._discover_tools_for_server",
        return_value=None,
    ):
        yield


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_as():
    """Factory: attach a JWT for ``user`` to ``client``.

    Mirrors usage_quota.tests.conftest.auth_as — uses the project's
    custom JWTManager (payload shape ``type: access``), which is what
    authentication.authentication.JWTAuthentication expects.
    """

    def _auth(client, user):
        access_token = JWTManager.create_access_token(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return client

    return _auth


@pytest.fixture
def user_a(db):
    return User.objects.create_user(email="a@t.com", password="x", is_verified=True)


@pytest.fixture
def user_b(db):
    return User.objects.create_user(email="b@t.com", password="x", is_verified=True)


def make_server(user, **kwargs):
    """Create an MCPServer owned by ``user`` with sane defaults."""
    defaults = {
        "name": "Test Server",
        "npm_package": "@modelcontextprotocol/server-test",
        "transport_type": MCPServer.TransportType.SANDBOXED,
        "is_active": True,
    }
    defaults.update(kwargs)
    return MCPServer.objects.create(user=user, **defaults)


def make_tool(server, **kwargs):
    """Create an MCPTool for ``server`` with sane defaults."""
    defaults = {
        "name": "test_tool",
        "description": "A test tool",
        "input_schema": {"type": "object", "properties": {}},
    }
    defaults.update(kwargs)
    return MCPTool.objects.create(server=server, **defaults)


def make_approval(user, tool, **kwargs):
    """Create an MCPToolApproval with sane defaults."""
    defaults = {
        "proposed_arguments": {"foo": "bar"},
        "status": MCPToolApproval.ApprovalStatus.PENDING,
    }
    defaults.update(kwargs)
    return MCPToolApproval.objects.create(user=user, tool=tool, **defaults)
