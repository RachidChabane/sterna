"""Centralized client-IP extraction for the api-gateway.

Task-29 H1 mirror of ``core/sterna/client_ip.py``. Same algorithm,
but reads from a Starlette/FastAPI request object instead of Django's
``request.META``. Duplicated deliberately so the gateway image does
not depend on Django at runtime.

Algorithm: prefer ``CF-Connecting-IP`` (set only by Cloudflare), fall
back to ``X-Forwarded-For`` first hop, then Starlette's ``client.host``.
When ``CF_REQUIRE_HEADER=true`` and the CF header is missing, emit a
warning log line (fail-open: still return a fallback IP) so missing
CF headers are visible in observability.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger("gateway.security.client_ip")


def _require_cf_header() -> bool:
    return os.getenv("CF_REQUIRE_HEADER", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def get_client_ip(request: Request) -> str:
    cf = (request.headers.get("CF-Connecting-IP") or "").strip()
    if cf:
        return cf
    if _require_cf_header():
        # Same fail-open rationale as the Django side: don't break
        # direct-to-pod health checks. Just make missing CF visible.
        logger.warning(
            "ip_extract.missing_cf_header",
            extra={
                "path": str(request.url.path),
                "client_host": (
                    request.client.host if request.client else None
                ),
            },
        )
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""
