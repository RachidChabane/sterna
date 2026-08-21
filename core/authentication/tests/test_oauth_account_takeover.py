"""Task-29 C4 regression: OAuth login MUST NOT auto-merge with a
pre-existing local-password account by email.

Before the fix:
    User.objects.get_or_create(email=email, defaults=...)
would auto-link an attacker who registers a Google/GitHub identity
verified at the victim's email to the victim's password account.

After the fix (``resolve_or_create_oauth_user``):

1. ``SocialAccount`` lookup by ``(provider, provider_user_id)`` first.
2. If no SocialAccount AND email-matching User has ``has_usable_password()``:
   refuse (409 + helpful message).
3. If no SocialAccount AND email-matching User has no password
   (OAuth-only): safe to link.
4. If no User exists AND email_verified: mint new.
5. If no User exists AND email NOT verified: 400.
"""
from __future__ import annotations

import pytest

from authentication.models import SocialAccount, User
from authentication.services.oauth_account import (
    resolve_or_create_oauth_user,
)


pytestmark = pytest.mark.django_db


def test_blocks_when_password_user_exists():
    """A local-password user at the same email must NOT be auto-linked."""
    User.objects.create_user(
        email="ada@example.com", password="x" * 12, is_verified=True
    )
    result = resolve_or_create_oauth_user(
        provider="google",
        provider_user_id="g-12345",
        email="ada@example.com",
        email_verified=True,
        full_name="Ada Lovelace",
        avatar_url="https://lh3.googleusercontent.com/a/x",
    )
    assert result.conflict is True
    assert result.user is None


def test_blocks_for_github_when_password_user_exists():
    """Symmetric to the Google case."""
    User.objects.create_user(
        email="ada@example.com", password="x" * 12, is_verified=True
    )
    result = resolve_or_create_oauth_user(
        provider="github",
        provider_user_id="42",
        email="ada@example.com",
        email_verified=True,
        full_name="Ada",
        avatar_url="https://avatars.githubusercontent.com/u/42",
    )
    assert result.conflict is True


def test_links_when_oauth_only_user_exists():
    """A user with no usable password (OAuth-only) safely accepts a
    second provider on the same email."""
    user = User.objects.create(
        email="ada@example.com", full_name="Ada", is_verified=True
    )
    user.set_unusable_password()
    user.save()
    # Pre-existing Google link.
    SocialAccount.objects.create(
        user=user, provider="google", provider_user_id="g-1", email=user.email
    )
    # Now GitHub OAuth tries with the same email.
    result = resolve_or_create_oauth_user(
        provider="github",
        provider_user_id="gh-2",
        email="ada@example.com",
        email_verified=True,
        full_name="Ada",
    )
    assert result.conflict is False
    assert result.user is not None
    assert result.user.pk == user.pk
    assert result.created is False


def test_creates_new_user_first_time():
    result = resolve_or_create_oauth_user(
        provider="google",
        provider_user_id="g-fresh",
        email="newuser@example.com",
        email_verified=True,
        full_name="New User",
        avatar_url="",
    )
    assert result.conflict is False
    assert result.user is not None
    assert result.created is True
    assert result.user.email == "newuser@example.com"
    assert not result.user.has_usable_password()


def test_finds_existing_social_account_directly():
    user = User.objects.create(
        email="ada@example.com", full_name="Ada", is_verified=True
    )
    user.set_unusable_password()
    user.save()
    SocialAccount.objects.create(
        user=user,
        provider="google",
        provider_user_id="g-stable-id",
        email="ada@example.com",
    )
    # Provider returns the SAME provider_user_id with a different email
    # (rare — user changed email at Google). The function must still
    # resolve via the stable provider_user_id, not the email.
    result = resolve_or_create_oauth_user(
        provider="google",
        provider_user_id="g-stable-id",
        email="ada-new@example.com",
        email_verified=True,
        full_name="Ada",
    )
    assert result.conflict is False
    assert result.user is not None
    assert result.user.pk == user.pk


def test_unverified_email_blocks_new_account():
    result = resolve_or_create_oauth_user(
        provider="github",
        provider_user_id="gh-99",
        email="unverified@example.com",
        email_verified=False,
        full_name="Unverified",
    )
    assert result.unverified_block is True
    assert result.user is None
    assert result.created is False
    assert not User.objects.filter(email="unverified@example.com").exists()


def test_unverified_email_allowed_for_existing_oauth_user():
    """If the user already exists as OAuth-only (via the same
    provider_user_id), the email_verified flag is irrelevant for THIS
    login — we already trust them."""
    user = User.objects.create(
        email="ada@example.com", full_name="Ada", is_verified=True
    )
    user.set_unusable_password()
    user.save()
    SocialAccount.objects.create(
        user=user, provider="google", provider_user_id="g-1", email=user.email
    )
    result = resolve_or_create_oauth_user(
        provider="google",
        provider_user_id="g-1",
        email="ada@example.com",
        email_verified=False,
        full_name="Ada",
    )
    assert result.conflict is False
    assert result.user is not None
    assert result.user.pk == user.pk
