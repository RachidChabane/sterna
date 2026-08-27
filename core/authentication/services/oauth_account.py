"""Pre-account-takeover-safe OAuth account resolution.

Task-29 C4: ``oauth_views.google_auth`` and ``github_auth`` used to do
``User.objects.get_or_create(email=email)``. That auto-merges an
attacker-controlled OAuth identity with any pre-existing
local-password account at the same email — the classic pre-account-
takeover pattern (OWASP).

This helper resolves an OAuth identity to a User using the safe
lookup chain:

1. ``SocialAccount`` lookup by ``(provider, provider_user_id)`` —
   this is the only "I have used this provider before" key.
2. If no SocialAccount row: look up User by email.
   - If a User exists AND ``has_usable_password()`` (a local-password
     account), REFUSE to auto-link. The user must sign in with their
     password and link the provider explicitly from settings.
   - If a User exists with NO usable password (OAuth-only account
     created by a different provider), it is safe to link this
     provider to it.
3. If no User exists at all: create a new one (only if the provider
   verified the email).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.utils import timezone

from authentication.models import SocialAccount, User


@dataclass(frozen=True)
class OAuthResolution:
    """Result of ``resolve_or_create_oauth_user``.

    Exactly one of ``user``/``conflict``/``unverified_block`` is set.
    """

    user: Optional[User] = None
    created: bool = False
    conflict: bool = False
    """True when an email-matching User exists with a usable password
    and no matching SocialAccount yet — auto-link refused."""
    unverified_block: bool = False
    """True when no User exists for this email AND the provider did
    not verify the email — refuse to mint a new account."""


def resolve_or_create_oauth_user(
    *,
    provider: str,
    provider_user_id: str,
    email: str,
    email_verified: bool,
    full_name: str = "",
    avatar_url: str = "",
) -> OAuthResolution:
    """Resolve an incoming OAuth identity to a User row.

    See module docstring for the lookup chain.
    """
    if not provider or not provider_user_id or not email:
        # Defensive — callers should have validated upstream. Treat as
        # a soft conflict so the view returns a 400-class response.
        return OAuthResolution(conflict=True)

    # 1. Provider lookup by stable provider_user_id.
    social = (
        SocialAccount.objects.filter(
            provider=provider, provider_user_id=provider_user_id
        )
        .select_related("user")
        .first()
    )
    if social is not None:
        return OAuthResolution(user=social.user, created=False)

    # 2. Email lookup — but ONLY safe to link if the existing user has
    #    no password set (i.e. they're already OAuth-only).
    existing = User.objects.filter(email__iexact=email).first()
    if existing is not None:
        if existing.has_usable_password():
            return OAuthResolution(conflict=True)
        return OAuthResolution(user=existing, created=False)

    # 3. First time. Only mint a new account if the provider verified
    #    the email.
    if not email_verified:
        return OAuthResolution(unverified_block=True)

    new_user = User.objects.create(
        email=email,
        full_name=full_name or "",
        is_verified=True,
        avatar_url=avatar_url or "",
        last_login=timezone.now(),
    )
    new_user.set_unusable_password()
    new_user.save()
    return OAuthResolution(user=new_user, created=True)
