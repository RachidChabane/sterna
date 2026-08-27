"""
Centralized API Key Resolution.

Provides a single point for resolving which OpenRouter API key to use
for any request, with proper fallback handling and usage logging.

This module ensures consistent API key resolution across the entire codebase,
making it easy to track and monitor usage.
"""

import logging
import os
from typing import Literal, Optional, Tuple, TYPE_CHECKING, cast

from django.conf import settings

from usage_quota.constants import (
    BILLING_ORIGIN_BYOK,
    BILLING_ORIGIN_PLATFORM,
)
from llm.provider_registry import (
    BYOK_PROVIDERS,
    OPENROUTER_BASE_URL,
    provider_for_model,
)

if TYPE_CHECKING:
    from django.http import HttpRequest
    from authentication.models import User

logger = logging.getLogger(__name__)

BillingOrigin = Literal['byok', 'platform']

# usage_quota.constants types these as plain `str` (its own BillingOrigin
# alias is intentionally loose); this module narrows to the two known
# values, so re-assert that narrowing once here rather than at every
# return site below.
_ORIGIN_BYOK: BillingOrigin = cast(BillingOrigin, BILLING_ORIGIN_BYOK)
_ORIGIN_PLATFORM: BillingOrigin = cast(BillingOrigin, BILLING_ORIGIN_PLATFORM)


class NoAPIKeyError(ValueError):
    """No API key is available for the request.

    Subclasses ValueError so existing ``except ValueError`` handlers keep
    working; error_messages.get_error_code maps it to the machine code
    ``no_api_key`` so the frontend can offer a direct fix (open the
    API-key settings) instead of a generic failure message.
    """


class APIKeyResolver:
    """
    Resolves the appropriate OpenRouter API key for a request.

    Priority order:
    1. User's personal key (if authenticated and has key provisioned)
    2. Fallback to environment variable (for system operations or anonymous)

    Usage:
        resolver = get_resolver()
        api_key = resolver.get_api_key(request)
        # or
        api_key = resolver.get_api_key_for_user(user)
    """

    def __init__(self):
        # Get fallback key from settings or environment
        self._fallback_key = (
            getattr(settings, 'OPENROUTER_API_KEY', '') or
            os.getenv('OPENROUTER_API_KEY', '')
        )

    @property
    def fallback_key(self) -> str:
        """Get the system-level fallback API key."""
        return self._fallback_key

    @property
    def has_fallback_key(self) -> bool:
        """Check if a fallback key is available."""
        return bool(self._fallback_key)

    def get_api_key(self, request: Optional['HttpRequest'] = None) -> str:
        """
        Get the appropriate API key for a request.

        Args:
            request: Django HttpRequest (optional)

        Returns:
            API key string

        Raises:
            ValueError: If no API key is available
        """
        # Try to get user's key first
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            user_key = self.get_api_key_for_user(cast('User', request.user))
            if user_key:
                return user_key

        # Fall back to system key
        if self._fallback_key:
            return self._fallback_key

        raise NoAPIKeyError(
            "No OpenRouter API key available. "
            "Either authenticate with a user that has a key, "
            "or set OPENROUTER_API_KEY environment variable."
        )

    def get_api_key_for_user(self, user: 'User') -> Optional[str]:
        """
        Get the API key for a specific user.

        Args:
            user: User model instance

        Returns:
            API key string or None if user has no key
        """
        if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
            return None

        # Check if user has a personal key
        api_key = getattr(user, 'openrouter_api_key', None)
        if api_key:
            return api_key

        return None

    def get_user_from_request(self, request: Optional['HttpRequest']) -> Optional['User']:
        """Extract authenticated user from request."""
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return cast('User', request.user)
        return None

    def get_api_key_with_fallback(
        self,
        user: Optional['User'] = None,
        request: Optional['HttpRequest'] = None,
    ) -> str:
        """
        Get API key with automatic fallback.

        Tries user key first, then falls back to system key.

        Args:
            user: User to get key for
            request: Request to extract user from

        Returns:
            API key string

        Raises:
            ValueError: If no API key is available
        """
        # Try user from parameter
        if user:
            user_key = self.get_api_key_for_user(user)
            if user_key:
                return user_key

        # Try user from request
        if request:
            return self.get_api_key(request)

        # Fall back to system key
        if self._fallback_key:
            return self._fallback_key

        raise NoAPIKeyError("No OpenRouter API key available")

    def resolve_with_origin(
        self,
        user: Optional['User'] = None,
        request: Optional['HttpRequest'] = None,
        model_id: Optional[str] = None,
    ) -> Tuple[str, BillingOrigin]:
        """Return ``(api_key, billing_origin)`` for the request.

        ``billing_origin`` is ``'byok'`` iff the user has uploaded their own
        OpenRouter key (``openrouter_api_key`` is set AND
        ``openrouter_key_provisioned_at`` is NULL). Auto-provisioned keys —
        created by ``OpenRouterKeyService`` — and the system fallback both
        return ``'platform'`` because the Sterna OpenRouter account pays.

        When ``model_id`` is given, provider-scoped BYOK keys take
        precedence: if the model maps to a first-party provider the user
        has a key for, that key is returned with origin ``'byok'``
        (matching :meth:`resolve_endpoint`).

        Raises:
            ValueError: if no API key is available.
        """
        if model_id is not None:
            api_key, _base_url, endpoint_origin, _slug = self.resolve_endpoint(
                user=user, request=request, model_id=model_id,
            )
            return api_key, endpoint_origin

        if user is None and request is not None:
            user = self.get_user_from_request(request)

        if user is not None and getattr(user, 'is_authenticated', False):
            user_key = getattr(user, 'openrouter_api_key', None)
            if user_key:
                provisioned_at = getattr(user, 'openrouter_key_provisioned_at', None)
                origin = _ORIGIN_PLATFORM if provisioned_at is not None else _ORIGIN_BYOK
                return user_key, origin

        if self._fallback_key:
            return self._fallback_key, _ORIGIN_PLATFORM

        raise NoAPIKeyError(
            "No OpenRouter API key available. "
            "Either authenticate with a user that has a key, "
            "or set OPENROUTER_API_KEY environment variable."
        )

    def resolve_endpoint(
        self,
        user: Optional['User'] = None,
        request: Optional['HttpRequest'] = None,
        model_id: Optional[str] = None,
    ) -> Tuple[str, str, BillingOrigin, Optional[str]]:
        """Resolve ``(api_key, base_url, billing_origin, provider_slug)``.

        Priority order:

        a. ``model_id`` maps to a first-party BYOK provider AND the user
           has a key for that provider -> route DIRECTLY to the provider:
           ``(provider_key, provider_base_url, 'byok', provider_slug)``.
        b. User has an OpenRouter key. BYOK iff it was user-uploaded
           (``openrouter_key_provisioned_at IS NULL``); auto-provisioned
           keys stay ``'platform'``:
           ``(user_key, OPENROUTER_BASE_URL, origin, None)``.
        c. Platform fallback:
           ``(fallback_key, OPENROUTER_BASE_URL, 'platform', None)``.

        Models whose prefix is not a first-party provider (meta-llama/,
        qwen/, ...) never match (a) — they resolve as before.

        Raises:
            ValueError: if no API key is available.
        """
        if user is None and request is not None:
            user = self.get_user_from_request(request)

        is_authenticated = user is not None and getattr(user, 'is_authenticated', False)

        if is_authenticated and model_id and user is not None:
            provider_slug = provider_for_model(model_id)
            if provider_slug and hasattr(user, 'get_provider_key'):
                provider_key = user.get_provider_key(provider_slug)
                if provider_key:
                    return (
                        provider_key,
                        BYOK_PROVIDERS[provider_slug]['base_url'],
                        _ORIGIN_BYOK,
                        provider_slug,
                    )

        if is_authenticated:
            user_key = getattr(user, 'openrouter_api_key', None)
            if user_key:
                provisioned_at = getattr(user, 'openrouter_key_provisioned_at', None)
                origin = _ORIGIN_PLATFORM if provisioned_at is not None else _ORIGIN_BYOK
                return user_key, OPENROUTER_BASE_URL, origin, None

        if self._fallback_key:
            return (
                self._fallback_key,
                OPENROUTER_BASE_URL,
                _ORIGIN_PLATFORM,
                None,
            )

        raise NoAPIKeyError(
            "No API key available. "
            "Either authenticate with a user that has a key, "
            "or set OPENROUTER_API_KEY environment variable."
        )


# Singleton instance
_resolver: Optional[APIKeyResolver] = None


def get_resolver() -> APIKeyResolver:
    """Get the singleton APIKeyResolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = APIKeyResolver()
    return _resolver


def get_api_key(request: Optional['HttpRequest'] = None) -> str:
    """
    Convenience function to get API key for a request.

    Args:
        request: Django HttpRequest (optional)

    Returns:
        API key string
    """
    return get_resolver().get_api_key(request)


def get_api_key_for_user(user: 'User') -> Optional[str]:
    """
    Convenience function to get API key for a user.

    Args:
        user: User model instance

    Returns:
        API key string or None
    """
    return get_resolver().get_api_key_for_user(user)


def get_api_key_with_fallback(
    user: Optional['User'] = None,
    request: Optional['HttpRequest'] = None,
) -> str:
    """
    Convenience function to get API key with fallback.

    Args:
        user: User to get key for
        request: Request to extract user from

    Returns:
        API key string
    """
    return get_resolver().get_api_key_with_fallback(user=user, request=request)


def resolve_with_origin(
    user: Optional['User'] = None,
    request: Optional['HttpRequest'] = None,
    model_id: Optional[str] = None,
) -> Tuple[str, BillingOrigin]:
    """Convenience: ``(api_key, billing_origin)`` for the request.

    See :meth:`APIKeyResolver.resolve_with_origin`.
    """
    return get_resolver().resolve_with_origin(
        user=user, request=request, model_id=model_id,
    )


def resolve_endpoint(
    user: Optional['User'] = None,
    request: Optional['HttpRequest'] = None,
    model_id: Optional[str] = None,
) -> Tuple[str, str, BillingOrigin, Optional[str]]:
    """Convenience: ``(api_key, base_url, billing_origin, provider_slug)``.

    See :meth:`APIKeyResolver.resolve_endpoint`.
    """
    return get_resolver().resolve_endpoint(
        user=user, request=request, model_id=model_id,
    )
