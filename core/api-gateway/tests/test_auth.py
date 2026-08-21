"""Tests for JWT authentication."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from gateway.auth.exceptions import InvalidTokenError, TokenExpiredError
from gateway.auth.jwt import JWTValidator, TokenPayload


class TestJWTValidator:
    """Test JWT validation."""

    @pytest.fixture
    def validator(self):
        return JWTValidator(secret_key="test-secret", algorithm="HS256")

    def _create_token(self, payload: dict, secret: str = "test-secret") -> str:
        return jwt.encode(payload, secret, algorithm="HS256")

    def test_validate_valid_token(self, validator):
        """Test validation of a valid token."""
        now = datetime.now(UTC)
        payload = {
            "user_id": "user-123",
            "email": "test@example.com",
            "type": "access",
            "iat": now.timestamp(),
            "exp": (now + timedelta(hours=1)).timestamp(),
            "jti": "jti-123",
        }
        token = self._create_token(payload)

        result = validator.validate(token)

        assert isinstance(result, TokenPayload)
        assert result.user_id == "user-123"
        assert result.email == "test@example.com"
        assert result.token_type == "access"

    def test_validate_expired_token(self, validator):
        """Test validation of an expired token."""
        now = datetime.now(UTC)
        payload = {
            "user_id": "user-123",
            "email": "test@example.com",
            "type": "access",
            "iat": (now - timedelta(hours=2)).timestamp(),
            "exp": (now - timedelta(hours=1)).timestamp(),
            "jti": "jti-123",
        }
        token = self._create_token(payload)

        with pytest.raises(TokenExpiredError):
            validator.validate(token)

    def test_validate_wrong_type(self, validator):
        """Test validation with wrong token type."""
        now = datetime.now(UTC)
        payload = {
            "user_id": "user-123",
            "email": "test@example.com",
            "type": "refresh",  # Wrong type
            "iat": now.timestamp(),
            "exp": (now + timedelta(hours=1)).timestamp(),
            "jti": "jti-123",
        }
        token = self._create_token(payload)

        with pytest.raises(InvalidTokenError) as exc_info:
            validator.validate(token, expected_type="access")

        assert "Expected token type 'access'" in str(exc_info.value)

    def test_validate_invalid_signature(self, validator):
        """Test validation with invalid signature."""
        now = datetime.now(UTC)
        payload = {
            "user_id": "user-123",
            "email": "test@example.com",
            "type": "access",
            "iat": now.timestamp(),
            "exp": (now + timedelta(hours=1)).timestamp(),
            "jti": "jti-123",
        }
        token = self._create_token(payload, secret="wrong-secret")

        with pytest.raises(InvalidTokenError):
            validator.validate(token)

    def test_validate_malformed_token(self, validator):
        """Test validation of malformed token."""
        with pytest.raises(InvalidTokenError):
            validator.validate("not-a-valid-token")

    def test_validate_missing_claims(self, validator):
        """Test validation with missing required claims."""
        now = datetime.now(UTC)
        payload = {
            "user_id": "user-123",
            # Missing email, type
            "iat": now.timestamp(),
            "exp": (now + timedelta(hours=1)).timestamp(),
        }
        token = self._create_token(payload)

        with pytest.raises(InvalidTokenError):
            validator.validate(token)

    def test_validate_safe_returns_none_on_error(self, validator):
        """Test validate_safe returns None instead of raising."""
        result = validator.validate_safe("invalid-token")
        assert result is None

    def test_validate_safe_returns_payload_on_success(self, validator):
        """Test validate_safe returns payload on success."""
        now = datetime.now(UTC)
        payload = {
            "user_id": "user-123",
            "email": "test@example.com",
            "type": "access",
            "iat": now.timestamp(),
            "exp": (now + timedelta(hours=1)).timestamp(),
            "jti": "jti-123",
        }
        token = self._create_token(payload)

        result = validator.validate_safe(token)

        assert result is not None
        assert result.user_id == "user-123"
