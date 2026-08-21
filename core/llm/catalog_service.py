"""
Service for managing OpenRouter model catalog with caching.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from django.db import transaction

from .client import OpenRouterClient
from .models import ModelCatalog
from .constants import MODEL_CATALOG_CACHE_TTL
from .pricing_config import PRICE_STORAGE_UNIT
from .provider_capabilities_service import supports_stream_cancellation

logger = logging.getLogger(__name__)

# Minimum requirements for models to be stored in the catalog
MIN_CONTEXT_WINDOW = 32768

# Pattern to match "openrouter" variations (case-insensitive)
OPENROUTER_PATTERN = re.compile(r'open[-\s]?router', re.IGNORECASE)


def _clean_description(description: str) -> str:
    """
    Remove sentences containing OpenRouter references from description.

    Args:
        description: Raw model description from OpenRouter API

    Returns:
        Cleaned description with OpenRouter-mentioning sentences removed
    """
    if not description:
        return ""

    # Split into sentences (handles . ! ? followed by space or end)
    sentences = re.split(r'(?<=[.!?])\s+', description)

    # Filter out sentences containing openrouter variations
    cleaned_sentences = [
        s for s in sentences
        if not OPENROUTER_PATTERN.search(s)
    ]

    return ' '.join(cleaned_sentences).strip()


def _meets_minimum_requirements(model_data: Dict[str, Any]) -> bool:
    """
    Check if a model meets minimum requirements to be stored in the catalog.

    Requirements:
    - Must support function/tool calling
    - Must have context window >= MIN_CONTEXT_WINDOW (32768 tokens)
    - Must not be an image/audio/free model (no "image", "audio", or ":free" in model ID)
    - Must support vision (image in input_modalities)

    Args:
        model_data: Raw model data from OpenRouter API

    Returns:
        True if model meets requirements, False otherwise
    """
    model_id = model_data.get("id", "").lower()

    # Exclude image, audio, and free models
    if "image" in model_id or "audio" in model_id or ":free" in model_id:
        return False

    # Check context window
    context_length = model_data.get("context_length", 0)
    if context_length < MIN_CONTEXT_WINDOW:
        return False

    # Check function/tool calling support
    supported_params = model_data.get("supported_parameters", [])
    if not supported_params:
        return False

    params_lower = {p.lower() for p in supported_params if isinstance(p, str)}
    function_indicators = {'tools', 'tool_choice', 'parallel_tool_calls', 'functions'}

    if not (params_lower & function_indicators):
        return False

    # Must support vision (image input)
    architecture = model_data.get("architecture", {})
    input_modalities = architecture.get("input_modalities") or []
    if "image" not in input_modalities:
        return False

    return True


def _detect_capabilities(supported_parameters: List[str], pricing: Dict[str, Any], provider: str = "") -> Dict[str, bool]:
    """
    Detect model capabilities from OpenRouter API fields and provider information.

    Args:
        supported_parameters: List of parameter names supported by the model
        pricing: Pricing dictionary from model data
        provider: Provider name (e.g., 'openai', 'anthropic', 'google')
                 Used to determine provider-specific capabilities like stream cancellation

    Returns:
        Dictionary with capability boolean flags:
        - 'streaming': Supports streaming responses (always True - OpenRouter supports streaming for all models)
        - 'functions': Supports function/tool calling
        - 'structured_outputs': Supports structured JSON schema validation
        - 'reasoning': Supports reasoning/thinking tokens
        - 'prompt_caching': Supports prompt caching (detected via pricing fields)
        - 'stream_cancellation': Supports stream cancellation (provider-dependent)

    Note:
        - Streaming is universal for all OpenRouter models
        - Stream cancellation is provider-dependent (fetched dynamically from OpenRouter docs)
        - Prompt caching is detected via 'input_cache_read' or 'input_cache_write' in pricing

    Examples:
        >>> _detect_capabilities(['tools', 'temperature'], {'prompt': '0.000003', 'input_cache_read': '0.0000001'}, 'openai')
        {'streaming': True, 'functions': True, 'structured_outputs': False, 'reasoning': False, 'prompt_caching': True, 'stream_cancellation': True}

        >>> _detect_capabilities(['tools'], {'prompt': '0.00001'}, 'google')
        {'streaming': True, 'functions': True, 'structured_outputs': False, 'reasoning': False, 'prompt_caching': False, 'stream_cancellation': False}
    """
    if not supported_parameters:
        supported_parameters = []

    # Convert to lowercase set for case-insensitive matching
    params_lower = {p.lower() for p in supported_parameters if isinstance(p, str)}

    # Streaming is supported universally by OpenRouter for all models
    # It's a request-level parameter, not a model capability
    supports_streaming = True

    # Detect function/tool calling support
    # Check for 'tools', 'tool_choice', 'parallel_tool_calls', or legacy 'functions'
    function_indicators = {'tools', 'tool_choice', 'parallel_tool_calls', 'functions'}
    supports_functions = bool(params_lower & function_indicators)

    # Detect structured outputs support
    # Check for 'structured_outputs' parameter
    supports_structured_outputs = 'structured_outputs' in params_lower

    # Detect reasoning/thinking tokens support
    # Check for 'reasoning', 'include_reasoning' parameters
    reasoning_indicators = {'reasoning', 'include_reasoning'}
    supports_reasoning = bool(params_lower & reasoning_indicators)

    # Detect prompt caching support
    # Models with cache pricing fields support prompt caching
    # Check for 'input_cache_read' or 'input_cache_write' in pricing dictionary
    supports_prompt_caching = (
        'input_cache_read' in pricing or
        'input_cache_write' in pricing
    )

    # Stream cancellation is provider-dependent
    # Dynamically fetched from OpenRouter documentation and cached in Redis
    # Falls back to JSON config if fetching fails
    supports_stream_cancellation_flag = supports_stream_cancellation(provider)

    return {
        'streaming': supports_streaming,
        'functions': supports_functions,
        'structured_outputs': supports_structured_outputs,
        'reasoning': supports_reasoning,
        'prompt_caching': supports_prompt_caching,
        'stream_cancellation': supports_stream_cancellation_flag
    }


class CatalogService:
    """Service for managing model catalog with caching."""

    CACHE_KEY_PREFIX = "openrouter:catalog:"
    CACHE_KEY_ALL_MODELS = f"{CACHE_KEY_PREFIX}all"
    CACHE_KEY_AVAILABLE_MODELS = f"{CACHE_KEY_PREFIX}available"
    CACHE_KEY_PRICING = f"{CACHE_KEY_PREFIX}pricing"
    CACHE_KEY_COST_PERCENTILES = f"{CACHE_KEY_PREFIX}cost_percentiles"
    CACHE_KEY_LAST_REFRESH = f"{CACHE_KEY_PREFIX}last_refresh"

    def __init__(self, client: Optional[OpenRouterClient] = None):
        """Initialize catalog service."""
        self.client = client or OpenRouterClient()

    def _is_catalog_stale(self) -> bool:
        """
        Check if the catalog data is stale and needs refreshing.

        Returns:
            True if catalog should be refreshed from OpenRouter
        """
        # Check if we have a recent refresh timestamp in cache
        last_refresh = cache.get(self.CACHE_KEY_LAST_REFRESH)
        if last_refresh:
            # Cache key exists, catalog is fresh
            return False

        # No cache key - check database for staleness
        try:
            latest_model = ModelCatalog.objects.order_by('-fetched_at').first()
            if not latest_model or not latest_model.fetched_at:
                # No models or no timestamp - needs refresh
                return True

            # Check if fetched_at is older than TTL
            age = (timezone.now() - latest_model.fetched_at).total_seconds()
            is_stale = age > MODEL_CATALOG_CACHE_TTL

            if is_stale:
                logger.info(f"Catalog is stale (age: {age/3600:.1f}h, TTL: {MODEL_CATALOG_CACHE_TTL/3600:.1f}h)")

            return is_stale
        except Exception as e:
            logger.warning(f"Error checking catalog staleness: {e}")
            return False  # Don't refresh on error

    def fetch_and_cache_models(
        self, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch models from OpenRouter and cache them.

        Args:
            force_refresh: Force refresh even if cache is valid

        Returns:
            List of model dictionaries
        """
        # Check cache first
        if not force_refresh:
            cached_models = cache.get(self.CACHE_KEY_ALL_MODELS)
            if cached_models:
                logger.debug("Using cached model catalog")
                return cached_models

        try:
            # Fetch from OpenRouter API
            logger.info("Fetching model catalog from OpenRouter")
            all_models_data = self.client.list_models()

            # Filter models that meet minimum requirements (tool support, min context window)
            models_data = [m for m in all_models_data if _meets_minimum_requirements(m)]
            skipped_count = len(all_models_data) - len(models_data)
            if skipped_count > 0:
                logger.info(f"Filtered out {skipped_count} models that don't meet minimum requirements (no tool support or context < {MIN_CONTEXT_WINDOW})")

            # Process and store in database
            with transaction.atomic():
                # Clear old entries if force refresh
                if force_refresh:
                    ModelCatalog.objects.all().delete()

                for model_data in models_data:
                    self._update_or_create_model(model_data)

            # Cache the result (only models meeting requirements)
            cache.set(self.CACHE_KEY_ALL_MODELS, models_data, MODEL_CATALOG_CACHE_TTL)

            # Also cache available models separately
            available_models = [
                m for m in models_data if m.get("status") != "unavailable"
            ]
            cache.set(
                self.CACHE_KEY_AVAILABLE_MODELS,
                available_models,
                MODEL_CATALOG_CACHE_TTL,
            )

            # Set last refresh timestamp (used by _is_catalog_stale)
            cache.set(self.CACHE_KEY_LAST_REFRESH, timezone.now().isoformat(), MODEL_CATALOG_CACHE_TTL)

            logger.info(f"Cached {len(models_data)} models (refresh timestamp set)")
            return models_data

        except Exception as e:
            logger.error(f"Failed to fetch model catalog: {e}")
            # Fall back to database if API fails
            return self._get_models_from_db()

    def _update_or_create_model(self, model_data: Dict[str, Any]) -> ModelCatalog:
        """Update or create a model in the database."""
        model_id = model_data.get("id", "")

        # Parse pricing information
        pricing = model_data.get("pricing", {})
        prompt_price = None
        completion_price = None

        if pricing:
            # OpenRouter pricing is per token, convert to storage unit (per 1K tokens)
            prompt_price = Decimal(str(pricing.get("prompt", 0))) * PRICE_STORAGE_UNIT
            completion_price = Decimal(str(pricing.get("completion", 0))) * PRICE_STORAGE_UNIT

        # Extract provider from model ID (format: provider/model-name)
        provider = model_id.split("/")[0] if "/" in model_id else "unknown"

        # Detect capabilities from supported_parameters, pricing, and provider
        supported_params = model_data.get("supported_parameters", [])
        pricing = model_data.get("pricing", {})
        capabilities = _detect_capabilities(supported_params, pricing, provider)

        # Extract architecture details (ensure lists are never None)
        architecture = model_data.get("architecture", {})
        modality = architecture.get("modality")
        input_modalities = architecture.get("input_modalities") or []
        output_modalities = architecture.get("output_modalities") or []
        tokenizer = architecture.get("tokenizer")

        # Extract top_provider details
        top_provider = model_data.get("top_provider", {})
        max_completion_tokens = top_provider.get("max_completion_tokens")
        is_moderated = top_provider.get("is_moderated", False)

        # Extract default_parameters (ensure it's never None)
        default_parameters = model_data.get("default_parameters") or {}

        defaults = {
            "name": model_data.get("name", model_id),
            "provider": provider,
            "prompt_price": prompt_price,
            "completion_price": completion_price,
            "max_tokens": model_data.get("context_length"),
            "supports_streaming": capabilities['streaming'],
            "supports_functions": capabilities['functions'],
            "supports_structured_outputs": capabilities['structured_outputs'],
            "supports_reasoning": capabilities['reasoning'],
            "supports_prompt_caching": capabilities['prompt_caching'],
            "supports_stream_cancellation": capabilities['stream_cancellation'],
            "modality": modality,
            "input_modalities": input_modalities,
            "output_modalities": output_modalities,
            "tokenizer": tokenizer,
            "max_completion_tokens": max_completion_tokens,
            "is_moderated": is_moderated,
            "default_parameters": default_parameters,
            "description": _clean_description(model_data.get("description", "")),
            "tags": model_data.get("tags", []),
            "is_available": model_data.get("status") != "unavailable",
            "fetched_at": timezone.now(),
        }

        model, created = ModelCatalog.objects.update_or_create(
            model_id=model_id,
            defaults=defaults,
        )

        # Only set first_seen_at for newly created models (not on updates)
        if created:
            model.first_seen_at = timezone.now()
            model.save(update_fields=["first_seen_at"])

        action = "Created (NEW)" if created else "Updated"
        logger.debug(f"{action} model: {model_id}")
        return model

    def _get_models_from_db(self) -> List[Dict[str, Any]]:
        """Get models from database as fallback."""
        models = ModelCatalog.objects.filter(is_available=True).values()
        return list(models)

    def ensure_catalog_populated(self, auto_refresh: bool = True) -> bool:
        """
        Ensure the model catalog is populated and fresh.
        Fetches from OpenRouter if the catalog is empty or stale.

        Args:
            auto_refresh: If True, automatically refresh stale catalogs (default: True)

        Returns:
            True if catalog has models, False if fetching failed
        """
        has_models = ModelCatalog.objects.exists()

        # Check if catalog is stale and needs refresh
        if has_models and auto_refresh and self._is_catalog_stale():
            logger.info("Catalog is stale, auto-refreshing from OpenRouter")
            try:
                models = self.fetch_and_cache_models(force_refresh=True)
                if models:
                    logger.info(f"Auto-refresh complete: {len(models)} models updated")
                    return True
            except Exception as e:
                logger.warning(f"Auto-refresh failed, using existing data: {e}")
                # Continue with existing data if refresh fails
                return True

        # If we have models (fresh or refresh failed), we're good
        if has_models:
            return True

        # Check cache
        cached_models = cache.get(self.CACHE_KEY_ALL_MODELS)
        if cached_models:
            return True

        # Check if API key is configured
        try:
            # This will raise ValueError if API key is not set
            OpenRouterClient()
        except ValueError as e:
            logger.warning(f"OpenRouter API key not configured: {e}")
            return False

        # Catalog is empty, fetch from OpenRouter
        try:
            logger.info("Catalog is empty, fetching from OpenRouter")
            models = self.fetch_and_cache_models(force_refresh=True)
            return len(models) > 0
        except Exception as e:
            logger.error(f"Failed to populate catalog: {e}")
            return False

    def get_all_models_smart(self) -> List[ModelCatalog]:
        """
        Get all models, automatically fetching from OpenRouter if needed.

        Returns:
            QuerySet of all available models
        """
        # Ensure catalog is populated
        self.ensure_catalog_populated()

        # Return models from database
        return ModelCatalog.objects.filter(is_available=True)

    def get_available_models(
        self, provider: Optional[str] = None, tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get available models with optional filtering.

        Args:
            provider: Filter by provider (e.g., 'openai', 'anthropic')
            tags: Filter by tags

        Returns:
            List of available models
        """
        # Try cache first
        cache_key = self.CACHE_KEY_AVAILABLE_MODELS
        if provider:
            cache_key = f"{cache_key}:{provider}"

        cached_models = cache.get(cache_key)
        if cached_models and not tags:  # Tag filtering not cached
            return cached_models

        # Ensure catalog is populated
        self.ensure_catalog_populated()

        # Query database
        queryset = ModelCatalog.objects.filter(is_available=True)

        if provider:
            queryset = queryset.filter(provider__iexact=provider)

        models = []
        for model in queryset:
            model_dict = {
                "id": model.model_id,
                "name": model.name,
                "provider": model.provider,
                "prompt_price": float(model.prompt_price)
                if model.prompt_price
                else None,
                "completion_price": float(model.completion_price)
                if model.completion_price
                else None,
                "max_tokens": model.max_tokens,
                "supports_streaming": model.supports_streaming,
                "supports_functions": model.supports_functions,
                "description": model.description,
                "tags": model.tags,
            }

            # Filter by tags if specified
            if tags:
                model_tags = set(model.tags)
                if not model_tags.intersection(set(tags)):
                    continue

            models.append(model_dict)

        # Cache if no tag filtering
        if not tags:
            cache.set(cache_key, models, MODEL_CATALOG_CACHE_TTL)

        return models

    def check_model_availability(self, model_id: str) -> bool:
        """
        Check if a specific model is available.

        Args:
            model_id: Model identifier (e.g., 'openai/gpt-4', can include :thinking:online suffixes)

        Returns:
            True if model is available
        """
        # Strip OpenRouter suffixes for catalog lookup
        base_model_id = model_id.split(':')[0] if ':' in model_id else model_id

        try:
            ModelCatalog.objects.get(model_id=base_model_id, is_available=True)
            return True
        except ModelCatalog.DoesNotExist:
            # Try fetching fresh catalog
            self.fetch_and_cache_models()

            # Check again
            return ModelCatalog.objects.filter(
                model_id=base_model_id, is_available=True
            ).exists()

    def get_model_pricing(self, model_id: str) -> Dict[str, Optional[float]]:
        """
        Get pricing information for a model.

        Args:
            model_id: Model identifier (can include OpenRouter suffixes like :thinking:online)

        Returns:
            Dictionary with prompt_price and completion_price
        """
        cache_key = f"{self.CACHE_KEY_PRICING}:{model_id}"

        # Check cache
        cached_pricing = cache.get(cache_key)
        if cached_pricing:
            return cached_pricing

        # Strip OpenRouter suffixes (:thinking, :online, :free, :extended, etc.)
        # These are routing modifiers but pricing is based on the base model
        base_model_id = model_id.split(':')[0] if ':' in model_id else model_id

        logger.info(f"[PRICING] Looking up pricing for model_id='{model_id}' (base='{base_model_id}')")

        try:
            model = ModelCatalog.objects.get(model_id=base_model_id)
            pricing = {
                "prompt_price": float(model.prompt_price)
                if model.prompt_price is not None
                else None,
                "completion_price": float(model.completion_price)
                if model.completion_price is not None
                else None,
            }

            logger.info(f"[PRICING] Found pricing - Prompt: {pricing['prompt_price']}, Completion: {pricing['completion_price']}")

            # Cache the pricing
            cache.set(cache_key, pricing, MODEL_CATALOG_CACHE_TTL)
            return pricing

        except ModelCatalog.DoesNotExist:
            logger.warning(f"[PRICING] Model not found in catalog: {base_model_id}")
            # Return None prices if model not found
            return {"prompt_price": None, "completion_price": None}

    def estimate_cost(
        self, model_id: str, prompt_tokens: int, completion_tokens: int
    ) -> Decimal:
        """
        Estimate cost for a completion.

        Args:
            model_id: Model identifier
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD
        """
        costs = self.estimate_cost_detailed(model_id, prompt_tokens, completion_tokens)
        return costs["total_cost"]

    def estimate_cost_detailed(
        self, model_id: str, prompt_tokens: int, completion_tokens: int
    ) -> Dict[str, Decimal]:
        """
        Estimate cost for a completion with detailed breakdown.

        Args:
            model_id: Model identifier
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Dictionary with prompt_cost, completion_cost, and total_cost
        """
        pricing = self.get_model_pricing(model_id)

        if pricing["prompt_price"] is None or pricing["completion_price"] is None:
            # Use default estimates if pricing not available
            logger.warning(f"No pricing data for {model_id}, using defaults")
            prompt_price = 0.01  # $0.01 per 1k tokens default
            completion_price = 0.02  # $0.02 per 1k tokens default
        else:
            prompt_price = pricing["prompt_price"]
            completion_price = pricing["completion_price"]

        # Calculate cost (prices are per storage unit)
        # Use quantize to avoid floating point precision issues
        prompt_cost = Decimal(str(prompt_tokens * prompt_price / PRICE_STORAGE_UNIT)).quantize(
            Decimal("0.00000001")
        )
        completion_cost = Decimal(str(completion_tokens * completion_price / PRICE_STORAGE_UNIT)).quantize(
            Decimal("0.00000001")
        )

        return {
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "total_cost": prompt_cost + completion_cost,
        }

    def get_models_by_tier(self, tier: str) -> List[str]:
        """
        Get model IDs for a specific tier.

        Args:
            tier: Tier name (budget, balanced, quality)

        Returns:
            List of model IDs
        """
        from .constants import MODEL_TIERS

        if tier not in MODEL_TIERS:
            return []

        tier_models = MODEL_TIERS[tier]["models"]

        # Verify models are available
        available_models = []
        for model_id in tier_models:
            if self.check_model_availability(model_id):
                available_models.append(model_id)

        return available_models

    def refresh_catalog(self) -> Dict[str, Any]:
        """
        Force refresh the model catalog.

        Returns:
            Summary of refresh operation
        """
        try:
            models = self.fetch_and_cache_models(force_refresh=True)

            # Count by provider
            provider_counts = {}
            for model in models:
                provider = model.get("id", "").split("/")[0]
                provider_counts[provider] = provider_counts.get(provider, 0) + 1

            return {
                "success": True,
                "total_models": len(models),
                "providers": provider_counts,
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to refresh catalog: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": timezone.now().isoformat(),
            }

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information for a specific model by ID.

        Args:
            model_id: The model identifier (can include :thinking:online suffixes)

        Returns:
            Dictionary with model information or None if not found
        """
        # Try cache first
        cache_key = f"{self.CACHE_KEY_PREFIX}model:{model_id}"
        cached_model = cache.get(cache_key)
        if cached_model:
            return cached_model

        # Strip OpenRouter suffixes for catalog lookup
        base_model_id = model_id.split(':')[0] if ':' in model_id else model_id

        # Query database
        try:
            model = ModelCatalog.objects.get(model_id=base_model_id)
            model_info = {
                "id": model.model_id,
                "name": model.name,
                "provider": model.provider,
                "description": model.description,
                "prompt_price": float(model.prompt_price)
                if model.prompt_price
                else None,
                "completion_price": float(model.completion_price)
                if model.completion_price
                else None,
                "max_tokens": model.max_tokens,
                "supports_streaming": model.supports_streaming,
                "supports_functions": model.supports_functions,
                "tags": model.tags,
                "is_available": model.is_available,
                "output_modalities": model.output_modalities or [],
                "input_modalities": model.input_modalities or [],
            }

            # Cache for shorter duration
            cache.set(cache_key, model_info, 3600)  # 1 hour cache
            return model_info
        except ModelCatalog.DoesNotExist:
            logger.debug(f"Model {base_model_id} not found in catalog")
            # Return basic info for fallback
            return {
                "id": model_id,
                "name": model_id,  # Use ID as name if not found
                "provider": "unknown",
                "is_available": True,
            }

    def get_cost_percentiles(self) -> Dict[str, float]:
        """
        Calculate cost percentiles for available paid models.

        Returns:
            Dictionary with p10, p40, p70, p95, p99 percentiles
        """
        # Check cache first
        cached_percentiles = cache.get(self.CACHE_KEY_COST_PERCENTILES)
        if cached_percentiles:
            logger.debug("Using cached cost percentiles")
            return cached_percentiles

        # Get all paid models (excluding free models)
        paid_models = ModelCatalog.objects.filter(
            is_available=True,
            prompt_price__gt=0
        ).values_list('prompt_price', flat=True)

        percentiles = {}
        if paid_models:
            # Convert to sorted list of floats
            costs = sorted([float(cost) for cost in paid_models if cost])

            def calculate_percentile(data: List[float], percentile: int) -> float:
                """Calculate percentile with linear interpolation."""
                if not data:
                    return 0
                index = (percentile / 100) * (len(data) - 1)
                lower = int(index)
                upper = min(lower + 1, len(data) - 1)
                weight = index - lower

                if lower == upper:
                    return data[lower]
                return data[lower] * (1 - weight) + data[upper] * weight

            percentiles = {
                "p10": calculate_percentile(costs, 10),
                "p40": calculate_percentile(costs, 40),
                "p70": calculate_percentile(costs, 70),
                "p95": calculate_percentile(costs, 95),
                "p99": calculate_percentile(costs, 99)
            }

            # Cache for 1 hour (costs don't change frequently)
            cache.set(self.CACHE_KEY_COST_PERCENTILES, percentiles, 3600)

        return percentiles
