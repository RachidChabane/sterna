"""JWT authentication for Orchestrator service."""

import jwt
import os
import logging
from datetime import datetime, timedelta
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme
security = HTTPBearer()

# Get JWT settings from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

# SECURITY: Validate JWT_SECRET_KEY is set in production mode (CWE-798)
if not DEBUG and not JWT_SECRET_KEY:
    logger.critical("[SECURITY] JWT_SECRET_KEY is not set! This is required in production.")
    raise RuntimeError("JWT_SECRET_KEY environment variable must be set in production mode")

# SECURITY: Warn if secret key is too short (should be at least 32 bytes for HS256)
if JWT_SECRET_KEY and len(JWT_SECRET_KEY) < 32:
    logger.warning("[SECURITY] JWT_SECRET_KEY is shorter than recommended (32+ characters). Consider using a stronger key.")


def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """
    Verify JWT token and return user_id.

    In development mode (DEBUG=True), accepts dev tokens (dev-access-token-*).
    In production mode (DEBUG=False), only validates real JWTs.

    Args:
        credentials: HTTP Authorization credentials from request header

    Returns:
        user_id: String ID of the authenticated user

    Raises:
        HTTPException: If token is invalid, expired, or missing required fields
    """
    token = credentials.credentials

    # Development mode: Accept dev tokens ONLY if both DEBUG and no JWT_SECRET_KEY
    # SECURITY: This ensures dev bypass only works in true local development (CWE-287)
    if DEBUG and not JWT_SECRET_KEY and token.startswith("dev-"):
        # Dev token detected - return mock user ID
        # NOTE: This only works when JWT_SECRET_KEY is unset AND DEBUG=True
        logger.warning(f"[DEV AUTH] Accepting dev token (development mode only): {token[:20]}...")
        return "dev-user-1"
    elif DEBUG and token.startswith("dev-"):
        # DEBUG is True but JWT_SECRET_KEY is set - don't allow dev tokens
        logger.warning("[SECURITY] Dev token rejected: DEBUG=True but JWT_SECRET_KEY is set. Use real JWT tokens.")

    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )

        # Validate token type (should be 'access' token)
        token_type = payload.get("type")
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Expected 'access' token.",
            )

        # Extract user_id
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user_id claim.",
            )

        return str(user_id)

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


def verify_jwt_token_from_query(
    token: str = None,
) -> str:
    """
    Verify JWT from query parameter. Used for iframe/preview endpoints
    where the browser cannot attach Authorization headers.
    """

    # This is a placeholder — the actual default comes from the endpoint signature
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    # Reuse the same validation logic
    if DEBUG and not JWT_SECRET_KEY and token.startswith("dev-"):
        return "dev-user-1"

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing user_id")
        return str(user_id)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")


# --- Preview Tokens (short-lived, scope-limited) ---

PREVIEW_TOKEN_EXPIRY = 300  # 5 minutes


def generate_preview_token(user_id: str, port: int) -> str:
    """Generate a short-lived JWT scoped to preview only."""
    payload = {
        "user_id": str(user_id),
        "type": "preview",
        "port": port,
        "exp": datetime.utcnow() + timedelta(seconds=PREVIEW_TOKEN_EXPIRY),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_preview_token(token: str) -> dict:
    """Verify a preview-scoped token. Returns {"user_id": ..., "port": ...}."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing preview token")
    if DEBUG and not JWT_SECRET_KEY and token.startswith("dev-"):
        return {"user_id": "dev-user-1", "port": 0}
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "preview":
            raise HTTPException(status_code=401, detail="Invalid token type — expected preview token")
        user_id = payload.get("user_id")
        port = payload.get("port")
        if not user_id or port is None:
            raise HTTPException(status_code=401, detail="Token missing required claims")
        return {"user_id": str(user_id), "port": int(port)}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Preview token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid preview token: {e}")
