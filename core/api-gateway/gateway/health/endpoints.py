"""Health check endpoints."""

import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: float
    version: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Basic health check.

    Returns immediately without checking dependencies.
    """
    from .. import __version__

    return HealthResponse(
        status="healthy",
        timestamp=time.time(),
        version=__version__,
        checks={},
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """
    Readiness check including dependencies.

    Verifies Redis connectivity.
    """
    from .. import __version__
    from ..main import redis_client

    checks = {}
    status = "healthy"

    # Check Redis
    try:
        if redis_client:
            await redis_client.ping()
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "not initialized"
            status = "degraded"
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"
        status = "unhealthy"

    return HealthResponse(
        status=status,
        timestamp=time.time(),
        version=__version__,
        checks=checks,
    )


@router.get("/metrics", status_code=501)
async def metrics():
    """
    Metrics endpoint — NOT implemented.

    Prometheus metrics are future work. This used to return hardcoded
    zero-valued placeholder series, which read as real (dead) traffic
    on any dashboard that scraped it. Until real instrumentation
    lands, answer 501 honestly instead of serving fake data.
    Observability today = structured JSON logs + Sentry + Better
    Uptime (see docs/operations/observability.md).
    """
    from starlette.responses import JSONResponse

    return JSONResponse(
        status_code=501,
        content={
            "detail": (
                "Prometheus metrics are not implemented. "
                "Use structured logs + Sentry + Better Uptime; "
                "see docs/operations/observability.md."
            ),
        },
    )
