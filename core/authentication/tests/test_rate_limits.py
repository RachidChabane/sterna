"""Rate-limit tests for auth views + OAuth callbacks (task 18).

Verifies the ``apply_ratelimit`` wiring shipped in commit dd40d73:

    RegisterView            ip 5/h      email 10/h
    LoginView               ip 10/m     email 20/m
    ResendVerificationView  user_or_ip 5/d
    PasswordResetRequestView ip 5/h     email 3/h
    OAuthStateView          ip 30/m
    google_auth/google_one_tap_auth/github_auth
                            ip 30/m (shared "oauth-callback" group)

Blocked requests raise ``django_ratelimit.exceptions.Ratelimited``
(a ``PermissionDenied`` subclass) which DRF renders as 403.

Determinism: ``django_ratelimit`` buckets counters into wall-clock
windows; a burst near a minute boundary would split across windows and
flake. ``_get_window`` is pinned per-test so every request lands in one
window. The cache is cleared per-test (LocMemCache is process-shared).

Historical production gaps pinned here (both fixed):
- The email buckets used ``post:email`` keys reading ``request.POST``,
  which is EMPTY for the JSON bodies the frontend sends — all JSON
  traffic shared one global bucket per group (password-reset collapsed
  to 3/h site-wide). Now keyed via ``exceptions.json_body_field_key``,
  which parses the JSON body and falls back to form POST, then IP.
- ``google_one_tap_auth`` had no ``apply_ratelimit`` decorator at all;
  it now shares the ``oauth-callback`` bucket with the other two.
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse

pytestmark = pytest.mark.django_db

LOGIN_URL = reverse("authentication:login")
REGISTER_URL = reverse("authentication:register")
RESEND_URL = reverse("authentication:resend-verification")
RESET_URL = reverse("authentication:password-reset")
OAUTH_STATE_URL = reverse("authentication:oauth-state")
GOOGLE_URL = reverse("authentication:google-auth")
GOOGLE_ONE_TAP_URL = reverse("authentication:google-one-tap")
GITHUB_URL = reverse("authentication:github-auth")

RATELIMITED_STATUS = 403


@pytest.fixture(autouse=True)
def _deterministic_ratelimit_window():
    """Pin the ratelimit window + start from a clean cache."""
    cache.clear()
    with patch("django_ratelimit.core._get_window", return_value=1_999_999_999):
        yield
    cache.clear()


def _is_ratelimited(response):
    """A ratelimit block is DRF's PermissionDenied rendering."""
    return (
        response.status_code == RATELIMITED_STATUS
        and "detail" in getattr(response, "data", {})
    )


class TestLoginRateLimits:
    def test_login_ip_limit_blocks_11th_attempt(self, api_client):
        for i in range(10):
            response = api_client.post(
                LOGIN_URL,
                {"email": f"nobody{i}@example.com", "password": "wrong-pass"},
                format="json",
                REMOTE_ADDR="10.9.9.9",
            )
            assert response.status_code == 400, f"attempt {i} unexpectedly blocked"
        blocked = api_client.post(
            LOGIN_URL,
            {"email": "nobody@example.com", "password": "wrong-pass"},
            format="json",
            REMOTE_ADDR="10.9.9.9",
        )
        assert _is_ratelimited(blocked)

    def test_login_ip_limit_is_per_ip(self, api_client):
        for i in range(10):
            api_client.post(
                LOGIN_URL,
                {"email": "nobody@example.com", "password": "wrong-pass"},
                format="json",
                REMOTE_ADDR="10.9.9.9",
            )
        # Different IP still gets through (bad creds -> 400, not 403).
        response = api_client.post(
            LOGIN_URL,
            {"email": "nobody@example.com", "password": "wrong-pass"},
            format="json",
            REMOTE_ADDR="10.9.9.10",
        )
        assert response.status_code == 400

    def test_login_email_limit_blocks_21st_attempt(self, api_client):
        # Form-encoded to exercise the email key's form fallback.
        # Distinct IPs keep the 10/m ip bucket out of the way.
        for i in range(20):
            response = api_client.post(
                LOGIN_URL,
                {"email": "victim@example.com", "password": "wrong-pass"},
                REMOTE_ADDR=f"10.1.{i // 250}.{i % 250 + 1}",
            )
            assert response.status_code == 400, f"attempt {i} unexpectedly blocked"
        blocked = api_client.post(
            LOGIN_URL,
            {"email": "victim@example.com", "password": "wrong-pass"},
            REMOTE_ADDR="10.1.200.200",
        )
        assert _is_ratelimited(blocked)


class TestRegisterRateLimits:
    def test_register_ip_limit_blocks_6th_attempt(self, api_client):
        for i in range(5):
            response = api_client.post(
                REGISTER_URL, {}, format="json", REMOTE_ADDR="10.2.2.2"
            )
            assert response.status_code != RATELIMITED_STATUS
        blocked = api_client.post(
            REGISTER_URL, {}, format="json", REMOTE_ADDR="10.2.2.2"
        )
        assert _is_ratelimited(blocked)

    def test_register_email_limit_blocks_11th_attempt(self, api_client):
        for i in range(10):
            response = api_client.post(
                REGISTER_URL,
                {"email": "dupe@example.com"},
                REMOTE_ADDR=f"10.3.{i}.1",
            )
            assert response.status_code != RATELIMITED_STATUS
        blocked = api_client.post(
            REGISTER_URL,
            {"email": "dupe@example.com"},
            REMOTE_ADDR="10.3.99.1",
        )
        assert _is_ratelimited(blocked)


class TestResendVerificationRateLimit:
    def test_anonymous_ip_blocks_6th_attempt(self, api_client):
        for i in range(5):
            response = api_client.post(
                RESEND_URL,
                {"email": "ghost@example.com"},
                format="json",
                REMOTE_ADDR="10.4.4.4",
            )
            assert response.status_code != RATELIMITED_STATUS
        blocked = api_client.post(
            RESEND_URL,
            {"email": "ghost@example.com"},
            format="json",
            REMOTE_ADDR="10.4.4.4",
        )
        assert _is_ratelimited(blocked)


class TestPasswordResetRateLimits:
    def test_reset_email_limit_blocks_4th_attempt(self, api_client):
        for i in range(3):
            response = api_client.post(
                RESET_URL,
                {"email": "target@example.com"},
                REMOTE_ADDR="10.5.5.5",
            )
            assert response.status_code != RATELIMITED_STATUS
        blocked = api_client.post(
            RESET_URL,
            {"email": "target@example.com"},
            REMOTE_ADDR="10.5.5.5",
        )
        assert _is_ratelimited(blocked)

    def test_reset_ip_limit_blocks_6th_attempt(self, api_client):
        for i in range(5):
            response = api_client.post(
                RESET_URL,
                {"email": f"distinct{i}@example.com"},
                REMOTE_ADDR="10.6.6.6",
            )
            assert response.status_code != RATELIMITED_STATUS
        blocked = api_client.post(
            RESET_URL,
            {"email": "distinct-final@example.com"},
            REMOTE_ADDR="10.6.6.6",
        )
        assert _is_ratelimited(blocked)

    def test_json_reset_for_new_email_not_blocked_by_others(self, api_client):
        for i in range(3):
            api_client.post(
                RESET_URL,
                {"email": f"attacker{i}@example.com"},
                format="json",
                REMOTE_ADDR=f"10.7.{i}.1",
            )
        # A fresh email from a fresh IP should not be rate-limited.
        response = api_client.post(
            RESET_URL,
            {"email": "innocent@example.com"},
            format="json",
            REMOTE_ADDR="10.7.99.1",
        )
        assert not _is_ratelimited(response)


class TestOAuthRateLimits:
    def test_oauth_state_limit_blocks_31st_attempt(self, api_client):
        for i in range(30):
            response = api_client.post(
                OAUTH_STATE_URL, {}, format="json", REMOTE_ADDR="10.8.8.8"
            )
            assert response.status_code == 200
        blocked = api_client.post(
            OAUTH_STATE_URL, {}, format="json", REMOTE_ADDR="10.8.8.8"
        )
        assert _is_ratelimited(blocked)

    def test_google_callback_limit_blocks_31st_attempt(self, api_client):
        for i in range(30):
            response = api_client.post(
                GOOGLE_URL, {}, format="json", REMOTE_ADDR="10.10.1.1"
            )
            # Missing credential -> 400; never a network call.
            assert response.status_code == 400
        blocked = api_client.post(
            GOOGLE_URL, {}, format="json", REMOTE_ADDR="10.10.1.1"
        )
        assert _is_ratelimited(blocked)

    def test_callback_bucket_is_shared_google_github(self, api_client):
        # 30 hits on google exhaust the shared "oauth-callback" group;
        # the first github hit from the same IP is already blocked.
        for i in range(30):
            api_client.post(
                GOOGLE_URL, {}, format="json", REMOTE_ADDR="10.11.1.1"
            )
        blocked = api_client.post(
            GITHUB_URL, {}, format="json", REMOTE_ADDR="10.11.1.1"
        )
        assert _is_ratelimited(blocked)

    def test_callback_limit_is_per_ip(self, api_client):
        for i in range(30):
            api_client.post(
                GOOGLE_URL, {}, format="json", REMOTE_ADDR="10.12.1.1"
            )
        response = api_client.post(
            GOOGLE_URL, {}, format="json", REMOTE_ADDR="10.12.1.2"
        )
        assert response.status_code == 400

    def test_google_one_tap_is_rate_limited(self, api_client):
        last = None
        for i in range(31):
            last = api_client.post(
                GOOGLE_ONE_TAP_URL, {}, format="json", REMOTE_ADDR="10.13.1.1"
            )
        assert _is_ratelimited(last)
