"""OAuth handshake tests: PKCE/state generation, CSRF-state validation on
callback, dynamic client registration, and token exchange — all outbound
HTTP mocked (mcp/oauth.py).

Pattern (matches usage_quota/tests/test_billing_coverage.py): sync
``def test_*`` methods, async call sites wrapped in ``async_to_sync``.
Django's test runner never awaits ``async def test_*`` under pytest here
(no pytest-asyncio installed), so an un-awaited coroutine would silently
pass without ever running its assertions.
"""

from unittest.mock import patch

import httpx
import pytest
from asgiref.sync import async_to_sync

from mcp.models import MCPServer
from mcp.oauth import (
    DynamicOAuthCallbackError,
    DynamicOAuthDiscoveryService,
    DynamicOAuthFlowError,
    DynamicOAuthRegistrationError,
    MCPDynamicOAuthFlow,
    PKCEFlow,
)

from .conftest import make_server

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fakes for httpx.AsyncClient(...) as an async context manager.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers_override=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text or ""
        self.headers = {"content-type": "application/json", **(headers_override or {})}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=self  # type: ignore[arg-type]
            )


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient supporting `async with ... as client`.

    Either a single ``response`` answers every get/post, or
    ``url_responses`` (a dict keyed by exact request URL) routes each
    call to its own canned response — needed once discovery makes
    several requests to different URLs in one flow. If ``calls`` (a
    list) is supplied, every get/post records its kwargs there so tests
    can assert on what was actually sent — e.g. that PKCE's
    code_verifier reached the token endpoint.
    """

    def __init__(self, response=None, url_responses=None, raise_exc=None, calls=None, **_kwargs):
        self._response = response
        self._url_responses = url_responses
        self._raise_exc = raise_exc
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _respond(self, url):
        if self._raise_exc:
            raise self._raise_exc
        if self._url_responses is not None:
            return self._url_responses.get(url, _FakeResponse(404))
        return self._response

    async def get(self, url, *args, **kwargs):
        if self._calls is not None:
            self._calls.append({"args": (url, *args), "kwargs": kwargs})
        return self._respond(url)

    async def post(self, url, *args, **kwargs):
        if self._calls is not None:
            self._calls.append({"args": (url, *args), "kwargs": kwargs})
        return self._respond(url)


def _client_factory(response=None, url_responses=None, raise_exc=None, calls=None):
    def factory(*args, **kwargs):
        return _FakeAsyncClient(
            response=response, url_responses=url_responses, raise_exc=raise_exc, calls=calls
        )

    return factory


# ---------------------------------------------------------------------------
# PKCE / state generation
# ---------------------------------------------------------------------------


def test_pkce_state_is_unique_and_unguessable():
    states = {PKCEFlow.generate_state() for _ in range(50)}
    assert len(states) == 50
    assert all(len(s) >= 32 for s in states)


def test_pkce_challenge_is_deterministic_s256_of_verifier():
    verifier = PKCEFlow.generate_verifier()
    challenge_1 = PKCEFlow.generate_challenge(verifier)
    challenge_2 = PKCEFlow.generate_challenge(verifier)
    assert challenge_1 == challenge_2
    # Any change to the verifier must change the challenge (binds the
    # authorization request to the code exchange — this IS the CSRF/
    # code-interception defense PKCE provides).
    assert PKCEFlow.generate_challenge(verifier + "x") != challenge_1


def test_pkce_authorization_url_includes_state_and_challenge():
    url = PKCEFlow.build_authorization_url(
        authorization_endpoint="https://auth.example.com/authorize",
        client_id="client-123",
        redirect_uri="https://us.example.com/callback",
        code_challenge="challenge-abc",
        state="state-xyz",
    )
    assert "state=state-xyz" in url
    assert "code_challenge=challenge-abc" in url
    assert "code_challenge_method=S256" in url


# ---------------------------------------------------------------------------
# OAuth server metadata discovery
# ---------------------------------------------------------------------------


def test_discovery_parses_well_known_metadata():
    """No PRM, no WWW-Authenticate: falls back to same-origin AS discovery
    at the server's own well-known URL (pre-RFC9728 servers)."""
    service = DynamicOAuthDiscoveryService()
    metadata_body = {
        "issuer": "https://mcp.example.com",
        "authorization_endpoint": "https://mcp.example.com/authorize",
        "token_endpoint": "https://mcp.example.com/token",
        "registration_endpoint": "https://mcp.example.com/register",
        "code_challenge_methods_supported": ["S256"],
    }
    with patch(
        "mcp.oauth_metadata.httpx.AsyncClient",
        side_effect=_client_factory(response=_FakeResponse(200, metadata_body)),
    ):
        metadata = async_to_sync(service.discover)("https://mcp.example.com/mcp")

    assert metadata.token_endpoint == "https://mcp.example.com/token"
    assert metadata.supports_dynamic_registration is True
    assert metadata.supports_pkce is True


def test_discovery_falls_back_to_defaults_on_404():
    service = DynamicOAuthDiscoveryService()
    with patch(
        "mcp.oauth_metadata.httpx.AsyncClient",
        side_effect=_client_factory(response=_FakeResponse(404)),
    ):
        metadata = async_to_sync(service.discover)("https://mcp.example.com/mcp")

    assert metadata.authorization_endpoint == "https://mcp.example.com/authorize"
    # `with_defaults` guesses a conventional /register endpoint even
    # though the server never actually advertised support for it.
    assert metadata.registration_endpoint == "https://mcp.example.com/register"


def test_discovery_follows_protected_resource_metadata_to_a_different_origin():
    """401 + WWW-Authenticate resource_metadata → PRM → authorization_servers
    can name an authorization server on an entirely different origin."""
    service = DynamicOAuthDiscoveryService()
    calls = []
    responses = {
        "https://mcp.example.com/mcp": _FakeResponse(
            401,
            headers_override={
                "www-authenticate": (
                    'Bearer resource_metadata="https://mcp.example.com/.well-known/'
                    'oauth-protected-resource/mcp", scope="files:read"'
                )
            },
        ),
        "https://mcp.example.com/.well-known/oauth-protected-resource/mcp": _FakeResponse(
            200, {"resource": "https://mcp.example.com/mcp", "authorization_servers": ["https://auth.example.org"]}
        ),
        "https://auth.example.org/.well-known/oauth-authorization-server": _FakeResponse(
            200,
            {
                "issuer": "https://auth.example.org",
                "authorization_endpoint": "https://auth.example.org/authorize",
                "token_endpoint": "https://auth.example.org/token",
            },
        ),
    }
    with patch(
        "mcp.oauth_metadata.httpx.AsyncClient",
        side_effect=_client_factory(url_responses=responses, calls=calls),
    ):
        metadata = async_to_sync(service.discover)("https://mcp.example.com/mcp")

    assert metadata.issuer == "https://auth.example.org"
    assert metadata.token_endpoint == "https://auth.example.org/token"
    # The 401 challenge's scope is the spec's first-priority scope source.
    assert metadata.scopes_supported == ["files:read"]


def test_discovery_rejects_authorization_server_metadata_with_mismatched_issuer():
    """A metadata document whose `issuer` doesn't match the URL it was
    fetched from must be rejected (RFC 8414 §3.3) — falls through to
    `with_defaults` rather than trusting it."""
    service = DynamicOAuthDiscoveryService()
    responses = {
        "https://mcp.example.com/mcp": _FakeResponse(404),
        "https://mcp.example.com/.well-known/oauth-protected-resource/mcp": _FakeResponse(404),
        "https://mcp.example.com/.well-known/oauth-protected-resource": _FakeResponse(404),
        "https://mcp.example.com/.well-known/oauth-authorization-server": _FakeResponse(
            200, {"issuer": "https://attacker.example", "token_endpoint": "https://attacker.example/token"}
        ),
        "https://mcp.example.com/.well-known/openid-configuration": _FakeResponse(404),
    }
    with patch(
        "mcp.oauth_metadata.httpx.AsyncClient",
        side_effect=_client_factory(url_responses=responses),
    ):
        metadata = async_to_sync(service.discover)("https://mcp.example.com/mcp")

    # Fell back to defaults rather than trusting the spoofed document.
    assert metadata.token_endpoint == "https://mcp.example.com/token"


def test_register_client_raises_on_http_error():
    service = DynamicOAuthDiscoveryService()
    with patch(
        "mcp.oauth.httpx.AsyncClient",
        side_effect=_client_factory(
            response=_FakeResponse(400, text="bad request")
        ),
    ):
        with pytest.raises(DynamicOAuthRegistrationError):
            async_to_sync(service.register_client)(
                "https://mcp.example.com/register",
                "https://us.example.com/callback",
            )


# ---------------------------------------------------------------------------
# start_authorization
# ---------------------------------------------------------------------------


def test_start_authorization_requires_manual_client_id_without_dynamic_registration(
    user_a,
):
    """Server has no registration_endpoint and caller supplies no client_id
    → must fail closed rather than silently proceed unauthenticated."""
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
            "code_challenge_methods_supported": ["S256"],
        },
    )

    flow = MCPDynamicOAuthFlow()
    with pytest.raises(DynamicOAuthFlowError):
        async_to_sync(flow.start_authorization)(server)


def test_start_authorization_stores_pkce_verifier_and_state(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_client_id="preexisting-client-id",
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
            "code_challenge_methods_supported": ["S256"],
        },
    )

    flow = MCPDynamicOAuthFlow()
    result = async_to_sync(flow.start_authorization)(server)

    server.refresh_from_db()
    assert server.oauth_state == result["state"]
    assert server.oauth_pkce_verifier != ""
    assert result["state"] in result["authorization_url"]
    # PKCE verifier must never be encrypted-away-to-empty or leaked in the URL.
    assert server.oauth_pkce_verifier not in result["authorization_url"]
    # RFC 8707 resource indicator, sent unconditionally per the MCP spec.
    assert "resource=https%3A%2F%2Fmcp.example.com%2Fmcp" in result["authorization_url"]


# ---------------------------------------------------------------------------
# handle_callback — CSRF/state validation
# ---------------------------------------------------------------------------


def test_callback_rejects_unknown_state(user_a):
    """No server has this oauth_state → must reject, not silently no-op."""
    flow = MCPDynamicOAuthFlow()
    with pytest.raises(DynamicOAuthCallbackError):
        async_to_sync(flow.handle_callback)(
            state="never-issued-state-token", code="some-code"
        )


def test_callback_rejects_when_no_code_present(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        oauth_state="mcp:pending-state",
    )
    flow = MCPDynamicOAuthFlow()
    with pytest.raises(DynamicOAuthCallbackError):
        async_to_sync(flow.handle_callback)(state=server.oauth_state, code="")


def test_callback_deletes_newly_created_server_on_user_cancellation(user_a):
    """Provider redirected with an error, and the server has never been
    authorized (no tokens, no tools) — treated as an abandoned draft and
    removed rather than left as a half-configured OAuth server."""
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        oauth_state="mcp:pending-state",
    )
    server_id = server.id

    flow = MCPDynamicOAuthFlow()
    with pytest.raises(DynamicOAuthCallbackError):
        async_to_sync(flow.handle_callback)(
            state=server.oauth_state, error="access_denied"
        )

    assert not MCPServer.objects.filter(id=server_id).exists()


def test_callback_keeps_previously_connected_server_on_reauth_denial(user_a):
    """Server already has a token (was connected before) — a denied
    re-authorization must NOT delete it, only clear the pending state."""
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        oauth_state="mcp:pending-state",
        oauth_access_token="already-have-a-token",
    )
    server_id = server.id

    flow = MCPDynamicOAuthFlow()
    with pytest.raises(DynamicOAuthCallbackError):
        async_to_sync(flow.handle_callback)(
            state=server.oauth_state, error="access_denied"
        )

    server.refresh_from_db()
    assert MCPServer.objects.filter(id=server_id).exists()
    assert server.oauth_state == ""
    assert server.oauth_access_token == "already-have-a-token"


def test_callback_success_stores_tokens_and_marks_connected(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_state="mcp:pending-state",
        oauth_pkce_verifier="verifier-value",
        oauth_client_id="client-id",
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
            "code_challenge_methods_supported": ["S256"],
        },
    )

    token_response = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "read write",
    }
    calls = []

    flow = MCPDynamicOAuthFlow()
    with patch(
        "mcp.oauth.httpx.AsyncClient",
        side_effect=_client_factory(
            response=_FakeResponse(200, token_response), calls=calls
        ),
    ):
        result_server = async_to_sync(flow.handle_callback)(
            state=server.oauth_state, code="auth-code-123"
        )

    assert result_server.id == server.id
    result_server.refresh_from_db()
    assert result_server.oauth_access_token == "new-access-token"
    assert result_server.oauth_refresh_token == "new-refresh-token"
    assert result_server.oauth_scopes == ["read", "write"]
    # Flow fields must be cleared once the exchange completes.
    assert result_server.oauth_state == ""
    assert result_server.oauth_pkce_verifier == ""
    assert result_server.connection_healthy is True

    # RFC 8707 resource indicator must reach the token endpoint too.
    assert len(calls) == 1
    assert calls[0]["kwargs"]["data"]["resource"] == "https://mcp.example.com/mcp"

    # PKCE must actually be transmitted to the token endpoint — a test
    # that only checks the stored result would stay green even if PKCE
    # were silently dropped from the exchange request.
    assert len(calls) == 1
    sent_data = calls[0]["kwargs"]["data"]
    assert sent_data["code"] == "auth-code-123"
    assert sent_data["code_verifier"] == "verifier-value"
    assert sent_data["client_id"] == "client-id"


def test_callback_state_is_single_use_replay_rejected(user_a):
    """Strongest CSRF guarantee: once a state has been consumed by a
    successful callback, replaying the same state must be rejected —
    it no longer matches any server's oauth_state (store_oauth_tokens
    clears it on success)."""
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_state="mcp:one-time-state",
        oauth_pkce_verifier="verifier-value",
        oauth_client_id="client-id",
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
            "code_challenge_methods_supported": ["S256"],
        },
    )
    used_state = server.oauth_state
    token_response = {"access_token": "tok", "token_type": "Bearer"}

    flow = MCPDynamicOAuthFlow()
    with patch(
        "mcp.oauth.httpx.AsyncClient",
        side_effect=_client_factory(response=_FakeResponse(200, token_response)),
    ):
        async_to_sync(flow.handle_callback)(state=used_state, code="auth-code-1")

    # Replay: same state, fresh code — must be rejected, no server has
    # this oauth_state anymore.
    with pytest.raises(DynamicOAuthCallbackError):
        async_to_sync(flow.handle_callback)(state=used_state, code="auth-code-2")


def test_callback_clears_pending_flow_fields_on_token_exchange_failure(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        transport_type=MCPServer.TransportType.HTTP,
        oauth_state="mcp:pending-state",
        oauth_pkce_verifier="verifier-value",
        oauth_client_id="client-id",
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
            "code_challenge_methods_supported": ["S256"],
        },
    )

    flow = MCPDynamicOAuthFlow()
    with patch(
        "mcp.oauth.httpx.AsyncClient",
        side_effect=_client_factory(response=_FakeResponse(400, text="denied")),
    ):
        with pytest.raises(DynamicOAuthCallbackError):
            async_to_sync(flow.handle_callback)(
                state=server.oauth_state, code="auth-code-123"
            )

    server.refresh_from_db()
    assert server.oauth_state == ""
    assert server.oauth_pkce_verifier == ""
    assert server.oauth_access_token == ""


# ---------------------------------------------------------------------------
# refresh_server_token
# ---------------------------------------------------------------------------


def test_refresh_server_token_returns_false_without_refresh_token(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        oauth_refresh_token="",
    )
    flow = MCPDynamicOAuthFlow()
    result = async_to_sync(flow.refresh_server_token)(server)
    assert result is False


def test_refresh_server_token_updates_access_token_on_success(user_a):
    server = make_server(
        user_a,
        npm_package="",
        remote_url="https://mcp.example.com/mcp",
        auth_type=MCPServer.AuthType.OAUTH,
        oauth_refresh_token="existing-refresh-token",
        oauth_client_id="client-id",
        oauth_metadata={
            "issuer": "https://mcp.example.com",
            "authorization_endpoint": "https://mcp.example.com/authorize",
            "token_endpoint": "https://mcp.example.com/token",
            "registration_endpoint": "",
        },
    )
    token_response = {
        "access_token": "refreshed-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    flow = MCPDynamicOAuthFlow()
    with patch(
        "mcp.oauth.httpx.AsyncClient",
        side_effect=_client_factory(response=_FakeResponse(200, token_response)),
    ):
        result = async_to_sync(flow.refresh_server_token)(server)

    assert result is True
    server.refresh_from_db()
    assert server.oauth_access_token == "refreshed-access-token"
    # Refresh token is preserved when the provider doesn't rotate it.
    assert server.oauth_refresh_token == "existing-refresh-token"
