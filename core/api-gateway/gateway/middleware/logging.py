"""Request/response logging middleware."""

import logging
import time
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("gateway.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs request and response details.

    Log format: method path status_code duration_ms
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()

        # Get request details
        method = request.method
        path = request.url.path
        client_ip = self._get_client_ip(request)
        request_id = getattr(request.state, "request_id", "-")

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Get user info if available
        user_id = getattr(request.state, "user_id", "-")

        logger.info(
            "gateway.access",
            extra={
                "client_ip": client_ip,
                "user_id": user_id,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "request_id": request_id,
            },
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request.

        task-29 H1: delegate to ``gateway.utils.client_ip.get_client_ip``
        (CF-aware). ``X-Real-IP`` is no longer consulted — Cloudflare
        does not set it; only CF-Connecting-IP carries the trusted
        edge client IP in our topology.
        """
        from gateway.utils.client_ip import get_client_ip

        return get_client_ip(request) or "unknown"
