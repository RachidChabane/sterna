"""Task-29 H1 regression: DRF default throttle subclasses MUST key
on the CF-aware client IP, not REMOTE_ADDR.

We don't drive a full HTTP throttle cycle here — that's brittle. We
just verify the override: ``get_ident`` returns the same value that
``sterna.client_ip.get_client_ip`` would return.
"""
from __future__ import annotations

from django.http import HttpRequest
from django.test import TestCase, override_settings

from sterna.throttling import AnonRateThrottle, UserRateThrottle


def _request_with(meta: dict) -> HttpRequest:
    req = HttpRequest()
    req.META.update(meta)
    return req


class ThrottleGetIdentTest(TestCase):
    def test_anon_throttle_uses_cf_header(self):
        req = _request_with(
            {
                "HTTP_CF_CONNECTING_IP": "1.2.3.4",
                "HTTP_X_FORWARDED_FOR": "9.9.9.9",
                "REMOTE_ADDR": "10.0.0.1",
            }
        )
        assert AnonRateThrottle().get_ident(req) == "1.2.3.4"

    def test_user_throttle_uses_cf_header(self):
        req = _request_with(
            {
                "HTTP_CF_CONNECTING_IP": "1.2.3.4",
                "REMOTE_ADDR": "10.0.0.1",
            }
        )
        assert UserRateThrottle().get_ident(req) == "1.2.3.4"

    def test_falls_back_to_xff_when_cf_absent(self):
        req = _request_with(
            {
                "HTTP_X_FORWARDED_FOR": "5.6.7.8",
                "REMOTE_ADDR": "10.0.0.1",
            }
        )
        with override_settings(CF_REQUIRE_HEADER=False):
            assert AnonRateThrottle().get_ident(req) == "5.6.7.8"
