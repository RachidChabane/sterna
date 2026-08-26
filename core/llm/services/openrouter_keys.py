"""
OpenRouter API Key Provisioning Service.

Manages per-user OpenRouter API keys via the OpenRouter Provisioning API.
Each user gets their own API key with configurable limits and usage tracking.

API Documentation: https://openrouter.ai/docs/guides/overview/auth/provisioning-api-keys
"""

import logging
from typing import Optional, Dict, TYPE_CHECKING
from dataclasses import dataclass
from decimal import Decimal

import httpx
from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)

# Configuration from settings
PROVISIONING_KEY = getattr(settings, 'OPENROUTER_PROVISIONING_KEY', '')
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"

# Default credit limit for new users (in USD)
DEFAULT_USER_CREDIT_LIMIT = getattr(settings, 'OPENROUTER_DEFAULT_USER_LIMIT', 10.0)
DEFAULT_LIMIT_RESET = getattr(settings, 'OPENROUTER_LIMIT_RESET', 'monthly')


@dataclass
class KeyUsageStats:
    """Usage statistics for an OpenRouter API key."""

    usage: Decimal
    remaining: Decimal
    limit: Decimal
    usage_daily: Decimal = Decimal(0)
    usage_weekly: Decimal = Decimal(0)
    usage_monthly: Decimal = Decimal(0)
    is_disabled: bool = False


class OpenRouterKeyError(Exception):
    """Exception for OpenRouter key provisioning errors."""

    pass


class OpenRouterKeyService:
    """
    Service for managing per-user OpenRouter API keys.

    Uses the OpenRouter Provisioning API to create, manage, and
    monitor API keys for individual users.

    Usage:
        service = get_key_service()
        service.provision_key_for_user(user)
        stats = service.get_key_usage(user)
    """

    def __init__(self):
        self.provisioning_key = PROVISIONING_KEY
        self.base_url = OPENROUTER_API_BASE

        if not self.provisioning_key:
            logger.warning(
                "OPENROUTER_PROVISIONING_KEY not set. "
                "Per-user API keys will not be provisioned."
            )

    @property
    def is_configured(self) -> bool:
        """Check if provisioning is properly configured."""
        return bool(self.provisioning_key)

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for provisioning API requests."""
        return {
            "Authorization": f"Bearer {self.provisioning_key}",
            "Content-Type": "application/json",
        }

    def provision_key_for_user(
        self,
        user: 'User',
        limit: Optional[float] = None,
        limit_reset: Optional[str] = None,
    ) -> bool:
        """
        Provision a new OpenRouter API key for a user.

        Args:
            user: User model instance
            limit: Credit limit in USD (default from settings)
            limit_reset: Reset frequency (daily, weekly, monthly, null)

        Returns:
            True if key was provisioned successfully

        Raises:
            OpenRouterKeyError: If provisioning fails
        """
        if not self.provisioning_key:
            raise OpenRouterKeyError("Provisioning key not configured")

        if user.openrouter_api_key:
            logger.info(f"User {user.id} already has an OpenRouter key")
            return True

        effective_limit = limit if limit is not None else DEFAULT_USER_CREDIT_LIMIT
        effective_reset = limit_reset or DEFAULT_LIMIT_RESET

        try:
            response = httpx.post(
                f"{self.base_url}/keys",
                headers=self._get_headers(),
                json={
                    "name": f"sterna-user-{user.id}",
                    "limit": effective_limit,
                    "limit_reset": effective_reset,
                },
                timeout=30.0,
            )
            response.raise_for_status()

            result = response.json()

            # Store the key (encrypted by EncryptedTextField) and hash
            # Response format: {"key": "sk-or-...", "data": {"hash": "...", ...}}
            user.openrouter_api_key = result["key"]
            user.openrouter_key_hash = result["data"]["hash"]
            user.openrouter_key_provisioned_at = timezone.now()
            user.save(update_fields=[
                'openrouter_api_key',
                'openrouter_key_hash',
                'openrouter_key_provisioned_at',
            ])

            logger.info(
                f"Provisioned OpenRouter key for user {user.id} "
                f"(limit=${effective_limit}, reset={effective_reset})"
            )
            return True

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else str(e)
            logger.error(f"Failed to provision key for user {user.id}: {error_detail}")
            raise OpenRouterKeyError(f"API error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Network error provisioning key for user {user.id}: {e}")
            raise OpenRouterKeyError(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Failed to provision key for user {user.id}: {e}")
            raise OpenRouterKeyError(str(e))

    def get_key_usage(self, user: 'User') -> Optional[KeyUsageStats]:
        """
        Get usage statistics for a user's API key from OpenRouter.

        Args:
            user: User model instance

        Returns:
            KeyUsageStats or None if key not found or error
        """
        if not user.openrouter_key_hash:
            return None

        if not self.provisioning_key:
            logger.warning("Cannot get key usage: provisioning key not configured")
            return None

        try:
            response = httpx.get(
                f"{self.base_url}/keys/{user.openrouter_key_hash}",
                headers=self._get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()

            response_data = response.json()
            # API wraps response in a "data" object
            data = response_data.get("data", response_data)
            return KeyUsageStats(
                usage=Decimal(str(data.get("usage", 0))),
                remaining=Decimal(str(data.get("limit_remaining", 0))),
                limit=Decimal(str(data.get("limit", 0))),
                usage_daily=Decimal(str(data.get("usage_daily", 0))),
                usage_weekly=Decimal(str(data.get("usage_weekly", 0))),
                usage_monthly=Decimal(str(data.get("usage_monthly", 0))),
                is_disabled=data.get("disabled", False),
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Key not found for user {user.id}")
            else:
                logger.error(f"Failed to get usage for user {user.id}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to get usage for user {user.id}: {e}")
            return None

    def disable_user_key(self, user: 'User') -> bool:
        """
        Disable a user's API key.

        Args:
            user: User model instance

        Returns:
            True if key was disabled successfully
        """
        if not user.openrouter_key_hash:
            return False

        if not self.provisioning_key:
            logger.warning("Cannot disable key: provisioning key not configured")
            return False

        try:
            response = httpx.patch(
                f"{self.base_url}/keys/{user.openrouter_key_hash}",
                headers=self._get_headers(),
                json={"disabled": True},
                timeout=30.0,
            )
            response.raise_for_status()
            logger.info(f"Disabled OpenRouter key for user {user.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to disable key for user {user.id}: {e}")
            return False

    def enable_user_key(self, user: 'User') -> bool:
        """
        Re-enable a user's API key.

        Args:
            user: User model instance

        Returns:
            True if key was enabled successfully
        """
        if not user.openrouter_key_hash:
            return False

        if not self.provisioning_key:
            logger.warning("Cannot enable key: provisioning key not configured")
            return False

        try:
            response = httpx.patch(
                f"{self.base_url}/keys/{user.openrouter_key_hash}",
                headers=self._get_headers(),
                json={"disabled": False},
                timeout=30.0,
            )
            response.raise_for_status()
            logger.info(f"Enabled OpenRouter key for user {user.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable key for user {user.id}: {e}")
            return False

    def update_user_limit(self, user: 'User', limit: float) -> bool:
        """
        Update the credit limit for a user's API key.

        Args:
            user: User model instance
            limit: New credit limit in USD

        Returns:
            True if limit was updated successfully
        """
        if not user.openrouter_key_hash:
            return False

        if not self.provisioning_key:
            logger.warning("Cannot update limit: provisioning key not configured")
            return False

        try:
            response = httpx.patch(
                f"{self.base_url}/keys/{user.openrouter_key_hash}",
                headers=self._get_headers(),
                json={"limit": limit},
                timeout=30.0,
            )
            response.raise_for_status()
            logger.info(f"Updated limit to ${limit} for user {user.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update limit for user {user.id}: {e}")
            return False

    def rotate_user_key(self, user: 'User') -> bool:
        """
        Rotate a user's API key (delete old, create new).

        This is useful for security key rotation or if a key is compromised.

        Args:
            user: User model instance

        Returns:
            True if rotation successful
        """
        if not self.provisioning_key:
            raise OpenRouterKeyError("Provisioning key not configured")

        # First, delete the old key if it exists
        if user.openrouter_key_hash:
            try:
                httpx.delete(
                    f"{self.base_url}/keys/{user.openrouter_key_hash}",
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                logger.info(f"Deleted old key for user {user.id}")
            except Exception as e:
                logger.warning(f"Failed to delete old key for user {user.id}: {e}")

        # Clear the old key from database
        user.openrouter_api_key = None
        user.openrouter_key_hash = None
        user.openrouter_key_provisioned_at = None
        user.save(update_fields=[
            'openrouter_api_key',
            'openrouter_key_hash',
            'openrouter_key_provisioned_at',
        ])

        # Provision new key
        return self.provision_key_for_user(user)

    def delete_user_key(self, user: 'User') -> bool:
        """
        Permanently delete a user's API key.

        Args:
            user: User model instance

        Returns:
            True if key was deleted successfully
        """
        if not user.openrouter_key_hash:
            return True  # No key to delete

        if not self.provisioning_key:
            logger.warning("Cannot delete key: provisioning key not configured")
            return False

        try:
            httpx.delete(
                f"{self.base_url}/keys/{user.openrouter_key_hash}",
                headers=self._get_headers(),
                timeout=30.0,
            )

            # Clear from database
            user.openrouter_api_key = None
            user.openrouter_key_hash = None
            user.openrouter_key_provisioned_at = None
            user.save(update_fields=[
                'openrouter_api_key',
                'openrouter_key_hash',
                'openrouter_key_provisioned_at',
            ])

            logger.info(f"Deleted OpenRouter key for user {user.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete key for user {user.id}: {e}")
            return False


# Singleton instance
_key_service: Optional[OpenRouterKeyService] = None


def get_key_service() -> OpenRouterKeyService:
    """Get the singleton OpenRouterKeyService instance."""
    global _key_service
    if _key_service is None:
        _key_service = OpenRouterKeyService()
    return _key_service
