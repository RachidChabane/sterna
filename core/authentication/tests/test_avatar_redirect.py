"""Task-29 C3 regression: ``serve_user_avatar`` MUST validate the
redirect target's host against ``AVATAR_REDIRECT_ALLOWLIST``.

Without the fix, a user whose ``avatar_url`` is non-r2:// gets an
unconditional ``HttpResponseRedirect(avatar_url)`` — open redirect
via OAuth-provider URL injection.

Tests cover the four observable shapes:

- legitimate provider host → 302
- non-allowlisted host → 404 + log line
- ``r2://`` URL → existing proxy path (200 or 503 depending on R2
  availability — we only test the routing decision, not the bytes)
- empty ``avatar_url`` → 404
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from authentication.models import User


class AvatarRedirectAllowlistTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="ada@example.com", password="x" * 12
        )

    def _avatar_url(self):
        return reverse("authentication:serve-avatar", args=[str(self.user.id)])

    @override_settings(
        AVATAR_REDIRECT_ALLOWLIST=[
            "googleusercontent.com",
            "avatars.githubusercontent.com",
        ]
    )
    def test_allowed_googleusercontent_redirects(self):
        self.user.avatar_url = (
            "https://lh3.googleusercontent.com/a/AAcHTtfake-photo"
        )
        self.user.save(update_fields=["avatar_url"])
        response = self.client.get(self._avatar_url())
        assert response.status_code == 302
        assert response["Location"] == self.user.avatar_url

    @override_settings(
        AVATAR_REDIRECT_ALLOWLIST=[
            "googleusercontent.com",
            "avatars.githubusercontent.com",
        ]
    )
    def test_allowed_github_avatar_redirects(self):
        self.user.avatar_url = (
            "https://avatars.githubusercontent.com/u/123456"
        )
        self.user.save(update_fields=["avatar_url"])
        response = self.client.get(self._avatar_url())
        assert response.status_code == 302

    @override_settings(
        AVATAR_REDIRECT_ALLOWLIST=[
            "googleusercontent.com",
            "avatars.githubusercontent.com",
        ]
    )
    def test_blocked_host_returns_404(self):
        self.user.avatar_url = "https://evil.example/phish.png"
        self.user.save(update_fields=["avatar_url"])
        response = self.client.get(self._avatar_url())
        assert response.status_code == 404

    @override_settings(
        AVATAR_REDIRECT_ALLOWLIST=[
            "googleusercontent.com",
            "avatars.githubusercontent.com",
        ]
    )
    def test_subdomain_attack_blocked(self):
        # `googleusercontent.com.attacker.example` must NOT match the
        # `.googleusercontent.com` suffix because the host is
        # `attacker.example` after the (`.`)-anchored suffix check.
        self.user.avatar_url = (
            "https://googleusercontent.com.attacker.example/x.png"
        )
        self.user.save(update_fields=["avatar_url"])
        response = self.client.get(self._avatar_url())
        assert response.status_code == 404

    @override_settings(
        AVATAR_REDIRECT_ALLOWLIST=[
            "googleusercontent.com",
            "avatars.githubusercontent.com",
        ]
    )
    def test_malformed_url_returns_404(self):
        # Invalid URL — urlparse may not raise, so hostname will be
        # empty/None, and the allowlist check will reject. We just
        # need to confirm we don't crash and don't redirect.
        self.user.avatar_url = "not-a-url-at-all"
        self.user.save(update_fields=["avatar_url"])
        response = self.client.get(self._avatar_url())
        assert response.status_code == 404

    def test_no_avatar_returns_404(self):
        self.user.avatar_url = ""
        self.user.save(update_fields=["avatar_url"])
        response = self.client.get(self._avatar_url())
        assert response.status_code == 404

    def test_r2_avatar_takes_proxy_path(self):
        """r2:// URLs go down the proxy path, not the redirect path."""
        self.user.avatar_url = "r2://test-bucket/avatars/ada.png"
        self.user.save(update_fields=["avatar_url"])

        # Mock the storage layer so the test doesn't need real R2.
        with patch(
            "workspaces.services.workspace_storage.get_storage_service"
        ) as mock_storage:
            mock_storage.return_value._get_r2_client.return_value = None
            response = self.client.get(self._avatar_url())
        # 503 means the proxy path WAS reached (client unavailable).
        # 200 with content would also be acceptable.
        assert response.status_code in (200, 503)
        # Must NOT be a redirect.
        assert response.status_code != 302
