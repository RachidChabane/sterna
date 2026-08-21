"""Task-29 C2 regression: PATCH /api/auth/profile/ MUST NOT allow
mass-assignment of sensitive fields.

Previously, ``UserProfileView.patch`` used the generic ``UserSerializer``
with ``email``, ``avatar_url``, and ``is_active`` writable. An
authenticated user could:

- change their own email (no re-verification → recovery email gets
  hijacked at password-reset time)
- self-deactivate (low impact)
- inject an arbitrary ``avatar_url`` (chains into C3's open redirect)

The fix marks those three fields ``read_only`` on the serializer.
PATCH requests with those keys silently ignore them (DRF's
default behavior for read-only fields).
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from authentication.jwt_utils import JWTManager
from authentication.models import User


class ProfilePatchSecurityTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="ada@example.com",
            password="x" * 12,
            full_name="Ada Lovelace",
        )
        token = JWTManager.create_access_token(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.url = reverse("authentication:profile")

    def test_patch_cannot_change_email(self):
        response = self.client.patch(
            self.url, {"email": "attacker@evil.example"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        self.user.refresh_from_db()
        assert self.user.email == "ada@example.com"

    def test_patch_cannot_change_is_active(self):
        response = self.client.patch(
            self.url, {"is_active": False}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        self.user.refresh_from_db()
        assert self.user.is_active is True

    def test_patch_cannot_change_avatar_url_directly(self):
        original = self.user.avatar_url
        response = self.client.patch(
            self.url,
            {"avatar_url": "https://evil.example/phish.png"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.user.refresh_from_db()
        assert self.user.avatar_url == original

    def test_patch_cannot_change_is_verified(self):
        # Regression guard for the pre-existing read-only field.
        response = self.client.patch(
            self.url, {"is_verified": True}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        self.user.refresh_from_db()
        assert self.user.is_verified is False

    def test_patch_can_still_change_name_fields(self):
        response = self.client.patch(
            self.url,
            {"full_name": "Ada Augusta King-Noel"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.user.refresh_from_db()
        assert self.user.full_name == "Ada Augusta King-Noel"

    def test_patch_combined_payload_only_safe_fields_apply(self):
        response = self.client.patch(
            self.url,
            {
                "full_name": "New Name",
                "email": "attacker@evil.example",
                "is_active": False,
                "avatar_url": "https://evil.example/x.png",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.user.refresh_from_db()
        assert self.user.full_name == "New Name"
        assert self.user.email == "ada@example.com"
        assert self.user.is_active is True
