"""MCPRemoteHTTPClient: protocol version negotiation, MCP-Protocol-Version
header injection, and MCP endpoint pinning (mcp/client.py, mcp/versioning.py).

Outbound HTTP is mocked at the transport seam via `httpx.MockTransport`,
so `MCPRemoteHTTPClient` runs its real `httpx.AsyncClient` machinery
(streaming POSTs, SSE-capable responses) against an in-process handler
instead of the network.

Pattern (matches test_oauth_flow.py): sync ``def test_*`` methods,
async call sites wrapped in ``async_to_sync``.
"""

import json
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from asgiref.sync import async_to_sync

from mcp.client import MCPRemoteHTTPClient
from mcp.exceptions import MCPUnsupportedProtocolVersionError

BASE_URL = "https://mcp.example.com"

# `mcp.client` and this module share the same `httpx` module object, so
# patching `mcp.client.httpx.AsyncClient` patches it process-wide.
# Capture the real class first so the factory below can still build a
# genuine client instead of recursing into its own patch.
_RealAsyncClient = httpx.AsyncClient


@contextmanager
def _mock_transport(handler):
    """Patch `mcp.client.httpx.AsyncClient` to route through `handler`.

    `handler(request) -> httpx.Response` sees exactly what
    `MCPRemoteHTTPClient` sends — a real `httpx.Request` — and the
    client gets back a real `httpx.AsyncClient` (with a mock transport
    swapped in), so streaming and SSE parsing behave as in production.
    """

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=httpx.MockTransport(handler), **kwargs)

    with patch("mcp.client.httpx.AsyncClient", side_effect=factory):
        yield


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def _initialize_result(version: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "protocolVersion": version,
                "capabilities": {},
                "serverInfo": {"name": "test-server", "version": "0.0.1"},
            },
        },
        headers={"mcp-session-id": "sess-abc"},
    )


def _version_error(supported: list) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "error": {
                "code": -32602,
                "message": "Unsupported protocol version",
                "data": {"supported": supported, "requested": "2025-11-25"},
            },
        },
    )


async def _connect_and_handshake(client: MCPRemoteHTTPClient) -> dict:
    await client.connect()
    return await client.handshake()


def test_handshake_accepts_echoed_version():
    def handler(request: httpx.Request) -> httpx.Response:
        if _body(request).get("method") == "initialize":
            return _initialize_result("2025-11-25")
        return httpx.Response(202)

    client = MCPRemoteHTTPClient(url=BASE_URL)
    with _mock_transport(handler):
        async_to_sync(_connect_and_handshake)(client)

    assert client.negotiated_protocol_version == "2025-11-25"


def test_handshake_accepts_a_different_version_the_server_chose():
    """Server MAY answer with another version it supports instead of the
    one requested (MCP lifecycle spec); the client accepts it."""
    def handler(request: httpx.Request) -> httpx.Response:
        if _body(request).get("method") == "initialize":
            return _initialize_result("2025-06-18")
        return httpx.Response(202)

    client = MCPRemoteHTTPClient(url=BASE_URL)
    with _mock_transport(handler):
        async_to_sync(_connect_and_handshake)(client)

    assert client.negotiated_protocol_version == "2025-06-18"


def test_handshake_disconnects_on_a_version_this_client_does_not_support():
    def handler(request: httpx.Request) -> httpx.Response:
        return _initialize_result("1900-01-01")

    client = MCPRemoteHTTPClient(url=BASE_URL)
    with _mock_transport(handler):
        with pytest.raises(MCPUnsupportedProtocolVersionError):
            async_to_sync(_connect_and_handshake)(client)


def test_handshake_tolerates_a_response_missing_protocol_version():
    """A non-compliant server that omits `protocolVersion` entirely must
    not be treated as an unsupported-version mismatch — that would
    disconnect a server that otherwise works fine."""
    def handler(request: httpx.Request) -> httpx.Response:
        if _body(request).get("method") == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": "1", "result": {"capabilities": {}}},
            )
        return httpx.Response(202)

    client = MCPRemoteHTTPClient(url=BASE_URL)
    with _mock_transport(handler):
        async_to_sync(_connect_and_handshake)(client)

    assert client.negotiated_protocol_version == "2025-11-25"


def test_handshake_retries_once_with_a_mutually_supported_version():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = _body(request)
        if body.get("method") != "initialize":
            return httpx.Response(202)
        requested = body["params"]["protocolVersion"]
        attempts.append(requested)
        if requested == "2025-11-25":
            return _version_error(supported=["2025-06-18"])
        return _initialize_result(requested)

    client = MCPRemoteHTTPClient(url=BASE_URL)
    with _mock_transport(handler):
        async_to_sync(_connect_and_handshake)(client)

    assert attempts == ["2025-11-25", "2025-06-18"]
    assert client.negotiated_protocol_version == "2025-06-18"


def test_protocol_version_header_absent_on_initialize_present_after():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = _body(request)
        method = body.get("method")
        seen_headers[method] = request.headers.get("mcp-protocol-version")
        if method == "initialize":
            return _initialize_result("2025-11-25")
        if method == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": {"tools": []}})
        return httpx.Response(202)

    client = MCPRemoteHTTPClient(url=BASE_URL)
    with _mock_transport(handler):
        async_to_sync(_connect_and_handshake)(client)
        async_to_sync(client.list_tools)()

    assert seen_headers["initialize"] is None
    assert seen_headers["tools/list"] == "2025-11-25"


def test_second_call_uses_the_pinned_endpoint_only():
    """The `/mcp` candidate is the one that answers; discovery must not
    re-run on the next call — it should POST straight to `/mcp`."""
    attempted_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempted_paths.append(request.url.path)
        if request.url.path != "/mcp":
            return httpx.Response(404)
        body = _body(request)
        if body.get("method") == "initialize":
            return _initialize_result("2025-11-25")
        if body.get("method") == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": {"tools": []}})
        return httpx.Response(202)

    client = MCPRemoteHTTPClient(url=BASE_URL)
    with _mock_transport(handler):
        async_to_sync(_connect_and_handshake)(client)
        attempted_paths.clear()
        async_to_sync(client.list_tools)()

    # Only the pinned endpoint was tried for the second call — no re-probing.
    assert attempted_paths == ["/mcp"]
    assert client._pinned_endpoint == "/mcp"
