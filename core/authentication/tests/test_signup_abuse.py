"""Tests for task 19 — signup abuse prevention.

Covers:
- Disposable-email rejection (validator + serializer integration).
- IP velocity gate (24h ceiling alone + service-layer 1h ceiling).
- Turnstile gate (missing token, invalid token, valid token).
- OAuth replay guards (state nonce mint, GitHub state expiry/missing/
  code-reuse, Google credential reuse).
- Vendored-blocklist sanity (catches missing/truncated data file).

The class-level ``patcher`` overrides the validator's blocklist loader
with a small in-memory frozenset so the suite doesn't depend on the
specific contents of the vendored .txt file. A dedicated test
deliberately bypasses the patcher to exercise the real file.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import responses
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from authentication.serializers import RegisterSerializer


class SignupAbuseTests(TestCase):
    """Signup abuse prevention (disposable + velocity + turnstile)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patcher = patch(
            "authentication.validators._load_disposable_domains",
            return_value=frozenset({"mailinator.com", "tempmail.io"}),
        )
        cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.register_url = reverse("authentication:register")

    def _payload(self, **overrides):
        data = {
            "email": "newuser@example.com",
            "password": "ValidPassword123!",
            "password_confirm": "ValidPassword123!",
            "full_name": "New User",
        }
        data.update(overrides)
        return data

    def test_disposable_email_rejected(self):
        response = self.client.post(
            self.register_url,
            self._payload(email="attacker@mailinator.com"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        serializer = RegisterSerializer(
            data=self._payload(email="attacker@mailinator.com")
        )
        self.assertFalse(serializer.is_valid())
        self.assertEqual(serializer.errors["email"][0].code, "disposable_email")

    @override_settings(DISPOSABLE_EMAIL_ALLOWLIST=["legit@mailinator.com"])
    def test_allowlisted_disposable_passes(self):
        response = self.client.post(
            self.register_url,
            self._payload(email="legit@mailinator.com"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_ip_velocity_24h_exceeded(self):
        from authentication.services.signup_guard import (
            SIGNUP_IP_TTL_1H,
            SIGNUP_IP_TTL_24H,
            _key,
        )

        ip = "10.99.0.42"
        # Under the 1h ceiling but already at the 24h ceiling. The view
        # bumps both windows; the 24h count crosses the threshold first.
        cache.set(_key(ip, "1h"), 4, SIGNUP_IP_TTL_1H)
        cache.set(_key(ip, "24h"), 20, SIGNUP_IP_TTL_24H)

        response = self.client.post(
            self.register_url,
            self._payload(),
            format="json",
            REMOTE_ADDR=ip,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "SIGNUP_THROTTLED")
        self.assertEqual(response.data["reason"], "ip_velocity")

    def test_check_ip_velocity_1h_ceiling_alone(self):
        """Task 19's 1h check stands on its own at the service layer.

        The HTTP-view path for the 1h case is covered by task 18's
        ``apply_ratelimit`` tests; this test proves ``check_ip_velocity``
        itself enforces the 1h ceiling so the invariant survives even
        if the decorator stack were removed.
        """
        from authentication.services.signup_guard import (
            BlockReason,
            SIGNUP_IP_TTL_1H,
            SIGNUP_IP_TTL_24H,
            _key,
            check_ip_velocity,
        )

        ip = "10.99.0.43"
        cache.set(_key(ip, "1h"), 5, SIGNUP_IP_TTL_1H)
        cache.set(_key(ip, "24h"), 5, SIGNUP_IP_TTL_24H)
        block = check_ip_velocity(ip)
        self.assertIsNotNone(block)
        self.assertEqual(block.reason, BlockReason.IP_VELOCITY)

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="test-secret")
    def test_missing_turnstile_rejected(self):
        response = self.client.post(
            self.register_url, self._payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "CAPTCHA_REQUIRED")

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="test-secret")
    @responses.activate
    def test_invalid_turnstile_rejected(self):
        responses.add(
            responses.POST,
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            json={"success": False, "error-codes": ["invalid-input-response"]},
            status=200,
        )
        response = self.client.post(
            self.register_url,
            self._payload(turnstile_token="obviously-fake"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "CAPTCHA_FAILED")

    @override_settings(DEBUG=False, TURNSTILE_SECRET_KEY="test-secret")
    @responses.activate
    def test_valid_turnstile_accepted(self):
        responses.add(
            responses.POST,
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            json={"success": True},
            status=200,
        )
        response = self.client.post(
            self.register_url,
            self._payload(turnstile_token="valid-token"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class OAuthReplayGuardTests(TestCase):
    """OAuth state nonce + code/credential reuse guards."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_oauth_state_mint(self):
        response = self.client.post(reverse("authentication:oauth-state"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        state = response.data["state"]
        self.assertEqual(len(state), 32)
        self.assertTrue(cache.get(f"oauth_state:{state}"))

    def test_github_oauth_state_missing_rejected(self):
        response = self.client.post(
            reverse("authentication:github-auth"),
            {"code": "fake-code"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_github_oauth_state_expired_rejected(self):
        response = self.client.post(
            reverse("authentication:github-auth"),
            {"code": "fake-code", "state": "expired-or-never-existed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired or invalid", response.data["error"].lower())

    @responses.activate
    def test_github_oauth_code_reused_rejected(self):
        state_resp = self.client.post(reverse("authentication:oauth-state"))
        state = state_resp.data["state"]

        responses.add(
            responses.POST,
            "https://github.com/login/oauth/access_token",
            json={"access_token": "gh-token", "scope": "user:email"},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"id": 1, "login": "u", "name": "U", "avatar_url": ""},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user/emails",
            json=[
                {"email": "u@example.com", "primary": True, "verified": True}
            ],
            status=200,
        )

        r1 = self.client.post(
            reverse("authentication:github-auth"),
            {"code": "shared-code", "state": state},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        state2 = self.client.post(
            reverse("authentication:oauth-state")
        ).data["state"]
        r2 = self.client.post(
            reverse("authentication:github-auth"),
            {"code": "shared-code", "state": state2},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already used", r2.data["error"].lower())

    @patch("authentication.oauth_views.id_token.verify_oauth2_token")
    def test_google_credential_reuse_rejected(self, mock_verify):
        mock_verify.return_value = {
            "aud": settings.GOOGLE_OAUTH_CLIENT_ID,
            "sub": "google-123",
            "iat": int(time.time()),
            "email": "user@example.com",
            "email_verified": True,
            "given_name": "U",
            "family_name": "X",
            "picture": "",
        }
        r1 = self.client.post(
            reverse("authentication:google-auth"),
            {"credential": "fake-jwt"},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        r2 = self.client.post(
            reverse("authentication:google-auth"),
            {"credential": "fake-jwt"},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already used", r2.data["error"].lower())


class VendoredBlocklistTests(TestCase):
    """Catch deploy bugs where the vendored .txt file is broken."""

    def test_vendored_blocklist_loads_real_file(self):
        """Deliberately bypasses the SignupAbuseTests-level patcher."""
        from authentication.validators import _load_disposable_domains

        _load_disposable_domains.cache_clear()
        try:
            domains = _load_disposable_domains()
            # `mailinator.com` is the canonical disposable-email domain;
            # it has been on the upstream blocklist for >10 years. If
            # the quarterly refresh ever lands a list without it, the
            # refresh PR is responsible for picking a new stable
            # invariant and updating this test.
            self.assertIn("mailinator.com", domains)
            self.assertGreater(len(domains), 100)
        finally:
            _load_disposable_domains.cache_clear()
