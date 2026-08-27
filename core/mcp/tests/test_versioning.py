"""Unit tests for the pure negotiation helpers in mcp/versioning.py.

End-to-end negotiation over the HTTP transport (handshake retries,
header injection) is covered in test_client.py; these are the fast,
precise checks of the negotiation rules in isolation.
"""

import pytest

from mcp.exceptions import MCPUnsupportedProtocolVersionError
from mcp.versioning import (
    SUPPORTED_PROTOCOL_VERSIONS,
    accept_negotiated_version,
    extract_server_supported_versions,
    select_mutual_version,
)


def test_accept_negotiated_version_accepts_the_requested_version():
    assert accept_negotiated_version("2025-11-25", "2025-11-25") == "2025-11-25"


def test_accept_negotiated_version_accepts_another_supported_version():
    assert accept_negotiated_version("2025-11-25", "2024-11-05") == "2024-11-05"


def test_accept_negotiated_version_rejects_an_unknown_version():
    with pytest.raises(MCPUnsupportedProtocolVersionError):
        accept_negotiated_version("2025-11-25", "1900-01-01")


def test_accept_negotiated_version_is_lenient_on_a_missing_field():
    """A response that omits `protocolVersion` is spec-non-compliant but
    not a declared mismatch — assume the requested version rather than
    disconnecting a server that would otherwise work."""
    assert accept_negotiated_version("2025-11-25", "") == "2025-11-25"


def test_extract_server_supported_versions_reads_the_data_field():
    error = {"code": -32602, "message": "bad version", "data": {"supported": ["2025-06-18", "2024-11-05"]}}
    assert extract_server_supported_versions(error) == ["2025-06-18", "2024-11-05"]


def test_extract_server_supported_versions_returns_none_without_a_list():
    assert extract_server_supported_versions({"message": "bad version"}) is None
    assert extract_server_supported_versions({"data": {"supported": "not-a-list"}}) is None


def test_select_mutual_version_prefers_the_newest_shared_revision():
    assert select_mutual_version(["2024-11-05", "2025-06-18"]) == "2025-06-18"


def test_select_mutual_version_returns_none_without_overlap():
    assert select_mutual_version(["1900-01-01"]) is None


def test_supported_versions_are_newest_first():
    assert SUPPORTED_PROTOCOL_VERSIONS == sorted(SUPPORTED_PROTOCOL_VERSIONS, reverse=True)
