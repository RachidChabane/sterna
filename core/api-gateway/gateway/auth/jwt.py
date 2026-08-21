"""JWT validation utilities - stateless, no database access."""

from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

from ..config import get_settings
from .exceptions import InvalidTokenError, TokenExpiredError


@dataclass
class TokenPayload:
    """Validated JWT token payload."""

    user_id: str
    email: str
    token_type: str
    issued_at: datetime
    expires_at: datetime
    jti: str


class JWTValidator:
    """
    Stateless JWT validation.

    No database access - validates token signature and claims only.
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def validate(
        self, token: str, expected_type: str = "access"
    ) -> TokenPayload | None:
        """
        Validate JWT token and return payload.

        Args:
            token: JWT token string
            expected_type: Expected token type (access or refresh)

        Returns:
            TokenPayload if valid, None otherwise

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is invalid or malformed
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={
                    "require": ["exp", "iat", "user_id", "email", "type"],
                    "verify_exp": True,
                },
            )

            # Validate token type
            if payload.get("type") != expected_type:
                raise InvalidTokenError(
                    f"Expected token type '{expected_type}', got '{payload.get('type')}'"
                )

            return TokenPayload(
                user_id=payload["user_id"],
                email=payload["email"],
                token_type=payload["type"],
                issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
                jti=payload.get("jti", ""),
            )

        except jwt.ExpiredSignatureError as e:
            raise TokenExpiredError("Token has expired") from e
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {e}") from e
        except (KeyError, ValueError) as e:
            raise InvalidTokenError(f"Malformed token payload: {e}") from e

    def validate_safe(
        self, token: str, expected_type: str = "access"
    ) -> TokenPayload | None:
        """
        Validate JWT token without raising exceptions.

        Returns None if token is invalid for any reason.
        """
        try:
            return self.validate(token, expected_type)
        except (TokenExpiredError, InvalidTokenError):
            return None


# Singleton instance
_validator: JWTValidator | None = None


def get_validator() -> JWTValidator:
    """Get or create JWT validator singleton."""
    global _validator
    if _validator is None:
        settings = get_settings()
        _validator = JWTValidator(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
    return _validator


def reset_validator() -> None:
    """Reset validator singleton (for testing)."""
    global _validator
    _validator = None
