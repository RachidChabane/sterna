"""Tests for the gateway's fail-closed startup guards.

These cover gateway/config.py's two `model_validator` checks: the JWT
secret must be real (or the dev bypass explicitly opted into), and
credentialed CORS must never fall back to a wildcard origin.
"""

import pytest
from pydantic import ValidationError

from gateway.config import Settings


def _settings(**overrides):
    """Build Settings with safe defaults, overridden per test."""
    kwargs = {
        "jwt_secret_key": "a-real-generated-secret-1234567890",
        "cors_origins": ["http://localhost:5173"],
        "environment": "development",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


class TestJWTSecretGuard:
    """Fail-closed startup check for GATEWAY_JWT_SECRET_KEY."""

    def test_default_placeholder_secret_refuses_to_boot(self):
        with pytest.raises(ValidationError, match="known-insecure"):
            _settings(jwt_secret_key="change-me-in-production")

    def test_empty_secret_refuses_to_boot(self):
        with pytest.raises(ValidationError, match="known-insecure"):
            _settings(jwt_secret_key="")

    def test_shared_django_insecure_marker_refuses_to_boot(self):
        with pytest.raises(ValidationError, match="known-insecure"):
            _settings(jwt_secret_key="django-insecure-development-key")

    def test_real_secret_boots_cleanly(self):
        settings = _settings(jwt_secret_key="a-real-generated-secret-1234567890")
        assert settings.jwt_secret_key == "a-real-generated-secret-1234567890"

    def test_bypass_flag_permits_insecure_secret_in_development(self):
        settings = _settings(
            jwt_secret_key="django-insecure-development-key",
            allow_insecure_jwt_secret=True,
            environment="development",
        )
        assert settings.jwt_secret_key == "django-insecure-development-key"

    def test_bypass_flag_is_inert_outside_development(self):
        """A stray GATEWAY_ALLOW_INSECURE_JWT_SECRET=true in a
        staging/production config must never reopen the guard — mirrors
        prod.py's DEV_TOKEN_BYPASS = False hard-rejection."""
        with pytest.raises(ValidationError, match="known-insecure"):
            _settings(
                jwt_secret_key="change-me-in-production",
                allow_insecure_jwt_secret=True,
                environment="production",
            )


class TestCORSGuard:
    """Fail-closed startup check for GATEWAY_CORS_ORIGINS."""

    def test_wildcard_with_credentials_refuses_to_boot(self):
        with pytest.raises(ValidationError, match="explicit list of origins"):
            _settings(cors_origins=["*"], cors_allow_credentials=True)

    def test_empty_origins_with_credentials_refuses_to_boot(self):
        with pytest.raises(ValidationError, match="explicit list of origins"):
            _settings(cors_origins=[], cors_allow_credentials=True)

    def test_explicit_origins_with_credentials_boots_cleanly(self):
        settings = _settings(
            cors_origins=["https://app.example.com"],
            cors_allow_credentials=True,
        )
        assert settings.cors_origins == ["https://app.example.com"]

    def test_wildcard_without_credentials_boots_cleanly(self):
        settings = _settings(cors_origins=["*"], cors_allow_credentials=False)
        assert settings.cors_origins == ["*"]
