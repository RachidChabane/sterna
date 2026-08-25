"""
Query building for the model catalog list endpoint.

Owns catalog population, filtering, sorting, pagination, and the
provider-count aggregation `ModelCatalogViewSet.list` returns; the
view keeps only request parsing and response caching.
"""

import hashlib
import json
import logging

from django.core.cache import cache
from django.db import models
from django.db.models import F, ExpressionWrapper, FloatField, Case, When, IntegerField, Q, Count

from ..catalog_service import CatalogService
from ..constants import MODEL_TIERS
from ..icon_config import PROVIDER_ICON_MAPPINGS, KNOWN_LOBEHUB_ICONS
from ..serializers import ModelCatalogSerializer
from ..utils import exclude_blacklisted_providers

logger = logging.getLogger(__name__)


def provider_icon_conditions() -> Q:
    """Q matching any provider with a known icon (case-insensitive)."""
    providers_with_icons = set(PROVIDER_ICON_MAPPINGS.keys()) | KNOWN_LOBEHUB_ICONS
    conditions = Q()
    for provider in providers_with_icons:
        conditions |= Q(provider__iexact=provider)
    return conditions


def model_icon_conditions() -> Q:
    """Q matching model IDs carrying a model-specific icon keyword."""
    model_icon_keywords = [
        "claude", "gemini", "mistral", "deepseek", "qwen", "yi",
        "command", "grok", "palm", "bard", "phi", "wizardlm",
        "orca", "falcon", "nova", "baichuan", "chatglm", "glm"
    ]
    conditions = Q()
    for keyword in model_icon_keywords:
        conditions |= Q(model_id__icontains=keyword)
    return conditions


def models_with_icons_queryset(queryset):
    """Restrict `queryset` to models that have either a provider or model icon."""
    return queryset.filter(provider_icon_conditions() | model_icon_conditions())


def build_model_list_response(filters: dict, query_params, fallback_queryset) -> dict:
    """Build the paginated, filtered, sorted model-list response body.

    `fallback_queryset` is used when the catalog service's smart fetch
    raises — it is the view's own `ModelCatalog` queryset, already
    scoped to available and non-blacklisted models.
    """
    # Build cache key based on all filter parameters
    cache_key_data = {
        'filters': filters,
        'page': query_params.get('page', 1),
        'page_size': query_params.get('page_size', 25)
    }
    cache_key_hash = hashlib.md5(
        json.dumps(cache_key_data, sort_keys=True).encode()
    ).hexdigest()
    cache_key = f"models:list:{cache_key_hash}"

    # Try to get cached response
    cached_response = cache.get(cache_key)
    if cached_response is not None:
        logger.debug(f"Cache HIT for models list: {cache_key}")
        return cached_response

    logger.debug(f"Cache MISS for models list: {cache_key}")

    # Use CatalogService to ensure models are populated from OpenRouter
    catalog = CatalogService()

    try:
        # This will auto-fetch from OpenRouter if the catalog is empty
        queryset = catalog.get_all_models_smart()
    except Exception as e:
        logger.warning(f"Failed to fetch models from OpenRouter: {e}")
        # Fall back to whatever is in the database
        queryset = fallback_queryset

        # If database is also empty, return empty list with a message
        if not queryset.exists():
            return {
                "results": [],
                "message": "Model catalog is empty. Please check your OpenRouter API key configuration."
            }

    # Apply blacklist filter (exclude providers that should never be exposed)
    queryset = exclude_blacklisted_providers(queryset)

    # Apply filters
    # Apply search filter
    if filters.get("search"):
        search_term = filters["search"]
        queryset = queryset.filter(
            models.Q(name__icontains=search_term) |
            models.Q(provider__icontains=search_term)
        )

    if filters.get("provider"):
        queryset = queryset.filter(provider__iexact=filters["provider"])

    if filters.get("available_only", True):
        queryset = queryset.filter(is_available=True)

    if filters.get("min_context_length"):
        queryset = queryset.filter(max_tokens__gte=filters["min_context_length"])

    # Apply tier filtering
    if filters.get("tier"):
        tier_models = MODEL_TIERS.get(filters["tier"], {}).get("models", [])
        if tier_models:
            queryset = queryset.filter(model_id__in=tier_models)

    # Only filter by supports_functions if explicitly provided in request
    if "supports_functions" in query_params:
        queryset = queryset.filter(supports_functions=filters["supports_functions"])

    # Only filter by supports_streaming if explicitly provided in request
    if "supports_streaming" in query_params:
        queryset = queryset.filter(supports_streaming=filters["supports_streaming"])

    # Only filter by supports_structured_outputs if explicitly provided in request
    if "supports_structured_outputs" in query_params:
        queryset = queryset.filter(supports_structured_outputs=filters["supports_structured_outputs"])

    # Only filter by supports_reasoning if explicitly provided in request
    if "supports_reasoning" in query_params:
        queryset = queryset.filter(supports_reasoning=filters["supports_reasoning"])

    # Only filter by supports_prompt_caching if explicitly provided in request
    if "supports_prompt_caching" in query_params:
        queryset = queryset.filter(supports_prompt_caching=filters["supports_prompt_caching"])

    # Only filter by supports_stream_cancellation if explicitly provided in request
    if "supports_stream_cancellation" in query_params:
        queryset = queryset.filter(supports_stream_cancellation=filters["supports_stream_cancellation"])

    # Filter by input_modalities if explicitly provided in request
    if filters.get("input_modalities"):
        for modality in filters["input_modalities"]:
            queryset = queryset.filter(input_modalities__contains=modality)

    # Apply tag filtering
    if filters.get("tags"):
        # Filter models that have any of the specified tags
        tag_query = None
        for tag in filters["tags"]:
            if tag_query is None:
                tag_query = models.Q(tags__contains=tag)
            else:
                tag_query |= models.Q(tags__contains=tag)
        if tag_query:
            queryset = queryset.filter(tag_query)

    # Apply has_icon filtering (default: True - only show models with icons)
    if filters.get("has_icon", True):
        queryset = models_with_icons_queryset(queryset)

    # Apply price range filtering
    if filters.get("max_price") is not None:
        max_price = filters.get("max_price")

        # Filter to keep models where BOTH prompt and completion prices are <= max_price
        # This ensures consistent behavior with frontend filtering (Calculator/Comparison)
        # Allow NULL prices (free models) by using isnull=True in OR condition
        queryset = queryset.filter(
            models.Q(prompt_price__lte=max_price) | models.Q(prompt_price__isnull=True),
            models.Q(completion_price__lte=max_price) | models.Q(completion_price__isnull=True)
        )

    # Apply dynamic sorting based on sort_by parameter
    sort_by = filters.get('sort_by', 'none')
    order = filters.get('order', 'asc')

    # Build ordering based on sort_by
    if sort_by == 'prompt_cost':
        # Nulls last: use COALESCE-like behavior with Case/When or simple nulls handling
        ordering = 'prompt_price' if order == 'asc' else '-prompt_price'
        queryset = queryset.order_by(models.F(ordering.lstrip('-')).asc(nulls_last=True) if order == 'asc' else models.F(ordering.lstrip('-')).desc(nulls_last=True))
    elif sort_by == 'completion_cost':
        ordering = 'completion_price' if order == 'asc' else '-completion_price'
        queryset = queryset.order_by(models.F(ordering.lstrip('-')).asc(nulls_last=True) if order == 'asc' else models.F(ordering.lstrip('-')).desc(nulls_last=True))
    elif sort_by == 'overall_cost':
        # Annotate with sum of prompt + completion prices
        queryset = queryset.annotate(
            overall_cost=ExpressionWrapper(
                F('prompt_price') + F('completion_price'),
                output_field=FloatField()
            )
        )
        ordering = 'overall_cost' if order == 'asc' else '-overall_cost'
        queryset = queryset.order_by(models.F(ordering.lstrip('-')).asc(nulls_last=True) if order == 'asc' else models.F(ordering.lstrip('-')).desc(nulls_last=True))
    elif sort_by == 'max_tokens':
        ordering = 'max_tokens' if order == 'asc' else '-max_tokens'
        queryset = queryset.order_by(models.F(ordering.lstrip('-')).asc(nulls_last=True) if order == 'asc' else models.F(ordering.lstrip('-')).desc(nulls_last=True))
    elif sort_by == 'latency':
        # Sort by median latency (p50) - lower is better
        queryset = queryset.order_by(models.F('latency_p50').asc(nulls_last=True) if order == 'asc' else models.F('latency_p50').desc(nulls_last=True))
    elif sort_by == 'throughput':
        # Sort by median throughput (p50) - higher is better
        queryset = queryset.order_by(models.F('throughput_p50').asc(nulls_last=True) if order == 'asc' else models.F('throughput_p50').desc(nulls_last=True))
    elif sort_by == 'provider' or sort_by == 'none':
        # Create Q objects for case-insensitive matching
        icon_conditions = provider_icon_conditions()

        # Annotate with has_icon (1 if has icon, 0 otherwise)
        queryset = queryset.annotate(
            has_icon=Case(
                When(icon_conditions, then=1),
                default=0,
                output_field=IntegerField()
            )
        )

        # Sort: icons first (has_icon DESC), then alphabetically by provider and name
        if order == 'asc':
            queryset = queryset.order_by('-has_icon', 'provider', 'name')
        else:
            queryset = queryset.order_by('-has_icon', '-provider', '-name')
    else:
        # Fallback: just sort by name
        queryset = queryset.order_by('name')

    # Calculate provider counts (before pagination, with same filters)
    provider_counts_qs = queryset.values('provider').annotate(
        model_count=Count('id')
    ).order_by('provider')

    # Convert to dict {provider_name: count}
    provider_counts = {
        item['provider']: item['model_count']
        for item in provider_counts_qs
    }

    # Apply pagination on queryset
    page_number = int(query_params.get('page', 1))
    page_size = int(query_params.get('page_size', 20))

    total_count = queryset.count()
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    page_queryset = queryset[start_index:end_index]

    # Serialize the page
    serializer = ModelCatalogSerializer(page_queryset, many=True)
    results = serializer.data

    # Prepend Sterna Auto entry on page 1 (no search/provider filter active)
    if page_number == 1 and not filters.get("search") and not filters.get("provider"):
        sterna_entry = {
            "id": "00000000-0000-0000-0000-000000000001",
            "model_id": "ornithops/sterna",
            "name": "Sterna General v1",
            "provider": "ornithops",
            "provider_icon_slug": "ornithops",
            "provider_icon_url": None,
            "model_icon_slug": "sterna",
            "model_icon_url": None,
            "cost_per_1m_prompt": None,
            "cost_per_1m_completion": None,
            "max_tokens": 1000000,
            "supports_streaming": True,
            "supports_functions": True,
            "supports_structured_outputs": True,
            "supports_reasoning": True,
            "supports_prompt_caching": True,
            "supports_stream_cancellation": True,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "tags": ["auto-routing"],
            "is_available": True,
            "is_new": False,
            "first_seen_at": None,
            "description": "Intelligent router \u2014 automatically selects the best model for each request.",
        }
        results = [sterna_entry] + list(results)
        total_count += 1

    # Build paginated response manually
    response_data = {
        'count': total_count,
        'results': results,
        'provider_counts': provider_counts
    }

    # Cache the response for 5 minutes (300 seconds)
    cache.set(cache_key, response_data, timeout=300)

    return response_data
