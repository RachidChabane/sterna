"""Centralized client-IP extraction.

Task-29 H1 fix. The deployed topology is:

    client → Cloudflare → cloudflared tunnel → api-gateway → Django

Cloudflare sets ``CF-Connecting-IP`` to the true edge client IP and
appends to ``X-Forwarded-For``. Anyone who can hit a Pod directly
(another compromised pod inside the cluster, a port-forward, a
debug ingress) can spoof ``X-Forwarded-For`` — but not
``CF-Connecting-IP``, which Cloudflare overwrites at the edge.

This helper prefers ``CF-Connecting-IP`` and falls back to ``X-Forwarded-For``
first-hop, then ``REMOTE_ADDR``. In prod/staging (``CF_REQUIRE_HEADER=True``),
a missing ``CF-Connecting-IP`` is logged as a suspicious-activity event so
the gap is visible in Sentry — but we fail OPEN (still return the
fallback IP) so direct-to-pod health checks don't break.

The api-gateway service has its own mirror helper at
``core/api-gateway/gateway/utils/client_ip.py`` — duplicated deliberately
so the gateway image does not depend on Django at runtime.
"""
from __future__ import annotations

import logging

from django.conf import settings


logger = logging.getLogger("security.client_ip")


def get_client_ip(request) -> str:
    cf = (request.META.get("HTTP_CF_CONNECTING_IP") or "").strip()
    if cf:
        return cf
    require_cf = getattr(settings, "CF_REQUIRE_HEADER", False)
    if require_cf:
        # The topology should always carry CF-Connecting-IP. Missing
        # header on a CF-fronted env is interesting — log + fall through.
        # Lazy import: exceptions.py imports things from
        # ``django.conf.settings`` at module import time; importing it at
        # module top-level here would risk a settings-not-ready
        # ImportError when settings reads CF_REQUIRE_HEADER.
        try:
            from exceptions import emit_suspicious_activity

            emit_suspicious_activity(
                category="ip_extract",
                reason="missing_cf_header",
                request=request,
            )
        except Exception:  # noqa: BLE001 — logging must never break the request
            logger.warning(
                "ip_extract.missing_cf_header_emit_failed", exc_info=True
            )
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""
