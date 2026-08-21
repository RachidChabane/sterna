"""Task-29 H1 regression: ``get_client_ip`` MUST prefer
``CF-Connecting-IP`` and emit a suspicious-activity event when the
header is required (prod/staging) but missing.
"""
from __future__ import annotations

from unittest.mock import patch

from django.http import HttpRequest
from django.test import TestCase, override_settings

from sterna.client_ip import get_client_ip


def _request_with(meta: dict) -> HttpRequest:
    req = HttpRequest()
    req.META.update(meta)
    return req


class ClientIPExtractionTest(TestCase):
    def test_cf_header_used_when_present(self):
        req = _request_with(
            {
                "HTTP_CF_CONNECTING_IP": "1.2.3.4",
                "HTTP_X_FORWARDED_FOR": "9.9.9.9, 8.8.8.8",
                "REMOTE_ADDR": "10.0.0.1",
            }
        )
        assert get_client_ip(req) == "1.2.3.4"

    def test_fallback_to_xff_when_cf_absent_and_require_off(self):
        req = _request_with(
            {
                "HTTP_X_FORWARDED_FOR": "5.6.7.8, 9.10.11.12",
                "REMOTE_ADDR": "10.0.0.1",
            }
        )
        with override_settings(CF_REQUIRE_HEADER=False):
            assert get_client_ip(req) == "5.6.7.8"

    def test_fallback_to_remote_addr_when_all_absent(self):
        req = _request_with({"REMOTE_ADDR": "192.168.1.5"})
        with override_settings(CF_REQUIRE_HEADER=False):
            assert get_client_ip(req) == "192.168.1.5"

    def test_returns_empty_string_when_no_signal(self):
        req = _request_with({})
        with override_settings(CF_REQUIRE_HEADER=False):
            assert get_client_ip(req) == ""

    def test_require_cf_emits_suspicious_when_missing(self):
        req = _request_with(
            {
                "HTTP_X_FORWARDED_FOR": "5.6.7.8",
                "REMOTE_ADDR": "10.0.0.1",
            }
        )
        with override_settings(CF_REQUIRE_HEADER=True), patch(
            "exceptions.emit_suspicious_activity"
        ) as mock_emit:
            ip = get_client_ip(req)
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["category"] == "ip_extract"
        assert kwargs["reason"] == "missing_cf_header"
        # Even with require, we still fall open to XFF/REMOTE_ADDR.
        assert ip == "5.6.7.8"

    def test_require_cf_does_not_emit_when_header_present(self):
        req = _request_with(
            {"HTTP_CF_CONNECTING_IP": "1.2.3.4", "REMOTE_ADDR": "10.0.0.1"}
        )
        with override_settings(CF_REQUIRE_HEADER=True), patch(
            "exceptions.emit_suspicious_activity"
        ) as mock_emit:
            ip = get_client_ip(req)
        mock_emit.assert_not_called()
        assert ip == "1.2.3.4"

    def test_strips_whitespace_in_xff(self):
        req = _request_with({"HTTP_X_FORWARDED_FOR": "  4.4.4.4 , 8.8.8.8"})
        with override_settings(CF_REQUIRE_HEADER=False):
            assert get_client_ip(req) == "4.4.4.4"
