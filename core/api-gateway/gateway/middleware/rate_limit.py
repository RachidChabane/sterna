"""Rate limiting middleware."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..config import get_settings
from ..rate_limiting.redis_limiter import RedisRateLimiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis sliding window.

    Applies per-user (if authenticated) or per-IP limits.
    """

    def __init__(self, app, limiter: RedisRateLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        # Skip if rate limiting is disabled
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Skip for OPTIONS requests
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip for health endpoints
        if request.url.path in ["/health", "/ready", "/metrics"]:
            return await call_next(request)

        # Determine identifier (user ID if authenticated, else IP)
        identifier = self._get_identifier(request)
        endpoint = request.url.path

        # Check rate limit
        result = await self.limiter.check(identifier, endpoint)

        if not result.allowed:
            logger.warning(
                f"Rate limit exceeded for {identifier} on {endpoint}. "
                f"Retry after {result.retry_after:.1f}s"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": int(result.retry_after) if result.retry_after else 60,
                },
                headers={
                    "Retry-After": str(int(result.retry_after) if result.retry_after else 60),
                    "X-RateLimit-Limit": str(self.limiter.default_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(result.reset_at)),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

        return response

    def _get_identifier(self, request: Request) -> str:
        """Get rate limit identifier from request."""
        # Prefer user ID if authenticated
        if hasattr(request.state, "user_id") and request.state.user_id:
            return f"user:{request.state.user_id}"

        # task-29 H1: CF-aware client IP (prefer CF-Connecting-IP).
        from gateway.utils.client_ip import get_client_ip

        ip = get_client_ip(request)
        return f"ip:{ip}" if ip else "ip:unknown"
