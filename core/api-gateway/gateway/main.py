"""
Sterna API Gateway - Main Application

Handles authentication, rate limiting, and routing for all backend services.
"""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
import uvicorn
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ._observability import init_observability  # noqa: E402
from .config import get_settings
from .health.endpoints import router as health_router
from .middleware.auth import AuthMiddleware
from .middleware.logging import LoggingMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIDMiddleware
from .rate_limiting.redis_limiter import RedisRateLimiter
from .routing.proxy import ProxyRouter

init_observability(service="api-gateway", app_loggers=("gateway",))
logger = logging.getLogger(__name__)

# Global instances (initialized in lifespan)
redis_client: redis.Redis | None = None
rate_limiter: RedisRateLimiter | None = None
proxy_router: ProxyRouter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global redis_client, rate_limiter, proxy_router

    settings = get_settings()

    logger.info(f"Starting API Gateway in {settings.environment} mode")

    # Initialize Redis
    try:
        redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        # Continue without Redis - rate limiting will fail open
        redis_client = None

    # Initialize rate limiter
    if redis_client:
        rate_limiter = RedisRateLimiter(
            redis_client=redis_client,
            default_limit=settings.default_rate_limit,
            default_window=3600,
        )
        logger.info("Rate limiter initialized")
    else:
        logger.warning("Rate limiter disabled - Redis not available")

    # Initialize proxy router
    proxy_router = ProxyRouter()
    logger.info(f"Proxy router initialized with {len(proxy_router.routes)} routes")

    logger.info("API Gateway started")

    yield

    # Cleanup
    if proxy_router:
        await proxy_router.close()

    if redis_client:
        await redis_client.close()

    logger.info("API Gateway stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Sterna API Gateway",
        description="API Gateway for authentication, rate limiting, and routing",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS middleware (must be first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    )

    # Request ID middleware
    app.add_middleware(RequestIDMiddleware)

    # Logging middleware
    app.add_middleware(LoggingMiddleware)

    # Auth middleware
    app.add_middleware(AuthMiddleware)

    # Health check routes (before proxy catch-all)
    app.include_router(health_router)

    # WebSocket proxy route — forwards WS connections to backend services
    @app.websocket("/api/v1/sandbox/ws/{path:path}")
    async def proxy_websocket(websocket: WebSocket, path: str):
        """Proxy WebSocket connections to the orchestrator."""
        # Build backend WS URL: strip /api/v1/sandbox prefix, forward to orchestrator
        query = str(websocket.query_params) if websocket.query_params else ""
        backend_url = f"ws://orchestrator:8003/ws/{path}"
        if query:
            backend_url = f"{backend_url}?{query}"

        await websocket.accept()

        try:
            async with websockets.connect(backend_url) as backend_ws:
                import asyncio

                async def client_to_backend():
                    try:
                        while True:
                            data = await websocket.receive_text()
                            await backend_ws.send(data)
                    except WebSocketDisconnect:
                        pass

                async def backend_to_client():
                    try:
                        async for message in backend_ws:
                            await websocket.send_text(message)
                    except Exception:
                        pass

                # Run both directions concurrently
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(client_to_backend()),
                        asyncio.create_task(backend_to_client()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()

        except Exception as e:
            logger.debug(f"WebSocket proxy error: {e}")
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    # Catch-all proxy route
    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )
    async def proxy_request(request: Request, path: str):
        """Proxy all requests to appropriate backend services."""
        return await proxy_router.proxy(request)

    return app


# Create app instance
app = create_app()


# Add rate limit middleware after app creation (needs rate_limiter from lifespan)
@app.on_event("startup")
async def add_rate_limit_middleware():
    """Add rate limit middleware after Redis is initialized."""
    if rate_limiter:
        app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)
        logger.info("Rate limit middleware enabled")


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "gateway.main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.debug,
        log_level="info",
    )
