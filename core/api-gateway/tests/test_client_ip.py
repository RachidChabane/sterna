"""Task-29 H1 regression: api-gateway client-IP helper mirrors the
Django side (CF-Connecting-IP > XFF > client.host).

The helper is stateless and reads ``CF_REQUIRE_HEADER`` from os.environ
directly, so we monkeypatch the env var.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from gateway.utils.client_ip import get_client_ip


def _request(headers: dict, client_host: str | None = "10.0.0.1"):
    """Build a minimal stand-in for a Starlette Request."""
    req = MagicMock()
    # Starlette's Headers behave dict-like for .get(). MagicMock(spec=dict)
    # exposes .get directly.
    req.headers.get = headers.get
    if client_host is None:
        req.client = None
    else:
        client = MagicMock()
        client.host = client_host
        req.client = client
    url = MagicMock()
    url.path = "/test"
    req.url = url
    return req


def test_cf_header_used_when_present(monkeypatch):
    monkeypatch.setenv("CF_REQUIRE_HEADER", "false")
    req = _request(
        {"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "9.9.9.9"}
    )
    assert get_client_ip(req) == "1.2.3.4"


def test_fallback_to_xff_when_cf_absent(monkeypatch):
    monkeypatch.setenv("CF_REQUIRE_HEADER", "false")
    req = _request({"X-Forwarded-For": "5.6.7.8, 8.8.8.8"})
    assert get_client_ip(req) == "5.6.7.8"


def test_fallback_to_client_host_when_all_absent(monkeypatch):
    monkeypatch.setenv("CF_REQUIRE_HEADER", "false")
    req = _request({}, client_host="192.168.1.5")
    assert get_client_ip(req) == "192.168.1.5"


def test_returns_empty_when_no_client(monkeypatch):
    monkeypatch.setenv("CF_REQUIRE_HEADER", "false")
    req = _request({}, client_host=None)
    assert get_client_ip(req) == ""


def test_logs_when_cf_required_and_missing(monkeypatch, caplog):
    monkeypatch.setenv("CF_REQUIRE_HEADER", "true")
    req = _request({"X-Forwarded-For": "5.6.7.8"})
    with caplog.at_level("WARNING", logger="gateway.security.client_ip"):
        ip = get_client_ip(req)
    assert any(
        "ip_extract.missing_cf_header" in record.message
        for record in caplog.records
    )
    # Fail-open: still return a fallback IP.
    assert ip == "5.6.7.8"


def test_no_log_when_cf_required_and_present(monkeypatch, caplog):
    monkeypatch.setenv("CF_REQUIRE_HEADER", "true")
    req = _request({"CF-Connecting-IP": "1.2.3.4"})
    with caplog.at_level("WARNING", logger="gateway.security.client_ip"):
        ip = get_client_ip(req)
    assert all(
        "missing_cf_header" not in record.message for record in caplog.records
    )
    assert ip == "1.2.3.4"


def test_strips_xff_whitespace(monkeypatch):
    monkeypatch.setenv("CF_REQUIRE_HEADER", "false")
    req = _request({"X-Forwarded-For": "  4.4.4.4 ,  8.8.8.8"})
    assert get_client_ip(req) == "4.4.4.4"
