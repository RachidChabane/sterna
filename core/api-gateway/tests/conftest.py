"""Test fixtures and configuration."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from gateway.auth.jwt import reset_validator
from gateway.config import Settings
from gateway.main import create_app


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        jwt_secret_key="test-secret-key-for-testing",
        jwt_algorithm="HS256",
        redis_url="redis://localhost:6379/0",
        rate_limit_enabled=False,  # Disable for most tests
        environment="test",
        debug=True,
        # cors_origins has no default (see config.py) — credentials are
        # allowed by default, so an explicit, non-wildcard list is required.
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
def app(settings):
    """Create test application."""
    # Override settings
    def get_test_settings():
        return settings

    # Reset validator to use test settings
    reset_validator()

    from gateway import config
    original_get_settings = config.get_settings
    config.get_settings = get_test_settings

    app = create_app()

    yield app

    # Restore original
    config.get_settings = original_get_settings
    reset_validator()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_token(settings):
    """Create a valid JWT token for testing."""
    now = datetime.now(UTC)
    payload = {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "jti": "test-jti-123",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@pytest.fixture
def expired_token(settings):
    """Create an expired JWT token for testing."""
    now = datetime.now(UTC)
    payload = {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "type": "access",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),  # Expired
        "jti": "test-jti-expired",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@pytest.fixture
def invalid_token():
    """Create an invalid JWT token."""
    return "invalid.token.here"
