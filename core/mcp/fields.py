"""Encrypted model fields for storing sensitive data."""

import json
from typing import Any, Optional

from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


def get_encryption_key() -> bytes:
    """Get the encryption key from settings.

    Returns:
        Encryption key as bytes

    Raises:
        ImproperlyConfigured: If FIELD_ENCRYPTION_KEY is not set
    """
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY must be set in settings for encrypted fields. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    if isinstance(key, str):
        key = key.encode()
    return key


def _build_cipher() -> MultiFernet:
    """Build a MultiFernet cipher with primary + legacy keys.

    Primary key: settings.BYOK_ENCRYPTION_KEY, falling back to
    FIELD_ENCRYPTION_KEY (the default behavior wired in base.py).

    Legacy keys: settings.BYOK_ENCRYPTION_KEY_LEGACY (list[str]).
    MultiFernet tries each key in order on decrypt; encrypt always
    uses the primary. Rotation procedure: docs/operations/byok-key-rotation.md
    """
    primary = (
        getattr(settings, 'BYOK_ENCRYPTION_KEY', None)
        or getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    )
    if not primary:
        raise ImproperlyConfigured(
            "BYOK_ENCRYPTION_KEY (or FIELD_ENCRYPTION_KEY fallback) must "
            "be set for encrypted fields. Generate one with: "
            "python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'"
        )

    if isinstance(primary, str):
        primary = primary.encode()
    keys = [Fernet(primary)]

    legacy = getattr(settings, 'BYOK_ENCRYPTION_KEY_LEGACY', []) or []
    for legacy_key in legacy:
        if isinstance(legacy_key, str):
            legacy_key = legacy_key.strip().encode()
        if legacy_key:
            keys.append(Fernet(legacy_key))

    return MultiFernet(keys)


class EncryptedTextField(models.TextField):
    """A TextField that encrypts data at rest using Fernet (AES 128-bit).

    Data is encrypted before saving to database and decrypted when reading.
    Uses Django's SECRET_KEY-derived encryption key for security.

    Example:
        class MyModel(models.Model):
            secret_data = EncryptedTextField()
    """

    description = "Encrypted text field using Fernet encryption"

    def __init__(self, *args, **kwargs):
        """Initialize the encrypted text field."""
        super().__init__(*args, **kwargs)
        # Test-only hook: cleared by tests when rotating settings keys to
        # invalidate the per-instance cipher cache. Production never mutates
        # settings at runtime so the cache is fine.
        self._fernet = None

    @property
    def fernet(self) -> MultiFernet:
        """Get or create MultiFernet cipher instance."""
        if self._fernet is None:
            self._fernet = _build_cipher()
        return self._fernet

    def get_prep_value(self, value: Any) -> str:
        """Encrypt value before saving to database.

        Args:
            value: Plain text value to encrypt

        Returns:
            Encrypted value as string
        """
        if value is None or value == '':
            return value

        # Convert to string if not already
        if not isinstance(value, str):
            value = str(value)

        # Encrypt the value
        encrypted = self.fernet.encrypt(value.encode())
        return encrypted.decode()

    def from_db_value(self, value: Any, expression, connection) -> str:
        """Decrypt value when reading from database.

        Args:
            value: Encrypted value from database
            expression: SQL expression
            connection: Database connection

        Returns:
            Decrypted plain text value
        """
        if value is None or value == '':
            return value

        try:
            # Decrypt the value
            decrypted = self.fernet.decrypt(value.encode())
            return decrypted.decode()
        except InvalidToken:
            # If decryption fails, it might be unencrypted legacy data
            # Log a warning and return as-is
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to decrypt field value - may be legacy unencrypted data")
            return value

    def to_python(self, value: Any) -> Optional[str]:
        """Convert value to Python string.

        Args:
            value: Value to convert

        Returns:
            Python string value
        """
        if isinstance(value, str) or value is None:
            return value
        return str(value)


class EncryptedJSONField(models.JSONField):
    """A JSONField that encrypts data at rest using Fernet (AES 128-bit).

    JSON data is encrypted before saving to database and decrypted when reading.
    Uses Django's SECRET_KEY-derived encryption key for security.

    Note: Stored as TEXT in database (not JSONB) to hold encrypted string.

    Example:
        class MyModel(models.Model):
            secret_config = EncryptedJSONField(default=dict)
    """

    description = "Encrypted JSON field using Fernet encryption"

    def __init__(self, *args, **kwargs):
        """Initialize the encrypted JSON field."""
        super().__init__(*args, **kwargs)
        # Test-only hook: cleared by tests when rotating settings keys to
        # invalidate the per-instance cipher cache. Production never mutates
        # settings at runtime so the cache is fine.
        self._fernet = None

    def db_type(self, connection):
        """Return TEXT as database type instead of JSONB.

        We store encrypted data as text, not JSON.
        """
        return 'text'

    @property
    def fernet(self) -> MultiFernet:
        """Get or create MultiFernet cipher instance."""
        if self._fernet is None:
            self._fernet = _build_cipher()
        return self._fernet

    def get_prep_value(self, value: Any) -> Optional[str]:
        """Encrypt JSON value before saving to database.

        Args:
            value: Dictionary/JSON value to encrypt

        Returns:
            Encrypted JSON as string
        """
        if value is None:
            return value

        # Convert to JSON string
        json_str = json.dumps(value, ensure_ascii=False)

        # Encrypt the JSON string
        encrypted = self.fernet.encrypt(json_str.encode())
        return encrypted.decode()

    def from_db_value(self, value: Any, expression, connection) -> Optional[dict[Any, Any]]:
        """Decrypt JSON value when reading from database.

        Args:
            value: Encrypted JSON from database
            expression: SQL expression
            connection: Database connection

        Returns:
            Decrypted dictionary/JSON value
        """
        if value is None:
            return value

        try:
            # Decrypt the value
            decrypted = self.fernet.decrypt(value.encode())
            json_str = decrypted.decode()

            # Parse JSON
            return json.loads(json_str)
        except (InvalidToken, json.JSONDecodeError) as e:
            # If decryption fails, it might be unencrypted legacy data
            # Try to parse as plain JSON
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to decrypt JSON field - attempting legacy parse: {e}")

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # If that also fails, return empty dict
                logger.error("Failed to parse JSON field value")
                return {}

    def to_python(self, value: Any) -> Optional[dict[Any, Any]]:
        """Convert value to Python dict.

        Args:
            value: Value to convert

        Returns:
            Python dict value
        """
        if isinstance(value, dict) or value is None:
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value
