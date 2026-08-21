"""MCPServerViewSet: auth boundaries (IDOR), secret non-exposure, and
URL/SSRF validation on user-supplied ``remote_url`` (mcp/views.py,
mcp/serializers.py).

House adversarial style: match usage_quota/tests/test_quota_idor.py —
strong assertions on cross-tenant isolation, not just status codes.
"""

import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from mcp.models import MCPServer

from .conftest import make_server

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Authentication required
# ---------------------------------------------------------------------------


def test_list_servers_rejects_unauthenticated(api_client):
    response = api_client.get(reverse("mcp:server-list"))
    assert response.status_code == 401


def test_create_server_rejects_unauthenticated(api_client):
    response = api_client.post(
        reverse("mcp:server-list"),
        data={"name": "x", "npm_package": "@a/b"},
        format="json",
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# IDOR: user A cannot read/modify/delete user B's server
# ---------------------------------------------------------------------------


def test_list_only_returns_own_servers(api_client, auth_as, user_a, user_b):
    make_server(user_a, name="A's server", npm_package="@a/server")
    make_server(user_b, name="B's server", npm_package="@b/server")

    client = auth_as(api_client, user_a)
    response = client.get(reverse("mcp:server-list"))

    assert response.status_code == 200
    names = [s["name"] for s in response.data["results"]]
    assert names == ["A's server"]


def test_retrieve_other_users_server_returns_404(api_client, auth_as, user_a, user_b):
    server_b = make_server(user_b, name="B's server", npm_package="@b/server")

    client = auth_as(api_client, user_a)
    response = client.get(reverse("mcp:server-detail", args=[server_b.id]))

    assert response.status_code == 404


def test_update_other_users_server_returns_404_and_does_not_modify(
    api_client, auth_as, user_a, user_b
):
    server_b = make_server(user_b, name="B's original name", npm_package="@b/server")

    client = auth_as(api_client, user_a)
    response = client.patch(
        reverse("mcp:server-detail", args=[server_b.id]),
        data={"name": "hijacked by A"},
        format="json",
    )

    assert response.status_code == 404
    server_b.refresh_from_db()
    assert server_b.name == "B's original name"


def test_delete_other_users_server_returns_404_and_does_not_delete(
    api_client, auth_as, user_a, user_b
):
    server_b = make_server(user_b, npm_package="@b/server")

    client = auth_as(api_client, user_a)
    response = client.delete(reverse("mcp:server-detail", args=[server_b.id]))

    assert response.status_code == 404
    assert MCPServer.objects.filter(id=server_b.id).exists()


def test_create_ignores_client_supplied_user_field(api_client, auth_as, user_a, user_b):
    """Even if a client tries to smuggle a `user` field pointing at
    another account, the server must be created under request.user."""
    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:server-list"),
        data={
            "name": "spoof-attempt",
            "npm_package": "@a/spoof",
            "user": str(user_b.id),
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    server = MCPServer.objects.get(id=response.data["id"])
    assert server.user_id == user_a.id


def test_own_server_actions_use_get_object_scoped_to_user(
    api_client, auth_as, user_a, user_b
):
    """Sanity check the positive case: A can retrieve A's own server."""
    server_a = make_server(user_a, name="mine", npm_package="@a/mine")
    client = auth_as(api_client, user_a)
    response = client.get(reverse("mcp:server-detail", args=[server_a.id]))
    assert response.status_code == 200
    assert response.data["name"] == "mine"


# ---------------------------------------------------------------------------
# Secrets never leave the API — env_vars / auth_config / oauth tokens
# ---------------------------------------------------------------------------


def test_create_response_never_contains_secret_values(api_client, auth_as, user_a):
    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:server-list"),
        data={
            "name": "secret server",
            "npm_package": "@a/secret",
            "env_vars": {"GITHUB_TOKEN": "ghp_SUPER_SECRET_TOKEN"},
            "auth_config": {"API_KEY": "sk-live-SUPER-SECRET-KEY"},
        },
        format="json",
    )
    assert response.status_code == 201, response.data

    body = json.dumps(response.data)
    assert "ghp_SUPER_SECRET_TOKEN" not in body
    assert "sk-live-SUPER-SECRET-KEY" not in body
    assert response.data["env_var_keys"] == ["GITHUB_TOKEN"]
    assert response.data["has_auth"] is True
    assert "auth_config" not in response.data
    assert "env_vars" not in response.data


def test_retrieve_response_never_contains_secret_values(api_client, auth_as, user_a):
    server = make_server(
        user_a,
        env_vars={"GITHUB_TOKEN": "ghp_SUPER_SECRET_TOKEN"},
        auth_config={"API_KEY": "sk-live-SUPER-SECRET-KEY"},
    )
    client = auth_as(api_client, user_a)
    response = client.get(reverse("mcp:server-detail", args=[server.id]))

    assert response.status_code == 200
    body = json.dumps(response.data)
    assert "ghp_SUPER_SECRET_TOKEN" not in body
    assert "sk-live-SUPER-SECRET-KEY" not in body


def test_retrieve_response_never_contains_oauth_tokens(api_client, auth_as, user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        oauth_access_token="ya29.SUPER-SECRET-ACCESS-TOKEN",
        oauth_refresh_token="1//SUPER-SECRET-REFRESH-TOKEN",
        oauth_client_secret="client-secret-value",
    )
    client = auth_as(api_client, user_a)
    response = client.get(reverse("mcp:server-detail", args=[server.id]))

    assert response.status_code == 200
    body = json.dumps(response.data)
    assert "SUPER-SECRET-ACCESS-TOKEN" not in body
    assert "SUPER-SECRET-REFRESH-TOKEN" not in body
    assert "client-secret-value" not in body


# ---------------------------------------------------------------------------
# remote_url validation — what IS enforced, and the SSRF gap that ISN'T.
# ---------------------------------------------------------------------------


def test_create_rejects_non_http_scheme_remote_url(api_client, auth_as, user_a):
    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:server-list"),
        data={"name": "ftp server", "remote_url": "ftp://evil.example.com/"},
        format="json",
    )
    assert response.status_code == 400
    assert "remote_url" in response.data


def test_create_rejects_conflicting_npm_and_remote_url(api_client, auth_as, user_a):
    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:server-list"),
        data={
            "name": "conflict",
            "npm_package": "@a/local",
            "remote_url": "https://mcp.example.com/mcp",
        },
        format="json",
    )
    assert response.status_code == 400


def test_create_rejects_invalid_npm_package_format(api_client, auth_as, user_a):
    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:server-list"),
        data={"name": "bad pkg", "npm_package": "Not Valid!!"},
        format="json",
    )
    assert response.status_code == 400
    assert "npm_package" in response.data


@pytest.mark.parametrize(
    "internal_url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://localhost:8000/internal-admin/",
        "http://127.0.0.1:6379/",  # internal redis
        "http://10.0.0.5/internal-service",
    ],
)
def test_GAP_no_ssrf_protection_on_remote_url(api_client, auth_as, user_a, internal_url):
    """DOCUMENTS A GAP, does not assert desired behavior.

    `MCPServerSerializer.validate_remote_url` only checks the URL starts
    with http(s):// — it does not block loopback, link-local (cloud
    metadata), or RFC1918 private addresses. This server is later fetched
    server-side (tool discovery, health checks), so an authenticated user
    can point it at internal infrastructure: classic SSRF.

    This test is a tripwire: if someone adds SSRF filtering later, THIS
    test starts failing (201 → 400) and must be updated, not silenced.
    Tracked in .oss-prep/notes/ — not fixed here per task scope (test-only
    changes).
    """
    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:server-list"),
        data={"name": "internal target", "remote_url": internal_url},
        format="json",
    )
    assert response.status_code == 201, (
        f"remote_url={internal_url!r} was rejected — SSRF protection may have "
        "been added; update/remove this gap-documenting test."
    )


def test_BUG_discover_tools_with_expiring_oauth_token_hits_broken_import(
    api_client, auth_as, user_a
):
    """DOCUMENTS A LIVE BUG, does not assert desired behavior.

    `MCPServerViewSet.discover_tools` (views.py, remote-server branch)
    does `from .oauth import DynamicOAuthManager` when
    `server.oauth_needs_refresh` is True — but `mcp/oauth.py` defines no
    such class (it's `MCPDynamicOAuthFlow`). Any remote OAuth server
    whose token is within 5 minutes of expiry hits an ImportError and
    the discovery call 500s instead of refreshing the token. No network
    call is ever made — the ImportError fires before any HTTP request.

    Tracked in .oss-prep/notes/ — not fixed here per task scope
    (test-only changes). If `DynamicOAuthManager` is added/renamed
    correctly, this test starts failing and must be updated.
    """
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_access_token="soon-to-expire-token",
        oauth_token_expires_at=timezone.now() + timedelta(minutes=2),
    )

    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:server-discover-tools", args=[server.id]),
        data={},
        format="json",
    )

    assert response.status_code == 500, (
        "discover_tools no longer 500s on an expiring OAuth token — the "
        "DynamicOAuthManager import bug may have been fixed; "
        "update/remove this bug-documenting test."
    )
    assert "DynamicOAuthManager" in response.data["message"]
