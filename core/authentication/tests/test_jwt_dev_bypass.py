"""Task-29 H4 regression: dev-token bypass MUST require explicit
opt-in via ``DEV_TOKEN_BYPASS=True`` AND ``DJANGO_ENV != "prod"``.

Previously, a single misconfiguration (``DEBUG=True`` in a prod
deploy) would have accepted any token starting with ``dev-``. Now
both conditions must hold.
"""
from __future__ import annotations

from django.test import TestCase, override_settings

from authentication.jwt_utils import JWTManager


class DevTokenBypassTest(TestCase):
    @override_settings(DEV_TOKEN_BYPASS=True, DJANGO_ENV="dev")
    def test_dev_token_accepted_when_explicit_bypass_set(self):
        payload = JWTManager.verify_token("dev-access-token-abc", "access")
        assert payload is not None
        assert payload["email"] == "dev@example.com"
        assert payload["type"] == "access"

    @override_settings(DEV_TOKEN_BYPASS=False, DJANGO_ENV="dev")
    def test_dev_token_rejected_when_bypass_false(self):
        payload = JWTManager.verify_token("dev-access-token-abc", "access")
        assert payload is None

    @override_settings(DEV_TOKEN_BYPASS=True, DJANGO_ENV="prod")
    def test_dev_token_rejected_in_prod_env_even_if_bypass_true(self):
        # Defense in depth: even if env var is misconfigured to enable
        # bypass, DJANGO_ENV=prod hard-blocks it.
        payload = JWTManager.verify_token("dev-access-token-abc", "access")
        assert payload is None

    @override_settings(DEV_TOKEN_BYPASS=True, DJANGO_ENV="staging")
    def test_dev_token_accepted_in_staging(self):
        # Staging is non-prod, so bypass works there for the operator
        # to issue smoke tokens. (Operator must explicitly opt in by
        # setting DEV_TOKEN_BYPASS=True — staging defaults to False
        # via prod-inherited settings.)
        payload = JWTManager.verify_token("dev-access-token-abc", "access")
        assert payload is not None

    @override_settings(DEV_TOKEN_BYPASS=True, DJANGO_ENV="dev")
    def test_non_dev_prefix_falls_through_to_real_verify(self):
        # A real JWT that fails verification returns None.
        payload = JWTManager.verify_token("not-a-real-jwt", "access")
        assert payload is None

    @override_settings(DEV_TOKEN_BYPASS=True, DJANGO_ENV="dev")
    def test_dev_refresh_token_returns_refresh_type(self):
        payload = JWTManager.verify_token("dev-refresh-xyz", "refresh")
        assert payload is not None
        assert payload["type"] == "refresh"
