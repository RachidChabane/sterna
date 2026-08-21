"""HTTP proxy router for backend services."""

import logging
import uuid

import httpx
from fastapi import Request
from starlette.responses import Response, StreamingResponse

from ..config import get_settings

logger = logging.getLogger(__name__)


class ProxyRouter:
    """
    HTTP proxy router for backend services.

    Routes requests to appropriate backend based on path prefix.
    Enriches requests with user context headers.
    """

    def __init__(self):
        settings = get_settings()
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.proxy_timeout,
                connect=settings.proxy_connect_timeout,
            ),
            follow_redirects=False,
            limits=httpx.Limits(
                max_keepalive_connections=100,
                max_connections=200,
            ),
        )
        self._routes = None

    @property
    def routes(self) -> dict:
        """Get routes configuration (lazy loaded)."""
        if self._routes is None:
            self._routes = get_settings().routes
        return self._routes

    @property
    def rewrites(self) -> dict:
        """Get route rewrite rules (lazy loaded)."""
        settings = get_settings()
        return getattr(settings, 'route_rewrites', {})

    def get_timeout_for_path(self, path: str) -> float:
        """Get timeout for a specific path, checking route_timeouts config."""
        settings = get_settings()
        route_timeouts = getattr(settings, 'route_timeouts', {})

        # Check for matching route timeout (longest prefix match)
        best_timeout = settings.proxy_timeout
        best_match_len = 0

        for prefix, timeout in route_timeouts.items():
            if path.startswith(prefix) and len(prefix) > best_match_len:
                best_timeout = timeout
                best_match_len = len(prefix)

        return best_timeout

    def get_backend_url(self, path: str) -> tuple[str | None, str]:
        """
        Find backend URL for given path and apply rewrite rules.

        Uses longest prefix match for routing, then applies rewrite
        rules to transform the path.

        Returns:
            Tuple of (backend_url, rewritten_path)

        Examples:
            /api/v1/auth/login -> (http://web:8000, /api/auth/login)
            /api/v1/sandbox/execute -> (http://orchestrator:8003, /execute)
        """
        best_match = None
        best_match_len = 0
        best_prefix = ""

        for prefix, backend in self.routes.items():
            if path.startswith(prefix) and len(prefix) > best_match_len:
                best_match = backend
                best_match_len = len(prefix)
                best_prefix = prefix

        if best_match:
            # Get the remainder of the path after the prefix
            remainder = path[len(best_prefix):]

            # Apply rewrite rule if exists
            rewrite_prefix = self.rewrites.get(best_prefix)

            if rewrite_prefix is not None:
                # Rewrite: /api/v1/auth/login -> /api/auth/login
                # or /api/v1/sandbox/execute -> /execute (if rewrite is "")
                rewritten_path = f"{rewrite_prefix}{remainder}" or "/"
            else:
                # No rewrite rule - strip prefix entirely
                rewritten_path = remainder or "/"

            return best_match, rewritten_path

        return None, path

    async def proxy(self, request: Request) -> Response:
        """
        Proxy request to appropriate backend.

        Enriches request with user context headers.
        """
        path = request.url.path
        backend_url, stripped_path = self.get_backend_url(path)

        if not backend_url:
            logger.warning(f"No route found for path: {path}")
            return Response(
                content='{"detail": "No route found"}',
                status_code=404,
                media_type="application/json",
            )

        # Build target URL with stripped path
        # e.g., /api/v1/sandbox/execute -> http://orchestrator:8003/execute
        target_url = f"{backend_url}{stripped_path}"
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"

        # Build headers
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("Host", None)

        # Add enrichment headers
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        headers["X-Request-ID"] = request_id

        # Add user context if authenticated
        if hasattr(request.state, "user_id") and request.state.user_id:
            headers["X-User-ID"] = request.state.user_id
        if hasattr(request.state, "user_email") and request.state.user_email:
            headers["X-User-Email"] = request.state.user_email

        # Forward client IP
        client_ip = self._get_client_ip(request)
        if client_ip:
            existing = headers.get("X-Forwarded-For", "")
            if existing:
                headers["X-Forwarded-For"] = f"{client_ip}, {existing}"
            else:
                headers["X-Forwarded-For"] = client_ip

        # Add forwarded headers
        headers["X-Forwarded-Proto"] = request.url.scheme
        headers["X-Forwarded-Host"] = request.headers.get("host", "")

        # Get request body
        body = await request.body()

        try:
            # Check if this is a streaming endpoint
            # These endpoints return SSE/chunked responses that need to be streamed
            streaming_paths = [
                "/llm/completions/stream",
                "/api/llm/completions/stream",
                "/api/v1/llm/completions/stream",
            ]
            is_streaming_request = any(
                stripped_path.startswith(sp) for sp in streaming_paths
            )

            # Get per-route timeout (may be longer for certain operations)
            route_timeout = self.get_timeout_for_path(path)
            settings = get_settings()

            logger.info(f"Proxy request: path={path}, stripped_path={stripped_path}, is_streaming={is_streaming_request}, timeout={route_timeout}s")

            if is_streaming_request:
                # Use streaming for SSE requests
                return await self._proxy_streaming(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    body=body,
                    request_id=request_id,
                    timeout=route_timeout,
                )

            # Make regular proxied request with per-route timeout
            response = await self.client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                timeout=httpx.Timeout(route_timeout, connect=settings.proxy_connect_timeout),
            )

            # Build response headers
            excluded_headers = {
                "content-encoding",
                "content-length",
                "transfer-encoding",
                "connection",
            }
            response_headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in excluded_headers
            }
            response_headers["X-Request-ID"] = request_id

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.headers.get("content-type"),
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout proxying to {target_url}")
            return Response(
                content='{"detail": "Backend timeout"}',
                status_code=504,
                media_type="application/json",
            )
        except httpx.ConnectError as e:
            logger.error(f"Connection error proxying to {target_url}: {e}")
            return Response(
                content='{"detail": "Backend unavailable"}',
                status_code=502,
                media_type="application/json",
            )
        except httpx.RequestError as e:
            logger.error(f"Error proxying to {target_url}: {e}")
            return Response(
                content='{"detail": "Backend error"}',
                status_code=502,
                media_type="application/json",
            )

    async def _proxy_streaming(
        self,
        method: str,
        url: str,
        headers: dict,
        body: bytes,
        request_id: str,
        timeout: float = 300.0,
    ) -> StreamingResponse:
        """
        Proxy a streaming request (SSE/event-stream).

        Uses httpx streaming to forward chunks as they arrive.
        """
        settings = get_settings()

        async def stream_generator():
            async with self.client.stream(
                method=method,
                url=url,
                headers=headers,
                content=body,
                timeout=httpx.Timeout(timeout, connect=settings.proxy_connect_timeout),
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

        # Build response headers for streaming
        response_headers = {
            "X-Request-ID": request_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers=response_headers,
        )

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract client IP from request.

        task-29 H1: re-anchored to ``gateway.utils.client_ip.get_client_ip``
        so the XFF chain forwarded to Django carries the CF-aware
        client IP (not the gateway pod's own client.host).
        """
        from gateway.utils.client_ip import get_client_ip

        ip = get_client_ip(request)
        return ip or None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
