"""Shared pytest fixtures for authentication test modules.

Mirrors the ``auth_as`` pattern from ``usage_quota/tests/conftest.py``:
the project uses a custom ``JWTManager`` whose payload carries
``type: access`` — ``rest_framework_simplejwt`` tokens would be
rejected by ``authentication.authentication.JWTAuthentication``.

These fixtures are additive only: the pre-existing unittest-style
modules in this package do not consume pytest fixtures, and nothing
here is autouse, so they are unaffected.
"""

import pytest
from rest_framework.test import APIClient

from authentication.jwt_utils import JWTManager
from authentication.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_as():
    """Factory: attach a JWT for ``user`` to ``client``."""

    def _auth(client, user):
        access_token = JWTManager.create_access_token(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return client

    return _auth


@pytest.fixture
def verified_user(db):
    return User.objects.create_user(
        email="gdpr-user@example.com",
        password="Sup3r-secret!",
        is_verified=True,
    )


@pytest.fixture
def other_verified_user(db):
    return User.objects.create_user(
        email="gdpr-other@example.com",
        password="0ther-secret!",
        is_verified=True,
    )
