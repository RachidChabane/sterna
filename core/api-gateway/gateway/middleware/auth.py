"""JWT Authentication middleware."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..auth.exceptions import InvalidTokenError, TokenExpiredError
from ..auth.jwt import get_validator
from ..config import get_settings

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    JWT Authentication middleware.

    Validates JWT tokens and enriches requests with user context.
    Public paths bypass authentication.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        path = request.url.path

        # Skip auth for public paths
        if self._is_public_path(path, settings.public_paths):
            return await call_next(request)

        # Skip auth for WebSocket upgrades — WS endpoints handle their own auth
        # via query param JWT (browsers can't set headers on WebSocket connections)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Skip auth for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate token
        try:
            validator = get_validator()
            payload = validator.validate(token)
        except TokenExpiredError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Store user context in request state
        request.state.user = payload
        request.state.user_id = payload.user_id
        request.state.user_email = payload.email
        request.state.authenticated = True

        # Continue to next middleware/route
        response = await call_next(request)

        return response

    def _extract_token(self, request: Request) -> str | None:
        """Extract Bearer token from Authorization header."""
        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            return auth_header[7:]

        return None

    def _is_public_path(self, path: str, public_paths: list) -> bool:
        """Check if path is public (no auth required)."""
        for public_path in public_paths:
            if path == public_path or path.startswith(public_path + "/"):
                return True
            # Handle paths with trailing slashes
            if path.rstrip("/") == public_path.rstrip("/"):
                return True
        return False
