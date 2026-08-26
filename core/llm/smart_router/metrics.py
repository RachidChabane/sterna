"""
Real-time Redis counters for smart router routing metrics.
"""

import logging
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

METRICS_PREFIX = "smart_router:metrics"


def _safe_incr(key: str, delta: int = 1):
    """Increment a cache counter, initializing to 0 if needed."""
    try:
        cache.incr(key, delta)
    except ValueError:
        # Key doesn't exist yet — set it
        cache.set(key, delta, timeout=None)


def record_routing_decision(
    tier: int,
    resolved_model: str,
    cost_tier: str,
    score: int,
    classification_latency_ms: Optional[int] = None,
    is_reroute: bool = False,
    tier2_fallback: bool = False,
):
    """Increment real-time counters for monitoring."""
    try:
        _safe_incr(f"{METRICS_PREFIX}:tier:{tier}")
        _safe_incr(f"{METRICS_PREFIX}:model:{resolved_model}")
        _safe_incr(f"{METRICS_PREFIX}:cost_tier:{cost_tier}")

        if is_reroute:
            _safe_incr(f"{METRICS_PREFIX}:reroutes")
        if tier2_fallback:
            _safe_incr(f"{METRICS_PREFIX}:tier2_fallbacks")

        # Score distribution bucket
        bucket = (score // 10) * 10
        _safe_incr(f"{METRICS_PREFIX}:score_bucket:{bucket}")

        # Latency histogram bucket
        if classification_latency_ms is not None:
            latency_bucket = (classification_latency_ms // 100) * 100
            _safe_incr(f"{METRICS_PREFIX}:latency_bucket:{latency_bucket}")
    except Exception as e:
        logger.debug(f"[SmartRouter Metrics] Failed to record metrics: {e}")
