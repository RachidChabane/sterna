"""JWT authentication and authorization."""

import logging

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme
security = HTTPBearer()


def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> UUID:
    """
    Verify JWT token and return user_id.

    In development mode (DEBUG=True), accepts dev tokens (dev-access-token-*).
    In production mode (DEBUG=False), only validates real JWTs.

    Args:
        credentials: HTTP Authorization credentials from request header

    Returns:
        user_id: UUID of the authenticated user

    Raises:
        HTTPException: If token is invalid, expired, or missing required fields
    """
    token = credentials.credentials

    # Development mode: Accept dev tokens
    if settings.debug and token.startswith("dev-"):
        # Dev token detected - return mock user ID
        # This allows local development without real JWT tokens.
        # NEVER log the token itself — presence marker only.
        logger.debug("auth.dev_token_accepted", extra={"dev_auth": True})
        return UUID("00000000-0000-0000-0000-000000000001")

    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        # Validate token type (should be 'access' token)
        token_type = payload.get("type")
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Expected 'access' token.",
            )

        # Extract user_id
        user_id_str = payload.get("user_id")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user_id claim.",
            )

        # Convert to UUID
        try:
            user_id = UUID(user_id_str)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user_id format in token.",
            )

        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token validation error: {str(e)}",
        )


# Dependency for protected routes
CurrentUser = verify_jwt_token
