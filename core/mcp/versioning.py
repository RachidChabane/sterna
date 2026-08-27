"""MCP handshake-based protocol version negotiation.

Protocol revisions up to and including 2025-11-25 negotiate a version
during the `initialize` handshake (the MCP lifecycle spec's "Version
Negotiation"): the client sends the newest revision it supports, and
the server replies with that same revision or with another one it
supports. The client accepts any revision it also implements and
disconnects otherwise. A server that rejects the request outright MAY
report the revisions it supports in the error's `data.supported` list,
in which case the client retries once with the newest mutually
supported revision.

The later, per-request `_meta`-based negotiation model (revision
2026-07-28 and later) is a distinct, session-less protocol era and is
out of scope here: this module only negotiates the handshake style
still spoken by deployed MCP servers.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .exceptions import MCPConnectionError, MCPUnsupportedProtocolVersionError
from .protocol import MCPResponse

# Every handshake-based protocol revision this client understands,
# newest first. `initialize` requests the first entry.
SUPPORTED_PROTOCOL_VERSIONS: List[str] = [
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]

# The revision requested on the first `initialize` attempt.
PREFERRED_PROTOCOL_VERSION: str = SUPPORTED_PROTOCOL_VERSIONS[0]

SendInitialize = Callable[[str], Awaitable[MCPResponse]]


def extract_server_supported_versions(error: Dict[str, Any]) -> Optional[List[str]]:
    """Read a version-mismatch error's `data.supported` list, if present."""
    data = error.get("data")
    if not isinstance(data, dict):
        return None
    supported = data.get("supported")
    if isinstance(supported, list) and all(isinstance(v, str) for v in supported):
        return supported
    return None


def select_mutual_version(server_supported: List[str]) -> Optional[str]:
    """Return the newest revision both this client and the server support."""
    for version in SUPPORTED_PROTOCOL_VERSIONS:
        if version in server_supported:
            return version
    return None


def accept_negotiated_version(requested: str, response_version: str) -> str:
    """Validate the `protocolVersion` an `initialize` response declared.

    The server may echo the requested version or reply with another
    revision it supports; either is acceptable as long as this client
    also implements it. A response that omits `protocolVersion`
    entirely is spec-non-compliant but not a version mismatch — treat
    it as having honored the requested version rather than disconnecting,
    since nothing was actually declared to be incompatible.
    """
    if not response_version:
        return requested
    if response_version in SUPPORTED_PROTOCOL_VERSIONS:
        return response_version
    raise MCPUnsupportedProtocolVersionError(
        f"Server negotiated protocol version {response_version!r}, which this "
        f"client does not support (requested {requested!r}; this client "
        f"supports {SUPPORTED_PROTOCOL_VERSIONS})"
    )


async def negotiate_handshake_version(
    send_initialize: SendInitialize,
) -> Tuple[MCPResponse, str]:
    """Run the `initialize` exchange, retrying once on a version mismatch.

    Args:
        send_initialize: sends an `initialize` request for the given
            protocol version and returns the server's response.

    Returns:
        The accepted `initialize` response and the protocol version the
        server negotiated.

    Raises:
        MCPConnectionError: the server rejected the request and no
            mutually supported version could be found.
        MCPUnsupportedProtocolVersionError: the server negotiated a
            version this client does not implement.
    """
    requested = PREFERRED_PROTOCOL_VERSION
    response = await send_initialize(requested)

    if response.is_error():
        error = response.error or {}
        server_supported = extract_server_supported_versions(error)
        mutual = select_mutual_version(server_supported) if server_supported else None
        if mutual is None:
            error_msg = error.get("message", "Unknown error")
            raise MCPConnectionError(f"Handshake failed: {error_msg}")

        requested = mutual
        response = await send_initialize(requested)
        if response.is_error():
            error_msg = (response.error or {}).get("message", "Unknown error")
            raise MCPConnectionError(f"Handshake failed: {error_msg}")

    response_version = (response.result or {}).get("protocolVersion", "")
    negotiated = accept_negotiated_version(requested, response_version)
    return response, negotiated
