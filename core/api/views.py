"""
Health check and monitoring views for Sterna.
"""

import time
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views import View
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator

import redis


@method_decorator(never_cache, name="dispatch")
class HealthCheckView(View):
    """Basic health check endpoint."""

    def get(self, request):
        """Return basic health status."""
        return JsonResponse(
            {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "sterna-api",
                "version": "1.0.0",
            }
        )


@method_decorator(never_cache, name="dispatch")
class LivenessProbeView(View):
    """Kubernetes liveness probe endpoint."""

    def get(self, request):
        """Return liveness status."""
        return JsonResponse(
            {
                "status": "alive",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )


@method_decorator(never_cache, name="dispatch")
class ReadinessProbeView(View):
    """Kubernetes readiness probe endpoint."""

    def get(self, request):
        """Check if service is ready to accept requests."""
        checks = {
            "database": False,
            "cache": False,
            "redis": False,
        }
        errors = []

        # Check database connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                checks["database"] = True
        except Exception as e:
            errors.append(f"Database check failed: {str(e)}")

        # Check cache
        try:
            cache_key = "health_check_test"
            cache.set(cache_key, "test", 10)
            if cache.get(cache_key) == "test":
                checks["cache"] = True
                cache.delete(cache_key)
        except Exception as e:
            errors.append(f"Cache check failed: {str(e)}")

        # Check Redis connection
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
            redis_client.ping()
            checks["redis"] = True
        except Exception as e:
            errors.append(f"Redis check failed: {str(e)}")

        # Determine overall status
        all_healthy = all(checks.values())
        status_code = 200 if all_healthy else 503

        response_data = {
            "status": "ready" if all_healthy else "not_ready",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks,
        }

        if errors:
            response_data["errors"] = errors

        return JsonResponse(response_data, status=status_code)


@method_decorator(never_cache, name="dispatch")
class DetailedHealthView(View):
    """Detailed health check with performance metrics."""

    def get(self, request):
        """Return detailed health and performance metrics."""
        start_time = time.time()

        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "sterna-api",
            "version": "1.0.0",
            "environment": settings.DJANGO_ENV
            if hasattr(settings, "DJANGO_ENV")
            else "unknown",
            "checks": {},
            "metrics": {},
        }

        # Database check with timing
        db_start = time.time()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                health_data["checks"]["database"] = {
                    "status": "healthy",
                    "response_time_ms": round((time.time() - db_start) * 1000, 2),
                }
        except Exception as e:
            health_data["checks"]["database"] = {
                "status": "unhealthy",
                "error": str(e),
                "response_time_ms": round((time.time() - db_start) * 1000, 2),
            }

        # Cache check with timing
        cache_start = time.time()
        try:
            cache_key = "health_check_detailed"
            cache.set(cache_key, "test", 10)
            value = cache.get(cache_key)
            if value == "test":
                cache.delete(cache_key)
                health_data["checks"]["cache"] = {
                    "status": "healthy",
                    "response_time_ms": round((time.time() - cache_start) * 1000, 2),
                }
            else:
                health_data["checks"]["cache"] = {
                    "status": "unhealthy",
                    "error": "Cache read/write test failed",
                    "response_time_ms": round((time.time() - cache_start) * 1000, 2),
                }
        except Exception as e:
            health_data["checks"]["cache"] = {
                "status": "unhealthy",
                "error": str(e),
                "response_time_ms": round((time.time() - cache_start) * 1000, 2),
            }

        # Redis check with timing
        redis_start = time.time()
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
            redis_client.ping()
            health_data["checks"]["redis"] = {
                "status": "healthy",
                "response_time_ms": round((time.time() - redis_start) * 1000, 2),
            }
        except Exception as e:
            health_data["checks"]["redis"] = {
                "status": "unhealthy",
                "error": str(e),
                "response_time_ms": round((time.time() - redis_start) * 1000, 2),
            }

        # Overall metrics
        health_data["metrics"]["total_response_time_ms"] = round(
            (time.time() - start_time) * 1000, 2
        )

        # Determine overall status
        all_healthy = all(
            check.get("status") == "healthy" for check in health_data["checks"].values()
        )

        if not all_healthy:
            health_data["status"] = "degraded"

        status_code = 200 if all_healthy else 503

        return JsonResponse(health_data, status=status_code)
