"""
Model selection from the smart router's routing pool.

Selects the cheapest model that meets the complexity score and capability requirements.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

POOL_CACHE_KEY = "smart_router:routing_pool"
POOL_CACHE_TTL = 300  # 5 minutes

COST_TIER_ORDER = {'budget': 0, 'balanced': 1, 'premium': 2}

FALLBACK_MODEL = "google/gemini-2.0-flash-001"


def _load_pool() -> list:
    """Load active routing pool entries, cached for 5 minutes."""
    cached = cache.get(POOL_CACHE_KEY)
    if cached is not None:
        return cached

    from llm.models import RoutingPool
    entries = list(
        RoutingPool.objects.filter(is_active=True)
        .select_related('model')
        .order_by('cost_tier', '-priority')
    )

    pool = []
    for entry in entries:
        model = entry.model
        pool.append({
            'model_id': model.model_id,
            'cost_tier': entry.cost_tier,
            'min_score': entry.min_complexity_score,
            'max_score': entry.max_complexity_score,
            'priority': entry.priority,
            'supports_reasoning': model.supports_reasoning,
            'input_modalities': model.input_modalities or [],
            'max_tokens': model.max_tokens or 0,
            'supports_functions': model.supports_functions,
        })

    # Sort by cost tier (budget first), then priority (highest first)
    pool.sort(key=lambda e: (COST_TIER_ORDER.get(e['cost_tier'], 99), -e['priority']))

    cache.set(POOL_CACHE_KEY, pool, timeout=POOL_CACHE_TTL)
    return pool


def select_model(
    final_score: int,
    needs_vision: bool = False,
    needs_reasoning: bool = False,
    needs_long_context: bool = False,
    excluded_models: list = None,
) -> tuple:
    """
    Select the cheapest model meeting score and capability requirements.

    Returns (model_id, cost_tier) or (FALLBACK_MODEL, 'budget') if no match.
    """
    pool = _load_pool()
    excluded = set(excluded_models or [])

    for entry in pool:
        model_id = entry['model_id']

        # Skip excluded
        if model_id in excluded:
            continue

        # Check score range
        if not (entry['min_score'] <= final_score <= entry['max_score']):
            continue

        # Check capabilities
        if needs_vision and 'image' not in entry.get('input_modalities', []):
            continue
        if needs_reasoning and not entry.get('supports_reasoning', False):
            continue
        if needs_long_context and (entry.get('max_tokens', 0) or 0) < 100000:
            continue

        return model_id, entry['cost_tier']

    # Fallback: most capable non-excluded model
    for entry in reversed(pool):
        if entry['model_id'] not in excluded:
            logger.warning(
                f"[SmartRouter Scorer] No score-matching model for score={final_score}, "
                f"falling back to {entry['model_id']}"
            )
            return entry['model_id'], entry['cost_tier']

    # Ultimate fallback
    logger.warning(f"[SmartRouter Scorer] Pool empty or all excluded, using fallback {FALLBACK_MODEL}")
    return FALLBACK_MODEL, 'budget'
