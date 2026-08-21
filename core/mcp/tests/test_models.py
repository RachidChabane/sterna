"""MCPServer OAuth state-machine properties and token lifecycle helpers
(mcp/models.py: has_valid_oauth_token, oauth_needs_refresh,
oauth_connection_status, clear_oauth_tokens, store_oauth_tokens).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from mcp.models import MCPServer

from .conftest import make_server

pytestmark = pytest.mark.django_db


def _oauth_server(user, **kwargs):
    defaults = {
        "npm_package": "",
        "remote_url": "https://mcp.example.com/mcp",
        "auth_type": MCPServer.AuthType.OAUTH,
        "transport_type": MCPServer.TransportType.HTTP,
    }
    defaults.update(kwargs)
    return make_server(user, **defaults)


# ---------------------------------------------------------------------------
# has_valid_oauth_token
# ---------------------------------------------------------------------------


def test_has_valid_oauth_token_false_without_access_token(user_a):
    server = _oauth_server(user_a, oauth_access_token="")
    assert server.has_valid_oauth_token is False


def test_has_valid_oauth_token_true_when_no_expiry_set(user_a):
    server = _oauth_server(user_a, oauth_access_token="tok", oauth_token_expires_at=None)
    assert server.has_valid_oauth_token is True


def test_has_valid_oauth_token_false_when_expired(user_a):
    server = _oauth_server(
        user_a,
        oauth_access_token="tok",
        oauth_token_expires_at=timezone.now() - timedelta(minutes=1),
    )
    assert server.has_valid_oauth_token is False


def test_has_valid_oauth_token_false_within_one_minute_buffer(user_a):
    """Within the 1-minute expiry buffer must be treated as already-expired."""
    server = _oauth_server(
        user_a,
        oauth_access_token="tok",
        oauth_token_expires_at=timezone.now() + timedelta(seconds=30),
    )
    assert server.has_valid_oauth_token is False


def test_has_valid_oauth_token_true_comfortably_before_expiry(user_a):
    server = _oauth_server(
        user_a,
        oauth_access_token="tok",
        oauth_token_expires_at=timezone.now() + timedelta(hours=1),
    )
    assert server.has_valid_oauth_token is True


# ---------------------------------------------------------------------------
# oauth_needs_refresh
# ---------------------------------------------------------------------------


def test_oauth_needs_refresh_false_without_token_or_expiry(user_a):
    server = _oauth_server(user_a, oauth_access_token="", oauth_token_expires_at=None)
    assert server.oauth_needs_refresh is False


def test_oauth_needs_refresh_true_within_five_minutes(user_a):
    server = _oauth_server(
        user_a,
        oauth_access_token="tok",
        oauth_token_expires_at=timezone.now() + timedelta(minutes=3),
    )
    assert server.oauth_needs_refresh is True


def test_oauth_needs_refresh_false_when_comfortably_valid(user_a):
    server = _oauth_server(
        user_a,
        oauth_access_token="tok",
        oauth_token_expires_at=timezone.now() + timedelta(hours=2),
    )
    assert server.oauth_needs_refresh is False


# ---------------------------------------------------------------------------
# oauth_connection_status
# ---------------------------------------------------------------------------


def test_oauth_connection_status_not_configured_for_non_oauth_server(user_a):
    server = make_server(user_a, auth_type=MCPServer.AuthType.NONE)
    assert server.oauth_connection_status == "not_configured"


def test_oauth_connection_status_pending_while_flow_in_progress(user_a):
    server = _oauth_server(user_a, oauth_state="mcp:some-state")
    assert server.oauth_connection_status == "pending"


def test_oauth_connection_status_connected_with_valid_token(user_a):
    server = _oauth_server(
        user_a,
        oauth_access_token="tok",
        oauth_token_expires_at=timezone.now() + timedelta(hours=1),
    )
    assert server.oauth_connection_status == "connected"


def test_oauth_connection_status_expired_with_stale_token(user_a):
    server = _oauth_server(
        user_a,
        oauth_access_token="tok",
        oauth_token_expires_at=timezone.now() - timedelta(hours=1),
    )
    assert server.oauth_connection_status == "expired"


def test_oauth_connection_status_not_configured_without_token_or_state(user_a):
    server = _oauth_server(user_a, oauth_access_token="", oauth_state="")
    assert server.oauth_connection_status == "not_configured"


# ---------------------------------------------------------------------------
# clear_oauth_tokens / store_oauth_tokens
# ---------------------------------------------------------------------------


def test_clear_oauth_tokens_wipes_all_oauth_fields(user_a):
    server = _oauth_server(
        user_a,
        oauth_access_token="access",
        oauth_refresh_token="refresh",
        oauth_token_expires_at=timezone.now() + timedelta(hours=1),
        oauth_scopes=["read"],
        oauth_state="mcp:state",
        oauth_pkce_verifier="verifier",
    )

    server.clear_oauth_tokens()
    server.refresh_from_db()

    assert server.oauth_access_token == ""
    assert server.oauth_refresh_token == ""
    assert server.oauth_token_expires_at is None
    assert server.oauth_scopes == []
    assert server.oauth_state == ""
    assert server.oauth_pkce_verifier == ""


def test_store_oauth_tokens_sets_expiry_and_clears_flow_fields(user_a):
    server = _oauth_server(
        user_a,
        oauth_state="mcp:pending",
        oauth_pkce_verifier="verifier",
    )

    before = timezone.now()
    server.store_oauth_tokens(
        access_token="new-access",
        refresh_token="new-refresh",
        expires_in=1800,
        scopes=["read", "write"],
    )
    server.refresh_from_db()

    assert server.oauth_access_token == "new-access"
    assert server.oauth_refresh_token == "new-refresh"
    assert server.oauth_scopes == ["read", "write"]
    assert server.oauth_state == ""
    assert server.oauth_pkce_verifier == ""
    assert server.oauth_token_expires_at is not None
    assert before + timedelta(minutes=29) <= server.oauth_token_expires_at <= before + timedelta(minutes=31)


def test_store_oauth_tokens_preserves_existing_refresh_token_when_absent(user_a):
    """A provider that doesn't rotate refresh tokens omits it from the
    response — the existing one must survive, not get blanked."""
    server = _oauth_server(user_a, oauth_refresh_token="original-refresh")

    server.store_oauth_tokens(access_token="new-access")
    server.refresh_from_db()

    assert server.oauth_access_token == "new-access"
    assert server.oauth_refresh_token == "original-refresh"
