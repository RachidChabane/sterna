"""
API views for LLM module.
"""

import logging
import hashlib
import json
import os
from typing import Any, Dict, Optional

import httpx as httpx_sync

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import models
from django.db.models import F, ExpressionWrapper, FloatField, Case, When, IntegerField, Q, Count
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.utils.decorators import method_decorator

from exceptions import apply_ratelimit

from .models import ModelCatalog, ImageModelCatalog
from .client import OpenRouterClient
from .catalog_service import CatalogService
from .rate_limiter import RateLimiter
from .utils import exclude_blacklisted_providers, is_provider_blacklisted
from .icon_config import PROVIDER_ICON_MAPPINGS, KNOWN_LOBEHUB_ICONS
from .exceptions import ContextLimitExceededException
from .error_messages import error_payload, get_user_friendly_error
from .serializers import (
    ModelCatalogSerializer,
    ModelAvailabilitySerializer,
    CompletionRequestSerializer,
    CompletionResponseSerializer,
    FallbackCompletionRequestSerializer,
    CostEstimateRequestSerializer,
    CostEstimateResponseSerializer,
    BatchCostEstimateRequestSerializer,
    BatchCostEstimateResponseSerializer,
    RateLimitInfoSerializer,
    CatalogRefreshResponseSerializer,
    ModelTierSerializer,
    ModelFilterSerializer,
    UsageStatsSerializer,
    ModelComparisonRequestSerializer,
    ImageModelCatalogSerializer,
    ImageModelFilterSerializer,
)
from .constants import MODEL_TIERS
from .icon_utils import get_provider_icon_slug, get_model_icon_slug
from .comparison_service import ModelComparisonService
from .comparison_config import ComparisonConstraints, ComparisonPriorities, CapabilityWeights
from .file_tools_integration import (
    should_enable_file_tools,
    get_file_tools,
    handle_file_tool_calls
)

logger = logging.getLogger(__name__)


# ===========================
# User Instructions Helper
# ===========================

# Preference keys matching frontend settingsStore.ts
USER_INSTRUCTIONS_PREFERENCE_KEYS = {
    'ENABLED': 'settings.instructions.enabled',
    'CONTENT': 'settings.instructions.content',
}

USER_PREFERENCES_SERVICE_URL = os.environ.get(
    "USER_PREFERENCES_SERVICE_URL",
    "http://user-preferences:8000"
)


def get_user_instructions(user_id: str, auth_token: str) -> dict:
    """
    Fetch global user instructions settings from the user-preferences service.

    Returns:
        dict with keys: enabled (bool), content (str)
        Returns defaults if fetch fails or instructions are not set.
    """
    import httpx

    defaults = {
        'enabled': False,
        'content': '',
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            # Fetch all settings-category preferences at once
            response = client.get(
                f"{USER_PREFERENCES_SERVICE_URL}/api/v1/preferences",
                params={'category': 'settings'},
                headers={'Authorization': f'Bearer {auth_token}'} if auth_token else {}
            )

            if response.status_code != 200:
                logger.debug(f"[UserInstructions] Failed to fetch preferences: {response.status_code}")
                return defaults

            data = response.json()
            prefs = data.get('preferences', {})

            # Extract instruction settings
            enabled = prefs.get(USER_INSTRUCTIONS_PREFERENCE_KEYS['ENABLED'], False)
            content = prefs.get(USER_INSTRUCTIONS_PREFERENCE_KEYS['CONTENT'], '')

            return {
                'enabled': bool(enabled),
                'content': content if isinstance(content, str) else '',
            }

    except Exception as e:
        logger.warning(f"[UserInstructions] Error fetching user instructions: {e}")
        return defaults


def get_chat_instructions(chat_id: str, user_id: str) -> dict:
    """
    Fetch chat-specific instructions from the database.

    Returns:
        dict with keys: content (str), mode (str: 'append'|'override')
        Returns empty dict if chat not found or has no instructions.
    """
    from conversations.models import Chat

    defaults = {
        'content': '',
        'mode': 'append',
    }

    if not chat_id:
        return defaults

    try:
        chat = Chat.objects.filter(
            id=chat_id,
            conversation__user_id=user_id
        ).first()

        if not chat or not chat.instructions:
            return defaults

        instructions = chat.instructions
        return {
            'content': instructions.get('content', ''),
            'mode': instructions.get('mode', 'append'),
        }

    except Exception as e:
        logger.warning(f"[ChatInstructions] Error fetching chat instructions: {e}")
        return defaults


class ModelCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for OpenRouter model catalog.

    Provides endpoints for:
    - Listing available models
    - Checking model availability
    - Refreshing catalog
    - Getting model tiers
    """

    queryset = exclude_blacklisted_providers(ModelCatalog.objects.filter(is_available=True))
    serializer_class = ModelCatalogSerializer
    permission_classes = [AllowAny]  # Models list is public information

    def list(self, request):
        """
        List available models with optional filtering.

        Performance: Results are cached in Redis for 5 minutes.
        Cache key includes all filter parameters for correct invalidation.
        """
        filter_serializer = ModelFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        # Build cache key based on all filter parameters
        cache_key_data = {
            'filters': filters,
            'page': request.query_params.get('page', 1),
            'page_size': request.query_params.get('page_size', 25)
        }
        cache_key_hash = hashlib.md5(
            json.dumps(cache_key_data, sort_keys=True).encode()
        ).hexdigest()
        cache_key = f"models:list:{cache_key_hash}"

        # Try to get cached response
        cached_response = cache.get(cache_key)
        if cached_response is not None:
            logger.debug(f"Cache HIT for models list: {cache_key}")
            return Response(cached_response)

        logger.debug(f"Cache MISS for models list: {cache_key}")

        # Use CatalogService to ensure models are populated from OpenRouter
        catalog = CatalogService()

        try:
            # This will auto-fetch from OpenRouter if the catalog is empty
            queryset = catalog.get_all_models_smart()
        except Exception as e:
            logger.warning(f"Failed to fetch models from OpenRouter: {e}")
            # Fall back to whatever is in the database
            queryset = self.get_queryset()

            # If database is also empty, return empty list with a message
            if not queryset.exists():
                return Response({
                    "results": [],
                    "message": "Model catalog is empty. Please check your OpenRouter API key configuration."
                })

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
        if "supports_functions" in request.query_params:
            queryset = queryset.filter(supports_functions=filters["supports_functions"])

        # Only filter by supports_streaming if explicitly provided in request
        if "supports_streaming" in request.query_params:
            queryset = queryset.filter(supports_streaming=filters["supports_streaming"])

        # Only filter by supports_structured_outputs if explicitly provided in request
        if "supports_structured_outputs" in request.query_params:
            queryset = queryset.filter(supports_structured_outputs=filters["supports_structured_outputs"])

        # Only filter by supports_reasoning if explicitly provided in request
        if "supports_reasoning" in request.query_params:
            queryset = queryset.filter(supports_reasoning=filters["supports_reasoning"])

        # Only filter by supports_prompt_caching if explicitly provided in request
        if "supports_prompt_caching" in request.query_params:
            queryset = queryset.filter(supports_prompt_caching=filters["supports_prompt_caching"])

        # Only filter by supports_stream_cancellation if explicitly provided in request
        if "supports_stream_cancellation" in request.query_params:
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
            # Build Q objects for providers with icons
            providers_with_icons = set(PROVIDER_ICON_MAPPINGS.keys()) | KNOWN_LOBEHUB_ICONS
            provider_icon_conditions = Q()
            for provider in providers_with_icons:
                provider_icon_conditions |= Q(provider__iexact=provider)

            # Model-specific icon keywords (from icon_utils.get_model_icon_slug)
            model_icon_keywords = [
                "claude", "gemini", "mistral", "deepseek", "qwen", "yi",
                "command", "grok", "palm", "bard", "phi", "wizardlm",
                "orca", "falcon", "nova", "baichuan", "chatglm", "glm"
            ]
            model_icon_conditions = Q()
            for keyword in model_icon_keywords:
                model_icon_conditions |= Q(model_id__icontains=keyword)

            # Keep models that have either provider icon OR model-specific icon
            queryset = queryset.filter(provider_icon_conditions | model_icon_conditions)

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
            # Get list of providers with icons (lowercase for case-insensitive matching)
            providers_with_icons = set(PROVIDER_ICON_MAPPINGS.keys()) | KNOWN_LOBEHUB_ICONS

            # Create Q objects for case-insensitive matching
            icon_conditions = Q()
            for provider in providers_with_icons:
                icon_conditions |= Q(provider__iexact=provider)

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
        page_number = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        total_count = queryset.count()
        start_index = (page_number - 1) * page_size
        end_index = start_index + page_size
        page_queryset = queryset[start_index:end_index]

        # Serialize the page
        serializer = self.get_serializer(page_queryset, many=True)
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

        return Response(response_data)

    @action(detail=False, methods=["post"], url_path="compare")
    def compare(self, request):
        """
        Compare selected models with priorities and constraints on the backend.

        Body:
        - model_ids: [string]
        - priorities: { cost, context, capabilities, multimodality, availability }
        - constraints: must-have toggles + thresholds
        - costDirection: 'lower' | 'higher'
        - capabilityWeights: optional weights per capability
        """
        serializer = ModelComparisonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Fetch models
        model_ids = data["model_ids"]
        models_qs = ModelCatalog.objects.filter(model_id__in=model_ids)
        models = list(models_qs)

        # Build priorities
        prio_data = data.get("priorities") or {}
        priorities = ComparisonPriorities(
            cost=prio_data.get("cost", "important"),
            context=prio_data.get("context", "important"),
            capabilities=prio_data.get("capabilities", "important"),
            multimodality=prio_data.get("multimodality", "nice"),
            availability=prio_data.get("availability", "nice"),
        )

        # Build constraints
        cons_data = data.get("constraints") or {}
        constraints = ComparisonConstraints(
            must_support_functions=cons_data.get("mustSupportFunctions", False),
            must_support_structured_outputs=cons_data.get("mustSupportStructuredOutputs", False),
            must_support_reasoning=cons_data.get("mustSupportReasoning", False),
            must_support_prompt_caching=cons_data.get("mustSupportPromptCaching", False),
            must_support_stream_cancellation=cons_data.get("mustSupportStreamCancellation", False),
            must_be_available=cons_data.get("mustBeAvailable", False),
            must_be_multimodal=cons_data.get("mustBeMultimodal", False),
            min_context_tokens=cons_data.get("minContextTokens"),
            max_cost_per_1m_tokens=cons_data.get("maxCostPer1MTokens"),
        )

        cost_direction = data.get("costDirection") or "lower"
        cw_data = data.get("capabilityWeights") or {}
        cw = CapabilityWeights(**cw_data)

        service = ModelComparisonService()
        result = service.compare_with_options(
            models=models,
            priorities=priorities,
            constraints=constraints,
            capability_weights=cw,
            cost_direction=cost_direction,
        )

        # Return in the expected format
        return Response({
            "scores": [s.to_dict() for s in result.scores],
            "best_model_id": result.best_model.id if result.best_model else None,
            "considered": result.total_compared,
        })

    @action(detail=False, methods=["post"])
    def check_availability(self, request):
        """Check if a specific model is available."""
        serializer = ModelAvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        model_id = serializer.validated_data["model_id"]
        catalog = CatalogService()

        is_available = catalog.check_model_availability(model_id)

        # Strip OpenRouter suffixes for catalog lookup
        base_model_id = model_id.split(':')[0] if ':' in model_id else model_id

        # Check if model provider is blacklisted - return as unavailable for frontend
        if is_available:
            try:
                model = ModelCatalog.objects.get(model_id=base_model_id)
                if is_provider_blacklisted(model.provider):
                    is_available = False
            except ModelCatalog.DoesNotExist:
                pass

        response_data = {"model_id": model_id, "is_available": is_available}

        if is_available:
            try:
                model = ModelCatalog.objects.get(model_id=base_model_id)
                response_data.update(
                    {
                        "provider": model.provider,
                        "max_tokens": model.max_tokens,
                        "pricing": {
                            "prompt_per_1k": float(model.prompt_price)
                            if model.prompt_price
                            else None,
                            "completion_per_1k": float(model.completion_price)
                            if model.completion_price
                            else None,
                        },
                    }
                )
            except ModelCatalog.DoesNotExist:
                pass

        return Response(response_data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def refresh(self, request):
        """
        Refresh the model catalog from OpenRouter.

        Performance: Invalidates all model list caches after refresh.
        """
        catalog = CatalogService()
        result = catalog.refresh_catalog()

        # Invalidate all cached model lists after refresh
        try:
            cache.delete_pattern("models:list:*")
        except AttributeError:
            # Cache backend without pattern deletion (e.g. LocMemCache in tests)
            cache.clear()
        logger.info("Invalidated cached model list entries after catalog refresh")

        serializer = CatalogRefreshResponseSerializer(data=result)
        serializer.is_valid(raise_exception=True)

        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get model catalog statistics including cost percentiles."""
        catalog = CatalogService()
        catalog.ensure_catalog_populated()

        # Get base queryset (exclude blacklisted providers)
        base_queryset = exclude_blacklisted_providers(ModelCatalog.objects)

        # Apply has_icon filter (same as list endpoint) to only count models with icons
        providers_with_icons = set(PROVIDER_ICON_MAPPINGS.keys()) | KNOWN_LOBEHUB_ICONS
        provider_icon_conditions = Q()
        for provider in providers_with_icons:
            provider_icon_conditions |= Q(provider__iexact=provider)

        # Model-specific icon keywords (from icon_utils.get_model_icon_slug)
        model_icon_keywords = [
            "claude", "gemini", "mistral", "deepseek", "qwen", "yi",
            "command", "grok", "palm", "bard", "phi", "wizardlm",
            "orca", "falcon", "nova", "baichuan", "chatglm", "glm"
        ]
        model_icon_conditions = Q()
        for keyword in model_icon_keywords:
            model_icon_conditions |= Q(model_id__icontains=keyword)

        # Filter to models with icons
        icon_queryset = base_queryset.filter(provider_icon_conditions | model_icon_conditions)

        # Get counts
        total_models = icon_queryset.count()
        available_models = icon_queryset.filter(is_available=True).count()

        # Get unique providers (only from models with icons)
        providers = icon_queryset.values_list('provider', flat=True).distinct()
        unique_providers = list(set(providers))

        # Get cost percentiles from catalog service (cached)
        cost_percentiles = catalog.get_cost_percentiles()

        return Response({
            "total_models": total_models,
            "available_models": available_models,
            "total_providers": len(unique_providers),
            "providers_list": sorted(unique_providers),
            "cost_percentiles": cost_percentiles
        })

    @action(detail=False, methods=["get"])
    def tiers(self, request):
        """Get available model tiers with their models."""
        catalog = CatalogService()
        tiers_data = []

        for tier_name, tier_config in MODEL_TIERS.items():
            available_models = catalog.get_models_by_tier(tier_name)

            # Filter out blacklisted provider models
            filtered_models = []
            for model_id in available_models:
                try:
                    # Strip suffixes just in case
                    base_model_id = model_id.split(':')[0] if ':' in model_id else model_id
                    model = ModelCatalog.objects.get(model_id=base_model_id)
                    if not is_provider_blacklisted(model.provider):
                        filtered_models.append(model_id)
                except ModelCatalog.DoesNotExist:
                    continue

            tier_data = {
                "tier": tier_name,
                "models": filtered_models,
                "cost_estimate": tier_config["cost_estimate"],
                "available_count": len(filtered_models),
            }

            tiers_data.append(tier_data)

        serializer = ModelTierSerializer(tiers_data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated], url_path='test-connection')
    @method_decorator(
        # Bare @apply_ratelimit breaks on the (self, request) signature of
        # viewset actions — method_decorator adapts it (see memory note).
        apply_ratelimit(
            key="user_or_ip",
            rate="10/h",
            method="POST",
            group="llm-test-connection",
            scope="llm.models.test-connection",
        ),
    )
    def test_connection(self, request):
        """Test OpenRouter API connection with provided API key.

        Authenticated-only: this dispatches a real (1-token) completion
        against the supplied key. The onboarding ApiKeyStep runs post-login
        (it immediately saves the key to /settings/openrouter/, an
        authenticated endpoint), so there is no anonymous flow to preserve.
        Rate-limited to blunt use as a stolen-key validation oracle.
        """
        api_key = request.data.get("api_key")
        logger.info(
            "llm.test_connection_attempt",
            extra={"user_id": str(request.user.id)},
        )

        if not api_key:
            return Response(
                {"success": False, "error": "API key is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Test by making an actual authenticated completion request
            # This will fail with invalid API keys, unlike list_models which is public
            client = OpenRouterClient(api_key=api_key)

            # Make a minimal test completion with cheapest model and 1 token
            client.complete(
                model="openrouter/auto",  # Auto-select cheapest available model
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,  # Minimal tokens to reduce cost
                temperature=0
            )

            # If we got here, the API key is valid
            logger.info("OpenRouter API key validated successfully")

            # Also fetch models count for informational purposes
            try:
                models = client.list_models()
                models_count = len(models) if models else 0
            except Exception:
                models_count = 0

            return Response({
                "success": True,
                "message": "Connection successful - API key is valid",
                "models_count": models_count
            })

        except ValueError as e:
            # Invalid API key format
            logger.warning(f"Invalid API key format: {e}")
            return Response({
                "success": False,
                "error": "Invalid API key format. Please check your API key."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Check for authentication errors in the error message
            error_str = str(e).lower()
            if "unauthorized" in error_str or "401" in error_str or "invalid" in error_str:
                logger.warning(f"Invalid API key attempted: {e}")
                return Response({
                    "success": False,
                    "error": "Invalid API key. Please check your API key and try again."
                }, status=status.HTTP_401_UNAUTHORIZED)
            else:
                # Other API errors
                logger.error(f"API key connection test failed: {e}")
                return Response({
                    "success": False,
                    "error": "Connection failed. Please try again."
                }, status=status.HTTP_400_BAD_REQUEST)


class ImageModelCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for image generation model catalog.

    Provides endpoints for:
    - Listing available image models
    - Getting image model details
    - Refreshing catalog from image-generation service
    """

    queryset = ImageModelCatalog.objects.filter(is_available=True)
    serializer_class = ImageModelCatalogSerializer
    permission_classes = [AllowAny]  # Models list is public information

    def list(self, request):
        """
        List available image models with optional filtering.

        Performance: Results are cached in Redis for 5 minutes.
        """
        filter_serializer = ImageModelFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        # Build cache key based on all filter parameters
        cache_key_data = {
            'filters': filters,
            'page': request.query_params.get('page', 1),
            'page_size': request.query_params.get('page_size', 25)
        }
        cache_key_hash = hashlib.md5(
            json.dumps(cache_key_data, sort_keys=True).encode()
        ).hexdigest()
        cache_key = f"image_models:list:{cache_key_hash}"

        # Try to get cached response
        cached_response = cache.get(cache_key)
        if cached_response is not None:
            logger.debug(f"Cache HIT for image models list: {cache_key}")
            return Response(cached_response)

        logger.debug(f"Cache MISS for image models list: {cache_key}")

        # Try to fetch from image-generation service if catalog is empty
        queryset = self.get_queryset()
        if not queryset.exists():
            self._populate_from_service()
            queryset = self.get_queryset()

        # Apply filters
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

        if "supports_editing" in request.query_params:
            queryset = queryset.filter(supports_editing=filters["supports_editing"])

        if "supports_variations" in request.query_params:
            queryset = queryset.filter(supports_variations=filters["supports_variations"])

        if "best_for_text" in request.query_params:
            queryset = queryset.filter(best_for_text=filters["best_for_text"])

        if "best_for_photorealism" in request.query_params:
            queryset = queryset.filter(best_for_photorealism=filters["best_for_photorealism"])

        if "is_fast" in request.query_params:
            queryset = queryset.filter(is_fast=filters["is_fast"])

        if filters.get("max_price"):
            queryset = queryset.filter(price_per_image__lte=filters["max_price"])

        # Apply sorting
        sort_by = filters.get("sort_by", "none")
        order = filters.get("order", "asc")
        order_prefix = "" if order == "asc" else "-"

        if sort_by == "price":
            queryset = queryset.order_by(f"{order_prefix}price_per_image")
        elif sort_by == "name":
            queryset = queryset.order_by(f"{order_prefix}name")
        elif sort_by == "provider":
            queryset = queryset.order_by(f"{order_prefix}provider", "name")

        # Serialize the results
        serializer = ImageModelCatalogSerializer(queryset, many=True)
        response_data = {
            "count": queryset.count(),
            "results": serializer.data
        }

        # Cache for 5 minutes
        cache.set(cache_key, response_data, timeout=300)

        return Response(response_data)

    def _populate_from_service(self):
        """Fetch models from image-generation service and populate catalog."""
        import httpx

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get("http://image-generation:8006/models")
                response.raise_for_status()
                data = response.json()

                for model_info in data.get("models", []):
                    ImageModelCatalog.objects.update_or_create(
                        model_id=model_info["id"],
                        defaults={
                            "name": model_info.get("name", model_info["id"]),
                            "provider": model_info.get("provider", "unknown"),
                            "price_per_image": model_info.get("base_price"),
                            "supports_generation": model_info.get("supports_generation", True),
                            "supports_editing": model_info.get("supports_editing", False),
                            "supports_variations": model_info.get("supports_variations", False),
                            "supported_sizes": model_info.get("supported_sizes", []),
                            "max_images_per_request": model_info.get("max_images", 1),
                            "is_available": True,
                            "description": model_info.get("description", ""),
                        }
                    )
                logger.info(f"[ImageModels] Populated {len(data.get('models', []))} models from service")
        except Exception as e:
            logger.warning(f"[ImageModels] Failed to populate from service: {e}")
            # Populate with hardcoded defaults if service is unavailable
            self._populate_defaults()

    def _populate_defaults(self):
        """Populate with default image models."""
        from django.utils import timezone

        default_models = [
            {
                "model_id": "openai/dall-e-3",
                "name": "DALL-E 3",
                "provider": "openai",
                "price_per_image": 0.040,
                "supports_generation": True,
                "supports_editing": False,
                "supports_variations": False,
                "supported_sizes": ["1024x1024", "1792x1024", "1024x1792"],
                "supported_qualities": ["standard", "hd"],
                "supported_styles": ["vivid", "natural"],
                "max_images_per_request": 1,
                "description": "Most capable DALL-E model with excellent prompt following",
                "best_for_photorealism": True,
                "best_for_illustration": True,
            },
            {
                "model_id": "openai/dall-e-2",
                "name": "DALL-E 2",
                "provider": "openai",
                "price_per_image": 0.020,
                "supports_generation": True,
                "supports_editing": True,
                "supports_variations": True,
                "supported_sizes": ["256x256", "512x512", "1024x1024"],
                "max_images_per_request": 10,
                "description": "Fast and affordable, supports editing and variations",
            },
            {
                "model_id": "openai/gpt-image-1",
                "name": "GPT Image 1",
                "provider": "openai",
                "price_per_image": 0.011,
                "supports_generation": True,
                "supports_editing": True,
                "supported_sizes": ["1024x1024", "1536x1024", "1024x1536"],
                "supported_qualities": ["low", "medium", "high"],
                "max_images_per_request": 1,
                "description": "Native GPT-4 image generation with transparent background support",
            },
            {
                "model_id": "bfl/flux-1.1-pro",
                "name": "FLUX 1.1 Pro",
                "provider": "bfl",
                "price_per_image": 0.040,
                "supports_generation": True,
                "supported_sizes": ["1024x1024"],
                "max_images_per_request": 1,
                "description": "State-of-the-art image quality from Black Forest Labs",
                "best_for_photorealism": True,
            },
            {
                "model_id": "bfl/flux-pro-ultra",
                "name": "FLUX Pro Ultra",
                "provider": "bfl",
                "price_per_image": 0.060,
                "supports_generation": True,
                "supported_sizes": ["up to 4MP"],
                "max_images_per_request": 1,
                "description": "Ultra high resolution up to 4 megapixels",
            },
            {
                "model_id": "bfl/flux-schnell",
                "name": "FLUX Schnell",
                "provider": "bfl",
                "price_per_image": 0.003,
                "supports_generation": True,
                "max_images_per_request": 1,
                "description": "Fast generation at lower cost",
                "is_fast": True,
            },
            {
                "model_id": "stability/stable-image-ultra",
                "name": "Stable Image Ultra",
                "provider": "stability",
                "price_per_image": 0.080,
                "supports_generation": True,
                "supported_aspect_ratios": ["1:1", "16:9", "21:9", "3:2", "2:3", "4:5", "5:4", "9:16", "9:21"],
                "max_images_per_request": 1,
                "description": "Stability AI's most advanced model",
                "best_for_photorealism": True,
            },
            {
                "model_id": "stability/stable-image-core",
                "name": "Stable Image Core",
                "provider": "stability",
                "price_per_image": 0.030,
                "supports_generation": True,
                "max_images_per_request": 1,
                "description": "Balanced quality and speed",
            },
            {
                "model_id": "ideogram/v2",
                "name": "Ideogram V2",
                "provider": "ideogram",
                "price_per_image": 0.080,
                "supports_generation": True,
                "max_images_per_request": 1,
                "description": "Excellent text rendering in images",
                "best_for_text": True,
            },
            {
                "model_id": "ideogram/v2-turbo",
                "name": "Ideogram V2 Turbo",
                "provider": "ideogram",
                "price_per_image": 0.050,
                "supports_generation": True,
                "max_images_per_request": 1,
                "description": "Fast version with good text rendering",
                "best_for_text": True,
                "is_fast": True,
            },
            {
                "model_id": "google/imagen-3",
                "name": "Imagen 3",
                "provider": "google",
                "price_per_image": 0.040,
                "supports_generation": True,
                "max_images_per_request": 4,
                "description": "Google's latest image generation model",
                "best_for_photorealism": True,
            },
            {
                "model_id": "google/imagen-3-fast",
                "name": "Imagen 3 Fast",
                "provider": "google",
                "price_per_image": 0.020,
                "supports_generation": True,
                "max_images_per_request": 4,
                "description": "Fast version of Imagen 3",
                "is_fast": True,
            },
            {
                "model_id": "google/gemini-2.5-flash-image",
                "name": "Nano Banana",
                "provider": "google",
                "price_per_image": 0.00,
                "supports_generation": True,
                "supported_sizes": ["1024x1024", "2048x2048"],
                "max_images_per_request": 1,
                "description": "Fast, good quality image generation",
                "is_fast": True,
            },
            {
                "model_id": "google/gemini-3-pro-image-preview",
                "name": "Nano Banana Pro",
                "provider": "google",
                "price_per_image": 0.04,
                "supports_generation": True,
                "supported_sizes": ["1024x1024", "2048x2048", "4096x4096"],
                "max_images_per_request": 1,
                "description": "Best quality, supports 4K resolution",
                "best_for_photorealism": True,
            },
        ]

        for model_data in default_models:
            model_id = model_data.pop("model_id")
            ImageModelCatalog.objects.update_or_create(
                model_id=model_id,
                defaults={
                    **model_data,
                    "is_available": True,
                    "first_seen_at": timezone.now(),
                }
            )
        logger.info(f"[ImageModels] Populated {len(default_models)} default models")

    @action(detail=False, methods=["post"], url_path="refresh")
    def refresh_catalog(self, request):
        """Refresh image model catalog from service."""
        try:
            # Clear cache
            cache.delete_pattern("image_models:*")

            # Repopulate from service
            self._populate_from_service()

            return Response({
                "success": True,
                "message": "Image model catalog refreshed"
            })
        except Exception as e:
            logger.error(f"[ImageModels] Refresh failed: {e}")
            return Response({
                "success": False,
                "error": "Failed to refresh model catalog. Please try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VideoModelViewSet(viewsets.ViewSet):
    """
    ViewSet for video generation model configuration.

    Returns available video models and their configuration from constants.py.
    Unlike ImageModelCatalog, this doesn't use a database table since
    video models are centrally configured.
    """

    permission_classes = [AllowAny]  # Models list is public information

    def list(self, request):
        """
        List available video models and configuration.

        Returns:
            - models: List of available video models with pricing
            - supported_aspect_ratios: Available aspect ratios
            - default_aspect_ratio: Default aspect ratio
            - default_duration_seconds: Default video duration
            - default_model: Default model ID
        """
        from .video_providers import (
            VIDEO_MODELS,
            SUPPORTED_ASPECT_RATIOS,
            DEFAULT_ASPECT_RATIO,
            DEFAULT_DURATION_SECONDS,
            DEFAULT_VIDEO_MODEL,
        )
        from .serializers import VideoModelConfigSerializer

        # Convert VideoModelConfig dataclasses to dicts
        models_data = []
        for model in VIDEO_MODELS.values():
            models_data.append({
                "model_id": model.model_id,
                "canonical_id": model.canonical_id,
                "display_name": model.display_name,
                "provider": model.provider,
                "price_per_second_usd": model.price_per_second_usd,
                "max_duration_seconds": model.max_duration_seconds,
                "is_pro": model.is_pro,
                "supported_fps": model.supported_fps,
                "description": model.description,
            })

        config_data = {
            "models": models_data,
            "supported_aspect_ratios": list(SUPPORTED_ASPECT_RATIOS),
            "default_aspect_ratio": DEFAULT_ASPECT_RATIO,
            "default_duration_seconds": DEFAULT_DURATION_SECONDS,
            "default_model": DEFAULT_VIDEO_MODEL.model_id,
        }

        serializer = VideoModelConfigSerializer(config_data)
        return Response(serializer.data)


def _estimate_system_prompt(custom_prompt: Optional[str], features: Dict[str, Any]) -> str:
    """System prompt used to approximate prompt-token cost for the given features.

    Built through the same prompts_v2 builder the LangChain agent uses in
    production, so the estimate reflects what the agent will actually send.

    Args:
        custom_prompt: User-provided system prompt override, if any
        features: Mapping with any of enable_mcp_tools, enable_reasoning,
            enable_file_tools, enable_image_generation, enable_video_generation
    """
    from .prompts_v2 import get_prompt_builder

    feature_keys = (
        "mcp_tools", "reasoning", "file_tools", "image_generation", "video_generation",
    )
    enabled_features = {
        key for key in feature_keys
        if features.get(f"enable_{key}", False)
    }
    system_prompt, _metadata = get_prompt_builder().build_full_prompt(
        custom_prompt=custom_prompt or None,
        enabled_features=enabled_features,
    )
    return system_prompt


class CompletionViewSet(viewsets.ViewSet):
    """
    ViewSet for OpenRouter completions.

    Provides endpoints for:
    - Single model completion
    - Completion with fallback
    - Cost estimation
    - Rate limit info
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def complete(self, request):
        """Generate completion with a single model."""
        serializer = CompletionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # --- Sterna intelligent routing intercept ---
        from llm.smart_router.router import SmartRouter
        if SmartRouter.is_auto_router_model(data["model"]):
            router = SmartRouter()
            sterna_strength = data.get("sterna_strength")
            min_score_override = 70 if sterna_strength == "strong" else None
            sterna_resolution = router.resolve(
                model_id=data["model"],
                messages=data["messages"],
                conversation_id=data.get("conversation_id"),
                user=request.user,
                min_score_override=min_score_override,
            )
            data["model"] = sterna_resolution.resolved_model_id
            logger.info(
                f"[Sterna] Complete endpoint resolved -> {data['model']} "
                f"(tier={sterna_resolution.tier}, score={sterna_resolution.final_score})"
            )

        # Check rate limit
        rate_limiter = RateLimiter()
        project_id = str(data.get("project_id")) if data.get("project_id") else None

        try:
            rate_limiter.wait_if_needed(
                data["model"], project_id=project_id, max_wait=10.0
            )
        except Exception as e:
            return Response({"error": get_user_friendly_error(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Generate completion (model_id enables provider-scoped BYOK
        # direct routing when the user has a matching provider key)
        client = OpenRouterClient(
            user=request.user, request_source='chat', model_id=data["model"],
        )

        try:
            # Build kwargs for additional parameters
            kwargs = {}
            if data.get("top_k") is not None:
                kwargs["top_k"] = data["top_k"]
            if data.get("frequency_penalty") is not None:
                kwargs["frequency_penalty"] = data["frequency_penalty"]
            if data.get("presence_penalty") is not None:
                kwargs["presence_penalty"] = data["presence_penalty"]
            if data.get("repetition_penalty") is not None:
                kwargs["repetition_penalty"] = data["repetition_penalty"]
            if data.get("min_p") is not None:
                kwargs["min_p"] = data["min_p"]
            if data.get("top_a") is not None:
                kwargs["top_a"] = data["top_a"]
            if data.get("reasoning_effort") is not None:
                kwargs["reasoning_effort"] = data["reasoning_effort"]
            if data.get("plugins") is not None:
                kwargs["plugins"] = data["plugins"]

            # Extract feature flags
            enable_reasoning = data.get("enable_reasoning", False)

            result = client.complete(
                model=data["model"],
                messages=data["messages"],
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens", 1000),
                top_p=data.get("top_p", 1.0),
                stream=data.get("stream", False),
                enable_mcp_tools=False,  # Non-streaming endpoint doesn't support MCP yet
                enable_reasoning=enable_reasoning,
                has_mcp_tools=False,
                mcp_tools=None,
                **kwargs
            )

            response_serializer = CompletionResponseSerializer(data=result)
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data)

        except ContextLimitExceededException as e:
            logger.error(f"Context limit exceeded: {e}")
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            logger.error(f"Completion failed: {e}")
            return Response(
                {"error": get_user_friendly_error(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], url_path='stream-complete')
    def stream_complete(self, request):
        """Generate completion with streaming (Server-Sent Events)."""
        serializer = CompletionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Check rate limit
        rate_limiter = RateLimiter()
        project_id = str(data.get("project_id")) if data.get("project_id") else None

        try:
            rate_limiter.wait_if_needed(
                data["model"], project_id=project_id, max_wait=10.0
            )
        except Exception as exc:
            # Capture the message eagerly: the exception variable is
            # cleared when the except block exits, so referencing it
            # lazily inside the generator raises NameError (F821).
            error_message = error_payload(exc)

            # Return error as SSE event
            def error_generator():
                yield f"event: error\ndata: {json.dumps(error_message)}\n\n"
            return StreamingHttpResponse(
                error_generator(),
                content_type="text/event-stream; charset=utf-8",
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # MCP Tools integration
        # Extract feature flags for system prompt building
        enable_mcp_tools = data.get("enable_mcp_tools", False)
        enable_brave_search = data.get("enable_brave_search", False)
        enable_google_maps = data.get("enable_google_maps", False)
        enable_reasoning = data.get("enable_reasoning", False)
        enable_file_tools = should_enable_file_tools(data, request.user)

        logger.info(f"MCP tools requested: {enable_mcp_tools} for user {request.user.id}")
        logger.info(f"Brave Search enabled: {enable_brave_search}")
        logger.info(f"Google Maps enabled: {enable_google_maps}")
        logger.info(f"Reasoning enabled: {enable_reasoning}")
        logger.info(f"File tools enabled: {enable_file_tools}")

        mcp_tools = None
        mcp_tools_payload = None
        has_mcp_tools = False

        if enable_mcp_tools:
            try:
                from mcp.registry import get_registry
                from mcp.utils import mcp_tools_to_openai_functions

                # Get MCP registry and fetch available tools
                registry = get_registry()
                mcp_tools = registry.get_available_tools_sync(request.user)

                if mcp_tools:
                    # Convert MCP tools to OpenAI function format
                    mcp_tools_payload = mcp_tools_to_openai_functions(mcp_tools)
                    has_mcp_tools = True

                    # Note: System prompt injection is handled centrally in
                    # llm/client.py's _inject_system_prompt(), which calls
                    # mcp.prompts.build_mcp_system_prompt() for the tool list.

                    logger.info(f"MCP enabled: {len(mcp_tools)} tools available for user {request.user.id}")
                else:
                    logger.warning(f"MCP enabled but no tools found for user {request.user.id}")
            except Exception as e:
                logger.error(f"Failed to load MCP tools: {e}")
                # Continue without MCP tools rather than failing the request

        # File Tools integration
        file_tools_payload = None
        if enable_file_tools:
            try:
                file_tools_payload = get_file_tools()
                logger.info(f"File tools enabled: {len(file_tools_payload)} tools available")
            except Exception as e:
                logger.error(f"Failed to load file tools: {e}")
                # Continue without file tools rather than failing the request

        # Generate streaming completion (model_id enables provider-scoped
        # BYOK direct routing when the user has a matching provider key)
        client = OpenRouterClient(
            user=request.user,
            request_source='chat_stream',
            model_id=data["model"],
        )

        def event_stream():
            """Generator that yields SSE events."""
            try:
                # Build kwargs for additional parameters
                kwargs = {}

                # Add optional sampling parameters if provided
                if data.get("top_k") is not None:
                    kwargs["top_k"] = data["top_k"]
                if data.get("frequency_penalty") is not None:
                    kwargs["frequency_penalty"] = data["frequency_penalty"]
                if data.get("presence_penalty") is not None:
                    kwargs["presence_penalty"] = data["presence_penalty"]
                if data.get("repetition_penalty") is not None:
                    kwargs["repetition_penalty"] = data["repetition_penalty"]
                if data.get("min_p") is not None:
                    kwargs["min_p"] = data["min_p"]
                if data.get("top_a") is not None:
                    kwargs["top_a"] = data["top_a"]
                if data.get("reasoning_effort") is not None:
                    kwargs["reasoning_effort"] = data["reasoning_effort"]
                if data.get("plugins") is not None:
                    kwargs["plugins"] = data["plugins"]

                # Add MCP tools and/or File tools if available
                all_tools = []
                if mcp_tools_payload:
                    all_tools.extend(mcp_tools_payload)
                if file_tools_payload:
                    all_tools.extend(file_tools_payload)

                if all_tools:
                    kwargs["tools"] = all_tools
                    kwargs["tool_choice"] = "auto"

                # Log message details for debugging tool calls
                logger.info(f"Sending {len(data['messages'])} messages to model")
                message_roles = [msg.get('role') for msg in data['messages']]
                logger.info(f"Message roles: {message_roles}")
                tool_messages = [msg for msg in data['messages'] if msg.get('role') == 'tool']
                if tool_messages:
                    logger.info(f"Found {len(tool_messages)} tool messages with tool_call_ids: {[msg.get('tool_call_id') for msg in tool_messages]}")

                for chunk in client.complete_stream(
                    model=data["model"],
                    messages=data["messages"],
                    temperature=data.get("temperature", 0.7),
                    max_tokens=data.get("max_tokens", 1000),
                    top_p=data.get("top_p", 1.0),
                    enable_mcp_tools=enable_mcp_tools,
                    enable_reasoning=enable_reasoning,
                    enable_file_tools=enable_file_tools,
                    has_mcp_tools=has_mcp_tools,
                    mcp_tools=mcp_tools,  # Pass MCP tools for dynamic prompt building
                    **kwargs
                ):
                    # Convert chunk to SSE format
                    event = chunk.get("event", "message")
                    chunk_data = chunk.get("data", {})

                    # Handle tool_calls in "done" event
                    if event == "done":
                        # Extract finish_reason early so it's available throughout this block
                        finish_reason = chunk_data.get("finish_reason")

                        # Capture first call usage for accumulation
                        first_call_usage = chunk_data.get("usage", {})
                        first_call_cost = chunk_data.get("cost", 0)
                        first_call_prompt_cost = chunk_data.get("prompt_cost", 0)
                        first_call_completion_cost = chunk_data.get("completion_cost", 0)

                        # Initialize tool call lists early
                        file_tool_calls = []
                        mcp_tool_calls = []

                        if "tool_calls" in chunk_data:
                            tool_calls = chunk_data["tool_calls"]

                            # Separate file tools from MCP tools
                            file_tool_names = {"list_files", "read_file", "write_file", "create_directory", "delete_file", "rename_file"}

                            for idx, tc in enumerate(tool_calls):
                                tool_name = tc.get("function", {}).get("name")
                                tool_call_id = tc.get("id")

                                # Fix missing ID
                                if tool_call_id is None:
                                    import uuid
                                    tool_call_id = f"call_{uuid.uuid4().hex[:16]}"
                                    tc["id"] = tool_call_id

                                # If tool_name is None, try to infer from arguments
                                if tool_name is None:
                                    arguments = tc.get("function", {}).get("arguments", "")

                                    # Try to infer tool from arguments structure
                                    if '"path"' in arguments and '"content"' in arguments:
                                        tool_name = "write_file"
                                        # Fix the tool_call by adding the name
                                        tc["function"]["name"] = "write_file"
                                    elif '"path"' in arguments and '"content"' not in arguments:
                                        # Could be read_file, list_files, or delete_file
                                        if '"recursive"' in arguments:
                                            tool_name = "list_files"
                                            tc["function"]["name"] = "list_files"
                                        else:
                                            # Default to read_file for now
                                            tool_name = "read_file"
                                            tc["function"]["name"] = "read_file"

                                if tool_name in file_tool_names:
                                    file_tool_calls.append(tc)
                                else:
                                    mcp_tool_calls.append(tc)

                            # Handle file tools immediately (no approval needed - sandboxed)
                            if finish_reason == "tool_calls" and file_tool_calls and enable_file_tools:
                                logger.info(f"File tool calls detected: {len(file_tool_calls)} call(s) - executing immediately")

                                # Execute file tools and get results
                                try:
                                    user_id = str(request.user.id)
                                    conversation_id = data.get("conversation_id", "default")
                                    chat_id = data.get("chat_id")

                                    logger.info(f"[FILE_TOOLS] user_id={user_id}, conversation_id={conversation_id}, chat_id={chat_id}")

                                    # Extract JWT token from request
                                    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
                                    auth_token = None
                                    if auth_header.startswith('Bearer '):
                                        auth_token = auth_header[7:]  # Remove "Bearer " prefix

                                    tool_results = handle_file_tool_calls(
                                        tool_calls=file_tool_calls,
                                        user_id=user_id,
                                        conversation_id=conversation_id,
                                        chat_id=chat_id,
                                        sync_mode=True,
                                        auth_token=auth_token
                                    )

                                    # Send file tool execution event to frontend
                                    yield f"event: file_tool_executed\ndata: {json.dumps({'tool_calls': file_tool_calls, 'results': tool_results})}\n\n"

                                    logger.info(f"File tools executed successfully: {len(tool_results)} results")

                                    # Build new messages list with original messages + tool_calls + results
                                    updated_messages = list(data["messages"])

                                    # Add assistant message with tool_calls
                                    updated_messages.append({
                                        "role": "assistant",
                                        "content": "",  # No content when calling tools
                                        "tool_calls": file_tool_calls
                                    })

                                    # Add tool result messages
                                    for tool_msg in tool_results:
                                        updated_messages.append(tool_msg)

                                    logger.info(f"Added {len(file_tool_calls)} tool_calls and {len(tool_results)} results to messages, recalling LLM")

                                    # If there are no MCP tool calls, recall the LLM immediately with tool results
                                    if not mcp_tool_calls:
                                        # Recall LLM with tool results to get final response
                                        logger.info("Recalling LLM with file tool results for final response")

                                        # Make new streaming request with updated messages
                                        # Note: disable file_tools for second call since they already executed
                                        response_stream = client.complete_stream(
                                            model=data["model"],
                                            messages=updated_messages,
                                            temperature=data.get("temperature", 0.7),
                                            max_tokens=data.get("max_tokens", 1000),
                                            top_p=data.get("top_p", 1.0),
                                            enable_mcp_tools=enable_mcp_tools,
                                            enable_reasoning=enable_reasoning,
                                            enable_file_tools=False,  # File tools already executed
                                            has_mcp_tools=has_mcp_tools,
                                            mcp_tools=mcp_tools,
                                            **kwargs
                                        )

                                        # Stream the final response
                                        # Note: response_stream is already in SSE format (event/data)
                                        for chunk in response_stream:
                                            event = chunk.get("event", "message")
                                            chunk_data = chunk.get("data", {})

                                            # Accumulate tokens from both API calls in the final done event
                                            if event == "done":
                                                second_call_usage = chunk_data.get("usage", {})

                                                # Accumulate tokens
                                                accumulated_usage = {
                                                    "prompt_tokens": first_call_usage.get("prompt_tokens", 0) + second_call_usage.get("prompt_tokens", 0),
                                                    "completion_tokens": first_call_usage.get("completion_tokens", 0) + second_call_usage.get("completion_tokens", 0),
                                                    "total_tokens": first_call_usage.get("total_tokens", 0) + second_call_usage.get("total_tokens", 0),
                                                }

                                                # Accumulate costs
                                                accumulated_cost = first_call_cost + chunk_data.get("cost", 0)
                                                accumulated_prompt_cost = first_call_prompt_cost + chunk_data.get("prompt_cost", 0)
                                                accumulated_completion_cost = first_call_completion_cost + chunk_data.get("completion_cost", 0)

                                                # Update chunk_data with accumulated values
                                                chunk_data["usage"] = accumulated_usage
                                                chunk_data["cost"] = accumulated_cost
                                                chunk_data["prompt_cost"] = accumulated_prompt_cost
                                                chunk_data["completion_cost"] = accumulated_completion_cost

                                                logger.info(f"[TOKEN_ACCUMULATION] First call: {first_call_usage}, Second call: {second_call_usage}, Accumulated: {accumulated_usage}")
                                                logger.info(f"[TOKEN_ACCUMULATION] Total cost: {accumulated_cost}")

                                            # Forward all events to client
                                            yield f"event: {event}\ndata: {json.dumps(chunk_data)}\n\n"

                                            # Stop after done event
                                            if event == "done":
                                                return

                                        # Fallback: if stream ended without done event
                                        logger.warning("File tool response stream ended without done event")
                                        yield f"event: done\ndata: {json.dumps({'model': data['model']})}\n\n"
                                        return

                                except Exception as e:
                                    logger.error(f"Error executing file tools: {e}", exc_info=True)
                                    yield f"event: error\ndata: {json.dumps({'error': 'File tool execution failed. Please try again.'})}\n\n"
                                    return

                        # Handle MCP tools (require approval)
                        if finish_reason == "tool_calls" and mcp_tool_calls and enable_mcp_tools:
                            logger.info(f"MCP tool calls detected: {len(mcp_tool_calls)} call(s) - awaiting approval")

                            # Create MCPToolApproval for each tool call
                            from mcp.models import MCPToolApproval, MCPTool
                            from mcp.registry import get_registry

                            approvals_created = []

                            for tool_call in mcp_tool_calls:
                                tool_name = tool_call.get("function", {}).get("name")
                                arguments_str = tool_call.get("function", {}).get("arguments", "{}")

                                logger.info(f"Processing tool call: {tool_name}")
                                logger.info(f"Raw arguments string: {arguments_str}")

                                # Parse arguments JSON
                                try:
                                    import json as json_lib
                                    arguments = json_lib.loads(arguments_str) if arguments_str else {}
                                    logger.info(f"Parsed arguments: {arguments}")
                                except Exception as e:
                                    logger.error(f"Failed to parse tool arguments: {e}")
                                    arguments = {}

                                # Find the MCP tool by name
                                get_registry()
                                mcp_tool = None
                                for tool in mcp_tools:
                                    if tool.name == tool_name:
                                        # Get the actual MCPTool object from database
                                        try:
                                            mcp_tool = MCPTool.objects.get(id=tool.id)
                                        except MCPTool.DoesNotExist:
                                            logger.error(f"Tool {tool_name} not found in database")
                                        break

                                if mcp_tool:
                                    # Validate required parameters
                                    input_schema = mcp_tool.input_schema or {}
                                    required_params = input_schema.get("required", [])

                                    missing_params = []
                                    for param in required_params:
                                        if param not in arguments or arguments[param] in (None, "", "undefined"):
                                            missing_params.append(param)

                                    if missing_params:
                                        logger.warning(f"Tool {tool_name} called with missing required parameters: {missing_params}")
                                        logger.warning(f"Required: {required_params}, Provided: {list(arguments.keys())}")
                                        # Skip this tool call - don't create approval for invalid calls
                                        continue

                                    # Create approval request
                                    approval = MCPToolApproval.objects.create(
                                        user=request.user,
                                        tool=mcp_tool,
                                        proposed_arguments=arguments,
                                        status=MCPToolApproval.ApprovalStatus.PENDING,
                                        scope=MCPToolApproval.ApprovalScope.ONCE
                                    )

                                    approvals_created.append({
                                        "id": str(approval.id),
                                        "tool_id": str(mcp_tool.id),
                                        "tool_name": mcp_tool.name,
                                        "tool_description": mcp_tool.description,
                                        "server_name": mcp_tool.server.name,
                                        "arguments": arguments,
                                        "status": "pending"
                                    })

                                    logger.info(f"Created approval {approval.id} for tool {tool_name} with arguments: {arguments}")

                            # Send tool_call_request event to frontend with approval details
                            if approvals_created:
                                yield f"event: tool_call_request\ndata: {json.dumps({'approvals': approvals_created, 'tool_calls': mcp_tool_calls})}\n\n"
                                # Send a "done" event indicating we're waiting for approval
                                done_data_with_approval = {
                                    **chunk_data,
                                    "awaiting_approval": True,
                                    "approval_count": len(approvals_created)
                                }
                                yield f"event: done\ndata: {json.dumps(done_data_with_approval)}\n\n"
                                # Use return instead of continue to properly terminate the generator
                                # This ensures the stream ends cleanly after sending the approval request
                                return
                            else:
                                # All tool calls failed validation - send done without tool_calls
                                logger.warning(f"All {len(mcp_tool_calls)} MCP tool call(s) failed validation - completing stream normally")
                                # Remove tool_calls from chunk_data to avoid confusing frontend
                                done_data_no_tools = {**chunk_data}
                                done_data_no_tools.pop("tool_calls", None)
                                done_data_no_tools["finish_reason"] = "stop"  # Override finish_reason
                                yield f"event: done\ndata: {json.dumps(done_data_no_tools)}\n\n"
                                # Use return instead of continue to properly terminate the generator
                                return

                    # Send as SSE event
                    yield f"event: {event}\ndata: {json.dumps(chunk_data)}\n\n"

            except ContextLimitExceededException as e:
                logger.error(f"Context limit exceeded in streaming: {e}")
                error_data = error_payload(e)
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

            except Exception as e:
                logger.error(f"Streaming completion failed: {e}")
                yield f"event: error\ndata: {json.dumps(error_payload(e))}\n\n"

        return StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream; charset=utf-8",
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',  # Disable nginx buffering
            }
        )

    @action(detail=False, methods=["post"])
    def complete_with_fallback(self, request):
        """Generate completion with automatic fallback."""
        serializer = FallbackCompletionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client = OpenRouterClient(user=request.user, request_source='chat_fallback')

        try:
            # Build kwargs for additional parameters
            kwargs = {}
            if data.get("top_k") is not None:
                kwargs["top_k"] = data["top_k"]
            if data.get("frequency_penalty") is not None:
                kwargs["frequency_penalty"] = data["frequency_penalty"]
            if data.get("presence_penalty") is not None:
                kwargs["presence_penalty"] = data["presence_penalty"]
            if data.get("repetition_penalty") is not None:
                kwargs["repetition_penalty"] = data["repetition_penalty"]
            if data.get("min_p") is not None:
                kwargs["min_p"] = data["min_p"]
            if data.get("top_a") is not None:
                kwargs["top_a"] = data["top_a"]
            if data.get("reasoning_effort") is not None:
                kwargs["reasoning_effort"] = data["reasoning_effort"]

            result = client.complete_with_fallback(
                models=data["models"],
                messages=data["messages"],
                max_cost=data.get("max_cost"),
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens", 1000),
                top_p=data.get("top_p", 1.0),
                **kwargs
            )

            response_serializer = CompletionResponseSerializer(data=result)
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data)

        except Exception as e:
            logger.error(f"Completion with fallback failed: {e}")
            return Response(
                {"error": get_user_friendly_error(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"])
    def estimate_cost(self, request):
        """Estimate cost for a completion."""
        serializer = CostEstimateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        catalog = CatalogService()
        total_cost = catalog.estimate_cost(
            data["model_id"], data["prompt_tokens"], data["completion_tokens"]
        )

        # Get individual costs
        pricing = catalog.get_model_pricing(data["model_id"])
        from .estimation_config import FALLBACK_PROMPT_PRICE_PER_1K, FALLBACK_COMPLETION_PRICE_PER_1K
        prompt_unit = pricing["prompt_price"] if pricing["prompt_price"] is not None else FALLBACK_PROMPT_PRICE_PER_1K
        completion_unit = pricing["completion_price"] if pricing["completion_price"] is not None else FALLBACK_COMPLETION_PRICE_PER_1K
        prompt_cost = float(data["prompt_tokens"]) * prompt_unit / 1000
        completion_cost = float(data["completion_tokens"]) * completion_unit / 1000

        # Round to 8 decimal places to avoid float precision issues with serializer validation
        response_data = {
            "model_id": data["model_id"],
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "prompt_cost": round(prompt_cost, 8),
            "completion_cost": round(completion_cost, 8),
            "total_cost": round(float(total_cost), 8),
            "currency": "USD",
        }

        response_serializer = CostEstimateResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data)

    @action(detail=False, methods=["post"], url_path='estimate-batch-cost')
    def estimate_batch_cost(self, request):
        """Estimate cost for multiple models.

        Prefer `typed_text` + `files_text` for accurate estimation. Falls back to
        `prompt_text` + optional `estimated_completion_tokens` for backward compatibility.
        """
        from .estimation_config import (
            CHARS_PER_TOKEN,
            SAFETY_COMPLETION_RESERVE,
            DEFAULT_MAX_TOKENS_FALLBACK,
            ALPHA_T_DEFAULT,
            BETA_T_DEFAULT,
            ABS_COMPLETION_CAP,
            LINEAR_P_CAP,
            SUMMARIZATION_FILE_BOOST_PER_FILE,
            SUMMARIZATION_FILE_BOOST_MAX_FILES,
            SUMMARIZATION_PROMPT_PERCENT_BOOST,
            KEYWORD_SCALE_PER_HIT,
            KEYWORD_SCALE_MAX,
            IMAGE_PROMPT_BASE_TOKENS,
            IMAGE_PROMPT_TOKENS_PER_MB,
            IMAGE_PROMPT_TOKENS_PER_MP,
            IMAGE_PROMPT_TOKENS_CAP_PER_IMAGE,
            IMAGE_MAX_COUNT,
            IMAGE_LINEAR_WEIGHT,
        )

        serializer = BatchCostEstimateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Token estimation helpers (approximate: ~4 chars per token)
        def approx_tokens(s: str) -> int:
            return max(0, len(s) // CHARS_PER_TOKEN)

        typed_text = data.get("typed_text") or ""
        files_text = data.get("files_text") or ""
        base_system_prompt = data.get("system_prompt") or ""
        images_meta = data.get("images") or []
        has_breakdown = bool(typed_text or files_text)
        files_meta = data.get("files") or []
        features_by_model = data.get("features_by_model") or {}

        # Build complete system prompt with all enabled features (global fallback)
        global_system_prompt = _estimate_system_prompt(
            base_system_prompt if base_system_prompt else None, data
        )
        # Choose alpha/beta: request override > task-derived > defaults
        if data.get("alpha") is not None and data.get("beta") is not None:
            alpha = float(data.get("alpha"))
            beta = float(data.get("beta"))
        else:
            try:
                from .prompt_classifier import predict_prompt_type, get_task_coefficients
                task_info = predict_prompt_type(typed_text, files_meta)
                primary = task_info.get('task_primary')
                alpha, beta = get_task_coefficients(primary)
                # Special case: files-only (no typed text) → summarization-like output
                if task_info.get('signals', {}).get('has_files') and not task_info.get('signals', {}).get('has_text'):
                    alpha, beta = get_task_coefficients('summarization')
                # Scale coefficients by keyword intensity for the primary task
                kw_scores = task_info.get('signals', {}).get('keyword_scores', {}) or {}
                kw_primary = int(kw_scores.get(primary, 0))
                if kw_primary > 0:
                    scale = 1.0 + min(kw_primary * KEYWORD_SCALE_PER_HIT, KEYWORD_SCALE_MAX - 1.0)
                    alpha *= scale
                    beta *= scale
                # Keep task_info around for later summarization boosts
                task_primary = primary
                task_detection = task_info
            except Exception:
                alpha = ALPHA_T_DEFAULT
                beta = BETA_T_DEFAULT
                task_primary = 'explanation'
                task_detection = None
        margin = data.get("margin") if data.get("margin") is not None else SAFETY_COMPLETION_RESERVE

        # Compute prompt tokens P
        def image_tokens(images) -> int:
            total = 0
            count = 0
            for img in images or []:
                if count >= IMAGE_MAX_COUNT:
                    break
                size = img.get('size') or 0
                width = img.get('width')
                height = img.get('height')
                # Prefer megapixels if dimensions are provided
                if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                    mp = (width * height) / 1_000_000.0
                    t = IMAGE_PROMPT_BASE_TOKENS + int(IMAGE_PROMPT_TOKENS_PER_MP * mp)
                else:
                    mb = float(size) / (1024.0 * 1024.0)
                    t = IMAGE_PROMPT_BASE_TOKENS + int(IMAGE_PROMPT_TOKENS_PER_MB * mb)
                t = min(t, IMAGE_PROMPT_TOKENS_CAP_PER_IMAGE)
                total += max(0, t)
                count += 1
            return total

        # Calculate base token counts (without system prompt)
        if has_breakdown:
            typed_tokens = approx_tokens(typed_text)
            file_tokens = approx_tokens(files_text)
            img_tokens = image_tokens(images_meta)
        else:
            prompt_text = data.get("prompt_text") or ""
            # If client sent only prompt_text, we cannot distinguish files/images; treat all as text
            base_prompt_tokens = max(1, len(prompt_text) // CHARS_PER_TOKEN)

        # Helper: Calculate file tools tokens (LangChain adds tool descriptions to prompt)
        def calc_file_tools_tokens() -> int:
            """Estimate tokens added by FILE_TOOLS descriptions in LangChain"""
            try:
                from .langchain_file_tools import FILE_TOOLS
                # Each tool has name + description + args schema
                # Rough estimate: ~60-100 tokens per tool
                return len(FILE_TOOLS) * 80  # Conservative estimate
            except Exception:
                return 0

        # Helper function to calculate prompt tokens for a given system prompt
        def calc_prompt_tokens(sys_prompt: str, include_file_tools: bool = False) -> int:
            system_tokens = approx_tokens(sys_prompt)
            # Add file tools overhead if enabled (LangChain adds tool descriptions)
            if include_file_tools:
                system_tokens += calc_file_tools_tokens()
            if has_breakdown:
                return typed_tokens + file_tokens + img_tokens + system_tokens
            else:
                return base_prompt_tokens + system_tokens

        # Calculate global prompt tokens (used for models without specific features)
        global_prompt_tokens = calc_prompt_tokens(global_system_prompt)

        # Base completion from alpha + beta·min(P, LINEAR_P_CAP) (lower bounded at 0)
        # Linear term uses a reduced image contribution to avoid inflating expected output
        if has_breakdown:
            P_linear_raw = typed_tokens + file_tokens + int(img_tokens * IMAGE_LINEAR_WEIGHT)
        else:
            P_linear_raw = base_prompt_tokens
        P_eff = min(P_linear_raw, LINEAR_P_CAP)
        base_completion_linear = max(0, int(alpha + beta * P_eff))
        # Additional boosts for summarization based on number of files and prompt size
        try:
            file_count = len(files_meta)
        except Exception:
            file_count = 0
        if file_count > 0 and (locals().get('task_primary') == 'summarization'):
            file_boost = SUMMARIZATION_FILE_BOOST_PER_FILE * min(file_count, SUMMARIZATION_FILE_BOOST_MAX_FILES)
            tokens_boost = int(SUMMARIZATION_PROMPT_PERCENT_BOOST * P_eff)
            base_completion_linear += file_boost + tokens_boost
        # Deprecated override
        deprecated_override = data.get("estimated_completion_tokens")

        catalog = CatalogService()
        costs = []
        total_cost = 0

        # Compute costs per model with per-model capacity using Ĉ(P) = min(M, W − P − margin, max(0, α + β·P))
        costs = []
        total_cost = 0
        per_model_estimates = []
        per_model_prompt_tokens = {}  # Track prompt tokens per model

        for model_id in data["model_ids"]:
            try:
                model_info = catalog.get_model(model_id)
                if not model_info:
                    continue
                max_tokens = model_info.get("max_tokens") or DEFAULT_MAX_TOKENS_FALLBACK

                # Calculate model-specific prompt tokens if features_by_model is provided
                if model_id in features_by_model:
                    model_features = features_by_model[model_id]
                    has_file_tools = model_features.get("enable_file_tools", False)
                    model_system_prompt = _estimate_system_prompt(
                        model_features.get("system_prompt") or base_system_prompt or None,
                        model_features,
                    )
                    model_prompt_tokens = calc_prompt_tokens(model_system_prompt, include_file_tools=has_file_tools)
                else:
                    # Use global prompt tokens for this model
                    model_prompt_tokens = global_prompt_tokens

                per_model_prompt_tokens[model_id] = model_prompt_tokens

                # M from per-model override > request > model property
                per_model = (data.get("max_new_tokens_by_model") or {}).get(model_id)
                req_max_new = data.get("max_new_tokens")
                model_max_new = model_info.get("max_completion_tokens") or (max_tokens - margin)
                if per_model is not None:
                    M = int(per_model)
                elif req_max_new is not None:
                    M = int(req_max_new)
                else:
                    M = int(model_max_new)
                # Apply absolute cap to M
                M = min(M, ABS_COMPLETION_CAP)
                # Compute Ĉ(P) using model-specific prompt tokens
                capacity = max(0, max_tokens - model_prompt_tokens - margin)
                c_hat = min(M, capacity, base_completion_linear) if deprecated_override is None else min(M, capacity, int(deprecated_override))
                per_model_estimates.append(max(0, int(c_hat)))

                # Clamp prompt for cost computation to respect total window with chosen completion
                effective_prompt = max(0, min(model_prompt_tokens, max_tokens - margin - c_hat))
                cost = catalog.estimate_cost(model_id, effective_prompt, int(c_hat))
                # Round to 8 decimal places to avoid float precision issues with serializer validation
                cost_rounded = round(float(cost), 8)
                costs.append({
                    "model_id": model_id,
                    "model_name": model_info.get("name", model_id),
                    "cost": cost_rounded,
                    "prompt_tokens": model_prompt_tokens,
                    "completion_tokens": int(c_hat),
                })
                total_cost += cost_rounded
                logger.debug(f"Estimated cost for {model_id}: ${cost_rounded:.6f}")
            except Exception as e:
                logger.warning(f"Failed to estimate cost for {model_id}: {e}")
                continue

        # Report representative estimates across models (median of per-model values)
        if per_model_estimates:
            sorted_est = sorted(per_model_estimates)
            mid = len(sorted_est) // 2
            if len(sorted_est) % 2 == 1:
                reported_completion = sorted_est[mid]
            else:
                reported_completion = int((sorted_est[mid - 1] + sorted_est[mid]) / 2)
        else:
            reported_completion = base_completion_linear

        # Report median prompt tokens across models (since they can differ now)
        if per_model_prompt_tokens:
            sorted_prompts = sorted(per_model_prompt_tokens.values())
            mid = len(sorted_prompts) // 2
            if len(sorted_prompts) % 2 == 1:
                reported_prompt_tokens = sorted_prompts[mid]
            else:
                reported_prompt_tokens = int((sorted_prompts[mid - 1] + sorted_prompts[mid]) / 2)
        else:
            reported_prompt_tokens = global_prompt_tokens

        # Round total_cost to avoid float precision issues with serializer validation
        total_cost_rounded = round(total_cost, 8)

        response_data = {
            "costs": costs,
            "total_cost": total_cost_rounded,
            "prompt_tokens": reported_prompt_tokens,
            "completion_tokens": int(reported_completion),
        }

        response_serializer = BatchCostEstimateResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data)

    @action(detail=False, methods=["get"])
    def rate_limit_info(self, request):
        """Get rate limit information for a model."""
        model_id = request.query_params.get("model_id")
        if not model_id:
            return Response(
                {"error": "model_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        rate_limiter = RateLimiter()
        info = rate_limiter.get_limits_info(model_id)

        serializer = RateLimitInfoSerializer(data=info)
        serializer.is_valid(raise_exception=True)

        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def usage_stats(self, request):
        """Get usage statistics."""
        # This would integrate with actual usage tracking
        # For now, return mock data
        stats = {
            "period": "last_30_days",
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "models_used": {},
            "daily_breakdown": [],
        }

        # Try to get from OpenRouter if available
        client = OpenRouterClient(user=request.user)
        api_stats = client.get_usage_stats()
        if api_stats:
            stats.update(api_stats)

        serializer = UsageStatsSerializer(data=stats)
        serializer.is_valid(raise_exception=True)

        return Response(serializer.data)


# ===========================
# LangChain-based Streaming (V2)
# ===========================


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_complete_langchain(request):
    """
    Stream completion using LangChain with automatic tool calling loop.

    This is a V2 endpoint that properly handles multiple tool call cycles.
    """
    from .langchain_agent import LangChainStreamingAgent
    from .uploaded_files_helper import encode_uploaded_files, prepare_uploaded_files_context

    # Handle both JSON and FormData (multipart/form-data with files)
    if request.content_type and 'multipart/form-data' in request.content_type:
        # FormData: fields are in request.POST, need to parse JSON strings
        data = request.POST.dict()

        # Parse messages from JSON string
        messages_json = data.get("messages", "[]")
        try:
            messages = json.loads(messages_json) if isinstance(messages_json, str) else messages_json
        except json.JSONDecodeError:
            messages = []

        # Parse other parameters
        model = data.get("model")
        temperature = float(data.get("temperature", 0.7))
        max_tokens = int(data.get("max_tokens", 1000))

        # Feature flags - parse booleans from strings
        enable_brave_search = data.get("enable_brave_search", "false").lower() == "true"
        enable_google_maps = enable_brave_search  # Auto-enabled with Extended Search
        enable_image_generation = data.get("enable_image_generation", "false").lower() == "true"
        enable_video_generation = data.get("enable_video_generation", "false").lower() == "true"
        enable_reasoning = data.get("enable_reasoning", "false").lower() == "true"
        enable_file_tools = data.get("enable_file_tools", "false").lower() == "true"
        enable_mcp_tools = data.get("enable_mcp_tools", "false").lower() == "true"
        enable_voice_mode = data.get("enable_voice_mode", "false").lower() == "true"
        enable_sparks = data.get("enable_sparks", "false").lower() == "true"
        enable_knowledge_base = data.get("enable_knowledge_base", "false").lower() == "true"

        # Spark auto-fix request (JSON string in form data)
        spark_fix_request_str = data.get("spark_fix_request")
        spark_fix_request = None
        if spark_fix_request_str:
            try:
                spark_fix_request = json.loads(spark_fix_request_str)
                logger.info(f"[LangChain] Spark fix request for spark_id={spark_fix_request.get('spark_id')}")
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[LangChain] Invalid spark_fix_request JSON: {spark_fix_request_str}")

        spark_ignite_request_str = data.get("spark_ignite_request")
        spark_ignite_request = None
        if spark_ignite_request_str:
            try:
                spark_ignite_request = json.loads(spark_ignite_request_str)
                # Enrich with spark code from DB (frontend only sends spark_id + title)
                from sparks.models import Spark
                try:
                    spark = Spark.objects.get(id=spark_ignite_request["spark_id"])
                    spark_ignite_request["spark_code"] = spark.get_code()
                    spark_ignite_request["dependencies"] = json.dumps(spark.dependencies or [])
                    logger.info(f"[LangChain] Spark ignite request for spark_id={spark_ignite_request.get('spark_id')}")
                except Spark.DoesNotExist:
                    logger.warning(f"[LangChain] Spark not found for ignite: {spark_ignite_request.get('spark_id')}")
                    spark_ignite_request = None
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[LangChain] Invalid spark_ignite_request JSON: {spark_ignite_request_str}")

        conversation_id = data.get("conversation_id", "default")
        chat_id = data.get("chat_id")

        # Additional parameters
        system_prompt = data.get("system_prompt")
        message_id = data.get("message_id")
        reasoning_effort = data.get("reasoning_effort")
        reasoning_max_tokens = int(data.get("reasoning_max_tokens")) if data.get("reasoning_max_tokens") else None
    else:
        # JSON: use request.data directly
        data = request.data
        model = data.get("model")
        messages = data.get("messages", [])
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 1000)

        enable_brave_search = data.get("enable_brave_search", False)
        enable_google_maps = enable_brave_search  # Auto-enabled with Extended Search
        enable_image_generation = data.get("enable_image_generation", False)
        enable_video_generation = data.get("enable_video_generation", False)
        enable_reasoning = data.get("enable_reasoning", False)
        enable_file_tools = data.get("enable_file_tools", False)
        enable_mcp_tools = data.get("enable_mcp_tools", False)
        enable_voice_mode = data.get("enable_voice_mode", False)
        enable_sparks = data.get("enable_sparks", False)
        enable_knowledge_base = data.get("enable_knowledge_base", False)

        # Spark auto-fix request
        spark_fix_request = data.get("spark_fix_request")
        if spark_fix_request:
            logger.info(f"[LangChain] Spark fix request for spark_id={spark_fix_request.get('spark_id')}")

        # Spark ignite request
        spark_ignite_request = data.get("spark_ignite_request")
        if spark_ignite_request:
            # Enrich with spark code from DB (frontend only sends spark_id + title)
            from sparks.models import Spark
            try:
                spark = Spark.objects.get(id=spark_ignite_request["spark_id"])
                spark_ignite_request["spark_code"] = spark.get_code()
                spark_ignite_request["dependencies"] = json.dumps(spark.dependencies or [])
                logger.info(f"[LangChain] Spark ignite request for spark_id={spark_ignite_request.get('spark_id')}")
            except Spark.DoesNotExist:
                logger.warning(f"[LangChain] Spark not found for ignite: {spark_ignite_request.get('spark_id')}")
                spark_ignite_request = None

        conversation_id = data.get("conversation_id", "default")
        chat_id = data.get("chat_id")

        # Additional parameters
        system_prompt = data.get("system_prompt")
        message_id = data.get("message_id")
        reasoning_effort = data.get("reasoning_effort")
        reasoning_max_tokens = data.get("reasoning_max_tokens")

    # Parse sterna_strength for "regenerate stronger"
    sterna_strength = data.get("sterna_strength") if isinstance(data, dict) else None

    logger.info(f"[LangChain] Stream request received for model: {model}")
    logger.info(f"[LangChain] Voice mode enabled: {enable_voice_mode}")

    # --- Sterna intelligent routing intercept ---
    sterna_resolution = None
    if model:
        from llm.smart_router.router import SmartRouter
        if SmartRouter.is_auto_router_model(model):
            router = SmartRouter()
            min_score_override = 70 if sterna_strength == "strong" else None
            sterna_resolution = router.resolve(
                model_id=model,
                messages=messages,
                conversation_id=conversation_id,
                user=request.user,
                min_score_override=min_score_override,
            )
            model = sterna_resolution.resolved_model_id
            logger.info(
                f"[Sterna] Resolved -> {model} "
                f"(tier={sterna_resolution.tier}, score={sterna_resolution.final_score})"
            )

    # Filter out any None messages (defensive - frontend should not send them)
    if messages:
        original_count = len(messages)
        messages = [m for m in messages if m is not None]
        if len(messages) != original_count:
            logger.warning(f"[LangChain] Filtered out {original_count - len(messages)} None message(s)")

    # Check rate limiting
    rate_limiter = RateLimiter()

    # Handle uploaded files
    uploaded_files_encoded = []
    files_context_message = None

    # First, check if there are already files in the attachments folder (from previous messages)
    # This ensures the model always knows about uploaded files throughout the conversation
    if enable_file_tools and chat_id:
        import httpx
        import asyncio

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        auth_token_check = auth_header[7:] if auth_header.startswith('Bearer ') else None
        orchestrator_url = "http://orchestrator:8003"

        async def check_existing_files():
            """Check if attachments folder has files from previous messages"""
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        f"{orchestrator_url}/fs/list",
                        json={
                            "path": "attachments",
                            "user_id": str(request.user.id),
                            "conversation_id": conversation_id,
                            "chat_id": chat_id,
                            "sync_mode": True
                        },
                        headers={"Authorization": f"Bearer {auth_token_check}"}
                    )
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success") and result.get("files"):
                            existing_files = [f["name"] for f in result["files"] if f["type"] == "file"]
                            if existing_files:
                                return existing_files
            except Exception as e:
                logger.debug(f"[LangChain] Could not check existing attachments: {e}")
            return []

        # Run async check
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            existing_files = loop.run_until_complete(check_existing_files())
            if existing_files:
                files_list = ", ".join(existing_files)
                attachments_dir = f"/workspace/chat-{chat_id}/attachments"
                files_context_message = f"""📎 Uploaded files available ({len(existing_files)}): {files_list}

**Location**: `{attachments_dir}/`

**How to use**:
- Read: `read_file('{attachments_dir}/{existing_files[0]}')`
- List: `list_files('{attachments_dir}/')`

Files remain available throughout the conversation."""
                logger.info(f"[LangChain] Found {len(existing_files)} existing file(s) in attachments folder")
        finally:
            loop.close()

    # Check for files in the request (multipart/form-data)
    if request.FILES:
        attachments = list(request.FILES.values())
        logger.info(f"[LangChain] Found {len(attachments)} uploaded file(s)")

        # Encode files for transmission to orchestrator
        uploaded_files_encoded = encode_uploaded_files(attachments)

        # Generate context message to inform the model (pass chat_id for folder path)
        files_context_message = prepare_uploaded_files_context(attachments, chat_id=chat_id)

        logger.info(f"[LangChain] Encoded {len(uploaded_files_encoded)} file(s) for workspace")

        # Copy files to workspace IMMEDIATELY (so they're available for all subsequent messages)
        if enable_file_tools and uploaded_files_encoded:
            import httpx
            import asyncio

            # Extract JWT token for orchestrator auth
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            auth_token_temp = auth_header[7:] if auth_header.startswith('Bearer ') else None

            orchestrator_url = "http://orchestrator:8003"

            async def copy_files_to_workspace():
                """Copy uploaded files to attachments folder immediately"""
                async with httpx.AsyncClient(timeout=30.0) as client:
                    for file_data in uploaded_files_encoded:
                        try:
                            # Files go to attachments/ folder inside the chat workspace
                            attachments_path = f"attachments/{file_data['filename']}"

                            response = await client.post(
                                f"{orchestrator_url}/fs/write",
                                json={
                                    "path": attachments_path,  # Store in attachments subfolder
                                    "content": file_data["content_base64"],  # Will be decoded by orchestrator
                                    "user_id": str(request.user.id),
                                    "conversation_id": conversation_id,
                                    "chat_id": chat_id,
                                    "sync_mode": True,
                                    "is_base64": True  # Flag to tell orchestrator to decode
                                },
                                headers={"Authorization": f"Bearer {auth_token_temp}"}
                            )
                            if response.status_code == 200:
                                logger.info(f"[LangChain] Copied uploaded file to attachments: {attachments_path}")
                            else:
                                logger.error(f"[LangChain] Failed to copy file {file_data['filename']}: {response.status_code}")
                        except Exception as e:
                            logger.error(f"[LangChain] Error copying file {file_data['filename']}: {e}")

            # Run the async copy operation
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(copy_files_to_workspace())
            finally:
                loop.close()

    # Also check for files in data (if sent as JSON with base64)
    elif data.get("uploaded_files"):
        uploaded_files_encoded = data.get("uploaded_files")
        # Extract filenames for context
        filenames = [f.get("filename") for f in uploaded_files_encoded if f.get("filename")]
        if filenames:
            files_list = ", ".join(filenames)
            attachments_dir = f"/workspace/chat-{chat_id}/attachments"
            files_context_message = f"""📎 Uploaded files available ({len(filenames)}): {files_list}

**Location**: `{attachments_dir}/`

**How to use**:
- Read: `read_file('{attachments_dir}/{filenames[0]}')`
- List: `list_files('{attachments_dir}/')`

Files remain available throughout the conversation."""
            logger.info(f"[LangChain] Received {len(uploaded_files_encoded)} pre-encoded file(s)")

    # Handle asset-backed files (persisted in R2, sent as asset IDs by frontend)
    # This covers the case where File objects aren't available (page reload, pre-upload)
    workspace_assets_raw = data.get("workspace_assets", [])
    logger.info(f"[LangChain] workspace_assets_raw={workspace_assets_raw}, enable_file_tools={enable_file_tools}, chat_id={chat_id}")
    if isinstance(workspace_assets_raw, str):
        try:
            workspace_assets_raw = json.loads(workspace_assets_raw)
        except (json.JSONDecodeError, ValueError):
            workspace_assets_raw = []

    MAX_ASSET_SIZE = 25 * 1024 * 1024  # 25MB limit per file

    if workspace_assets_raw and enable_file_tools and chat_id:
        import base64
        import uuid as uuid_mod
        import httpx
        import asyncio
        from workspaces.models import Asset
        from workspaces.services.asset_storage import get_asset_storage_service

        # Validate asset IDs as UUIDs
        valid_asset_ids = []
        asset_filename_map = {}
        for wa in workspace_assets_raw:
            aid = wa.get("asset_id", "")
            try:
                uuid_mod.UUID(str(aid))
                valid_asset_ids.append(str(aid))
                asset_filename_map[str(aid)] = wa.get("filename", "unknown")
            except (ValueError, AttributeError):
                logger.warning(f"[LangChain] Invalid asset ID in workspace_assets: {aid}")

        if valid_asset_ids:
            storage = get_asset_storage_service()
            assets = Asset.objects.filter(id__in=valid_asset_ids, user=request.user)
            assets_map = {str(a.id): a for a in assets}

            auth_header_assets = request.META.get('HTTP_AUTHORIZATION', '')
            auth_token_assets = auth_header_assets[7:] if auth_header_assets.startswith('Bearer ') else None
            orchestrator_url = "http://orchestrator:8003"

            # Pre-download asset content from R2 (sync ORM/storage, before async loop)
            asset_payloads = []  # list of (filename, content_b64, path)
            for aid in valid_asset_ids:
                asset = assets_map.get(aid)
                if not asset:
                    logger.warning(f"[LangChain] Asset {aid} not found or not owned by user")
                    continue
                if asset.size_bytes and asset.size_bytes > MAX_ASSET_SIZE:
                    logger.warning(f"[LangChain] Asset {asset.filename} too large ({asset.size_bytes} bytes), skipping workspace copy")
                    continue
                content_bytes = storage.retrieve_asset(asset)
                if not content_bytes:
                    logger.warning(f"[LangChain] Could not retrieve asset {aid}")
                    continue
                filename = asset_filename_map.get(aid, asset.filename)
                content_b64 = base64.b64encode(content_bytes).decode('utf-8')
                path = f"attachments/{filename}"
                asset_payloads.append((filename, content_b64, path))

            asset_copied_filenames = []

            if asset_payloads:
                async def copy_assets_to_workspace():
                    """Copy asset files to sandbox attachments folder"""
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        for filename, content_b64, path in asset_payloads:
                            try:
                                response = await client.post(
                                    f"{orchestrator_url}/fs/write",
                                    json={
                                        "path": path,
                                        "content": content_b64,
                                        "user_id": str(request.user.id),
                                        "conversation_id": conversation_id,
                                        "chat_id": chat_id,
                                        "sync_mode": True,
                                        "is_base64": True,
                                    },
                                    headers={"Authorization": f"Bearer {auth_token_assets}"},
                                )
                                if response.status_code == 200:
                                    asset_copied_filenames.append(filename)
                                    logger.info(f"[LangChain] Copied asset to workspace: {path}")
                                else:
                                    logger.error(f"[LangChain] Failed to copy asset {filename}: {response.status_code}")
                            except Exception as e:
                                logger.error(f"[LangChain] Error copying asset {filename}: {e}")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(copy_assets_to_workspace())
                finally:
                    loop.close()

            # Merge copied asset filenames into context message
            if asset_copied_filenames:
                attachments_dir = f"/workspace/chat-{chat_id}/attachments"
                if files_context_message:
                    # Append to existing context (from request.FILES or check_existing_files)
                    files_context_message += f"\n\nAdditional files from attachments: {', '.join(asset_copied_filenames)} (in `{attachments_dir}/`)"
                else:
                    files_context_message = f"""📎 Uploaded files available ({len(asset_copied_filenames)}): {', '.join(asset_copied_filenames)}

**Location**: `{attachments_dir}/`

**How to use**:
- Read: `read_file('{attachments_dir}/{asset_copied_filenames[0]}')`
- List: `list_files('{attachments_dir}/')`

Files remain available throughout the conversation."""
                logger.info(f"[LangChain] Copied {len(asset_copied_filenames)} asset(s) to workspace")

    # Enrich the last user message with files context if needed
    if files_context_message and messages and enable_file_tools:
        # Find the last user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                # Prepend the files context to the user message
                original_content = messages[i].get("content", "")
                messages[i]["content"] = f"{files_context_message}\n\n{original_content}"
                logger.info("[LangChain] Enriched user message with files context")
                break

    # Extract JWT token
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    auth_token = auth_header[7:] if auth_header.startswith('Bearer ') else None

    # API key + endpoint are resolved below (after the model-capability
    # check) via resolve_endpoint, so provider-scoped BYOK keys can route
    # eligible chat models directly to the provider.

    # Use wait_if_needed for rate limiting (like the other endpoints)
    project_id = str(data.get("project_id")) if data.get("project_id") else None
    try:
        rate_limiter.wait_if_needed(model, project_id=project_id, max_wait=10.0)
    except Exception as e:
        logger.error(f"[LangChain] Rate limit error: {e}")
        error_response = {
            "error": "Too many requests. Please wait a moment and try again."
        }
        return StreamingHttpResponse(
            iter([f"event: error\ndata: {json.dumps(error_response)}\n\n"]),
            content_type='text/event-stream'
        )

    # Check model capabilities BEFORE creating agent
    # If model doesn't support function calling, disable all tool-related features
    model_obj = None
    supports_functions = True  # Default to True if catalog lookup fails
    output_modalities = ["text"]  # Default to text only
    try:
        catalog = CatalogService()
        model_obj = catalog.get_model(model)
        if model_obj:
            supports_functions = model_obj.get("supports_functions", True)
            output_modalities = model_obj.get("output_modalities", ["text"])
            if not supports_functions:
                # Model doesn't support function calling - disable all tool features
                if enable_file_tools or enable_brave_search or enable_google_maps or enable_mcp_tools:
                    logger.warning(f"[LangChain] Model {model} does not support function calling. Disabling tools (file_tools={enable_file_tools}, brave_search={enable_brave_search}, google_maps={enable_google_maps}, mcp_tools={enable_mcp_tools})")
                    enable_file_tools = False
                    enable_brave_search = False
                    enable_google_maps = False
                    enable_mcp_tools = False
            # Log if model supports image generation
            if "image" in output_modalities:
                logger.info(f"[LangChain] Model {model} supports image generation (output_modalities: {output_modalities})")
    except Exception as e:
        logger.warning(f"[LangChain] Failed to check model capabilities: {e}")

    # Resolve max_tokens using model limits from the catalog
    # The max_tokens parameter is for OUTPUT tokens, not total context
    FALLBACK_MAX_OUTPUT_TOKENS = 16384  # Fallback when model info unavailable
    if model_obj:
        model_context_length = model_obj.get("max_tokens") or 128000
        model_max_completion = model_obj.get("max_completion_tokens")
        if model_max_completion:
            # Model has explicit max completion tokens - use it
            max_tokens = model_max_completion
        else:
            # No explicit limit - use half the context as a safe ceiling
            max_tokens = model_context_length // 2
        logger.info(f"[LangChain] Using model max_tokens={max_tokens} (model_max_completion={model_max_completion}, context={model_context_length})")
    else:
        max_tokens = max(max_tokens, FALLBACK_MAX_OUTPUT_TOKENS)
        logger.warning(f"[LangChain] No model info, using max_tokens={max_tokens}")

    # Load MCP tools if enabled
    mcp_tools_list = None
    mention_priority_prompt = None
    forced_tool_name = None
    media_tool_params = None
    if enable_mcp_tools:
        try:
            from mcp.registry import get_registry
            registry = get_registry()
            mcp_tools_list = registry.get_available_tools_sync(request.user)
            if mcp_tools_list:
                logger.info(f"[LangChain] Loaded {len(mcp_tools_list)} MCP tools for user {request.user.id}")

                # Parse @mentions from user messages and build priority prompt
                try:
                    from .mention_parser import extract_mentions_from_messages, build_mention_priority_prompt, get_forced_tool_choice, extract_media_params
                    mentions = extract_mentions_from_messages(messages)
                    if mentions:
                        logger.info(f"[LangChain] Parsed {len(mentions)} @mention(s): {[m.full_name for m in mentions]}")
                        # Debug: log available tools and their server names
                        available_servers = set()
                        for tool in mcp_tools_list:
                            server = getattr(tool, 'server', None)
                            if server:
                                available_servers.add(server.name)
                        logger.info(f"[LangChain] Available MCP servers: {list(available_servers)}")

                        # Check if user explicitly selected a coding agent tool (force it)
                        forced_tool_name = get_forced_tool_choice(mentions)
                        if forced_tool_name:
                            logger.info(f"[LangChain] Will force tool_choice for: {forced_tool_name}")

                        # Extract media tool params if force-calling a media tool
                        media_tool_params = None
                        if forced_tool_name in ('generate_image', 'generate_video', 'animate_image', 'upscale_video', 'animate_character'):
                            last_user_msg = next((m for m in reversed(messages) if m.get('role') == 'user'), None)
                            if last_user_msg:
                                content = last_user_msg.get('content', '')
                                if isinstance(content, list):
                                    content = ' '.join(p.get('text', '') for p in content if isinstance(p, dict))
                                media_tool_params = extract_media_params(content)
                                if media_tool_params:
                                    logger.info(f"[LangChain] Extracted media tool params: {media_tool_params}")

                        mention_priority_prompt = build_mention_priority_prompt(mentions, mcp_tools_list)
                        if mention_priority_prompt:
                            logger.info(f"[LangChain] Built mention priority prompt for {len(mentions)} mention(s)")
                        else:
                            logger.warning("[LangChain] Mentions parsed but no valid priority prompt built (server/tool not found)")
                except Exception as e:
                    logger.warning(f"[LangChain] Failed to parse @mentions: {e}", exc_info=True)
            else:
                logger.warning(f"[LangChain] MCP enabled but no tools found for user {request.user.id}")
        except Exception as e:
            logger.error(f"[LangChain] Failed to load MCP tools: {e}")

    logger.info(f"[LangChain] Creating agent: model={model}, max_tokens={max_tokens}, file_tools={enable_file_tools}, mcp_tools={enable_mcp_tools}, reasoning={enable_reasoning}, reasoning_effort={reasoning_effort}, reasoning_max_tokens={reasoning_max_tokens}")

    # Get model metadata for file tracking
    model_metadata = None
    if enable_file_tools and model_obj:
        try:
            # model_obj is a dict, not an object
            model_name = model_obj.get("name")
            model_id = model_obj.get("id")
            provider = model_obj.get("provider")

            # Generate icon slugs using the same functions used elsewhere in the app
            model_icon_slug = get_model_icon_slug(model_id, model_name)
            provider_icon_slug = get_provider_icon_slug(provider)

            model_metadata = {
                "model_name": model_name,
                "model_id": model_id,
                "provider": provider,
                "model_icon_slug": model_icon_slug,
                "model_icon_url": None,  # Not needed with slugs
                "provider_icon_slug": provider_icon_slug,
                "provider_icon_url": None,  # Not needed with slugs
                "message_id": message_id  # Frontend can pass this if available
            }
            logger.info(f"[LangChain] Model metadata: {model_metadata}")
        except Exception as e:
            logger.warning(f"[LangChain] Failed to get model metadata: {e}")

    # Create agent (passes V2 params for tool discovery when enabled)
    model_display_name = model_obj.get("name") if model_obj else None

    # Fetch global user instructions from preferences service
    global_instructions = get_user_instructions(
        user_id=str(request.user.id),
        auth_token=auth_token or ""
    )

    # Fetch chat-specific instructions from database
    chat_instructions = get_chat_instructions(
        chat_id=chat_id,
        user_id=str(request.user.id)
    )

    # Build effective system prompt, combining:
    # 1. Global user instructions (if enabled)
    # 2. Chat-specific instructions (based on mode: append or override)
    # 3. Custom system prompt from chat
    # 4. @mention priority instructions
    effective_system_prompt = system_prompt

    # Build user instructions section
    instructions_parts = []

    # Check if chat instructions override global
    if chat_instructions['content'] and chat_instructions['mode'] == 'override':
        # Chat instructions override global - only use chat instructions
        instructions_parts.append(chat_instructions['content'])
        logger.info(f"[LangChain] Using chat instructions (override mode, {len(chat_instructions['content'])} chars)")
    else:
        # Append mode or no chat instructions - use global + chat
        if global_instructions['enabled'] and global_instructions['content']:
            instructions_parts.append(global_instructions['content'])
            logger.info(f"[LangChain] Added global instructions ({len(global_instructions['content'])} chars)")

        if chat_instructions['content']:
            instructions_parts.append(chat_instructions['content'])
            logger.info(f"[LangChain] Added chat instructions (append mode, {len(chat_instructions['content'])} chars)")

    # Combine all instructions into one section with prompt injection protection
    if instructions_parts:
        from conversations.prompt_protection import wrap_instructions_safely
        combined_instructions = "\n\n".join(instructions_parts)
        # Apply sanitization and safe wrapping to prevent prompt injection
        user_instructions_section = wrap_instructions_safely(combined_instructions)
        if effective_system_prompt:
            effective_system_prompt = f"{user_instructions_section}\n\n{effective_system_prompt}"
        else:
            effective_system_prompt = user_instructions_section

    # Add @mention priority instructions
    if mention_priority_prompt:
        if effective_system_prompt:
            effective_system_prompt = f"{effective_system_prompt}\n\n{mention_priority_prompt}"
        else:
            effective_system_prompt = mention_priority_prompt
        logger.info("[LangChain] Added mention priority prompt to system prompt")

    # Resolve API key + endpoint for the chat model (provider-scoped BYOK).
    # Image-capable chat models always stay on OpenRouter (V1 scope), so
    # they resolve without a model_id.
    from llm.services.api_key_resolver import resolve_endpoint
    byok_model_id = model if "image" not in output_modalities else None
    try:
        api_key, chat_base_url, _chat_origin, chat_provider_slug = resolve_endpoint(
            user=request.user, model_id=byok_model_id,
        )
    except ValueError:
        # No key anywhere — preserve the previous failure mode (agent
        # construction fails downstream exactly as before).
        api_key, chat_base_url, chat_provider_slug = None, None, None

    agent = LangChainStreamingAgent(
        model=model,
        api_key=api_key,
        base_url=chat_base_url,
        provider_slug=chat_provider_slug,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_file_tools=enable_file_tools,
        enable_brave_search=enable_brave_search,
        enable_google_maps=enable_google_maps,
        enable_image_generation=enable_image_generation,
        enable_video_generation=enable_video_generation,
        enable_reasoning=enable_reasoning,
        enable_mcp_tools=enable_mcp_tools,
        enable_voice_mode=enable_voice_mode,
        enable_sparks=enable_sparks,
        enable_knowledge_base=enable_knowledge_base,
        mcp_tools=mcp_tools_list,
        custom_prompt=effective_system_prompt,
        reasoning_effort=reasoning_effort,  # For effort-based models
        reasoning_max_tokens=reasoning_max_tokens,  # For token-limited models
        output_modalities=output_modalities,  # For image generation models
        model_name=model_display_name,  # For system prompt identification
        # V2 tool discovery params
        user_id=str(request.user.id),
        conversation_id=conversation_id,
        chat_id=chat_id,
        # User info for system prompt
        user_first_name=getattr(request.user, 'first_name', None),
        user_last_name=getattr(request.user, 'last_name', None),
        user_email=getattr(request.user, 'email', None),
        # Spark auto-fix
        spark_fix_request=spark_fix_request,
        # Spark ignite
        spark_ignite_request=spark_ignite_request,
        # Forced tool choice (from @mention)
        forced_tool_name=forced_tool_name,
        # Media tool parameters (from @generate_image [params] or @generate_video [params])
        media_tool_params=media_tool_params,
    )

    # Define async generator
    async def generate_sse():
        nonlocal agent, model

        MAX_REROUTE_ATTEMPTS = 2
        excluded_models = []
        current_agent = agent
        current_model = model

        for attempt in range(1 + MAX_REROUTE_ATTEMPTS):
            rerouted = False
            try:
                # Emit Sterna routing info before streaming content
                if attempt == 0 and sterna_resolution:
                    sterna_event = {
                        "resolved_model": sterna_resolution.resolved_model_id,
                        "resolved_model_name": sterna_resolution.resolved_model_name,
                        "score": sterna_resolution.final_score,
                        "tier": sterna_resolution.tier,
                        "reason": sterna_resolution.reason,
                        "cost_tier": sterna_resolution.cost_tier,
                    }
                    yield f"event: sterna_route\ndata: {json.dumps(sterna_event)}\n\n"

                async for event in current_agent.astream_chat(
                    messages=messages,
                    user_id=str(request.user.id),
                    conversation_id=conversation_id,
                    chat_id=chat_id,
                    auth_token=auth_token or "",
                    model_metadata=model_metadata,
                    uploaded_files=uploaded_files_encoded if uploaded_files_encoded else None
                ):
                    event_type = event.get("event", "message")
                    event_data = event.get("data", {})

                    # Detect 429 rate limit errors — reroute if possible
                    if event_type == "error":
                        error_msg = str(event_data.get("error", ""))
                        if "429" in error_msg and attempt < MAX_REROUTE_ATTEMPTS:
                            excluded_models.append(current_model)
                            from llm.smart_router.router import SmartRouter
                            router = SmartRouter()
                            alt_model = router.reroute_on_rate_limit(
                                failed_model=current_model,
                                messages=messages,
                                conversation_id=conversation_id,
                                user=request.user,
                                excluded_models=excluded_models,
                            )
                            if alt_model:
                                logger.info(
                                    f"[Sterna] Rerouting 429: {current_model} -> {alt_model} "
                                    f"(attempt {attempt + 1}/{MAX_REROUTE_ATTEMPTS})"
                                )
                                # Emit reroute event so frontend knows
                                yield f"event: sterna_reroute\ndata: {json.dumps({'from_model': current_model, 'to_model': alt_model})}\n\n"
                                # Create new agent with the alternative model
                                current_model = alt_model
                                # Re-resolve endpoint for the alternative
                                # model — its BYOK provider may differ.
                                reroute_model_id = (
                                    current_model
                                    if "image" not in output_modalities
                                    else None
                                )
                                try:
                                    (
                                        alt_api_key,
                                        alt_base_url,
                                        _alt_origin,
                                        alt_provider_slug,
                                    ) = resolve_endpoint(
                                        user=request.user,
                                        model_id=reroute_model_id,
                                    )
                                except ValueError:
                                    alt_api_key = api_key
                                    alt_base_url = chat_base_url
                                    alt_provider_slug = chat_provider_slug
                                current_agent = LangChainStreamingAgent(
                                    model=current_model,
                                    api_key=alt_api_key,
                                    base_url=alt_base_url,
                                    provider_slug=alt_provider_slug,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                    enable_file_tools=enable_file_tools,
                                    enable_brave_search=enable_brave_search,
                                    enable_google_maps=enable_google_maps,
                                    enable_image_generation=enable_image_generation,
                                    enable_video_generation=enable_video_generation,
                                    enable_reasoning=enable_reasoning,
                                    enable_mcp_tools=enable_mcp_tools,
                                    enable_voice_mode=enable_voice_mode,
                                    enable_sparks=enable_sparks,
                                    enable_knowledge_base=enable_knowledge_base,
                                    mcp_tools=mcp_tools_list,
                                    custom_prompt=effective_system_prompt,
                                    reasoning_effort=reasoning_effort,
                                    reasoning_max_tokens=reasoning_max_tokens,
                                    output_modalities=output_modalities,
                                    model_name=current_model.split('/')[-1].replace('-', ' ').title(),
                                    user_id=str(request.user.id),
                                    conversation_id=conversation_id,
                                    chat_id=chat_id,
                                    user_first_name=getattr(request.user, 'first_name', None),
                                    user_last_name=getattr(request.user, 'last_name', None),
                                    user_email=getattr(request.user, 'email', None),
                                    spark_fix_request=spark_fix_request,
                                    spark_ignite_request=spark_ignite_request,
                                    forced_tool_name=forced_tool_name,
                                    media_tool_params=media_tool_params,
                                )
                                # Update outer agent reference for cleanup
                                agent = current_agent
                                rerouted = True
                                break  # Break inner for-loop, outer loop retries

                    yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

                if not rerouted:
                    break  # Streaming completed normally, exit retry loop

            except Exception as e:
                logger.error(f"[LangChain] Stream error: {e}", exc_info=True)
                yield f"event: error\ndata: {json.dumps(error_payload(e))}\n\n"
                break  # Don't retry on non-429 exceptions

    # For ASGI (Uvicorn), we need to use async streaming
    # StreamingHttpResponse accepts async iterators when running under ASGI
    async def async_streaming_wrapper():
        """Async wrapper that handles cancellation and cleanup"""
        client_disconnected = False
        max_chunks_after_cancel = 5
        chunks_after_cancel = 0

        try:
            async for chunk in generate_sse():
                # If client disconnected, we're in cleanup mode - limit chunks
                if client_disconnected:
                    chunks_after_cancel += 1
                    logger.debug(f"[LangChain] Sending cleanup chunk {chunks_after_cancel}/{max_chunks_after_cancel}")
                    if chunks_after_cancel >= max_chunks_after_cancel:
                        logger.warning("[LangChain] Max cleanup chunks reached - stopping")
                        break
                yield chunk
        except GeneratorExit:
            # Client disconnected (abort/stop button clicked)
            logger.warning("[LangChain] Client disconnected - cancelling agent")
            client_disconnected = True
            agent.cancel()
            # Server-side settlement: bill the true cost of this aborted
            # stream even if the client never PATCHes the stopped message.
            # Skipped when the final aggregate row was already recorded
            # (disconnect raced the stream end). Iterations already billed
            # inline (Direct Client path) are skipped by the task's
            # request_id idempotency guard.
            # Provider-scoped BYOK streams bypass OpenRouter entirely:
            # their generation ids are provider-native and cannot be
            # settled against OpenRouter's /generation endpoint (and the
            # user's own provider account already paid) — skip.
            try:
                if (
                    not getattr(agent, "final_usage_recorded", False)
                    and getattr(agent, "is_openrouter", True)
                ):
                    from llm.tasks import enqueue_abort_settlement
                    enqueue_abort_settlement(
                        user_id=str(request.user.id),
                        generation_ids=list(
                            getattr(agent, "all_generation_ids", []) or []
                        ),
                        model_id=agent.model,
                        chat_id=chat_id or "",
                    )
            except Exception:
                logger.error(
                    "billing.abort_settlement_hook_failed", exc_info=True
                )
        except Exception as e:
            logger.error(f"[LangChain] async_streaming_wrapper error: {e}")
            agent.cancel()
        finally:
            # Close HTTP client if file tools were used
            if agent.file_tools_context:
                try:
                    await agent.file_tools_context.close()
                except Exception as e:
                    logger.warning(f"[LangChain] Error closing file tools context: {e}")
            logger.info("[LangChain] Stream completed")

    return StreamingHttpResponse(
        async_streaming_wrapper(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


# ===========================
# Google Maps Proxy Endpoints
# ===========================
# These endpoints proxy requests to the Google Maps service for frontend display purposes.
# This keeps all API calls going through the backend gateway while keeping display-only
# data (like photos) separate from model context.

GOOGLE_MAPS_SERVICE_URL = os.environ.get("GOOGLE_MAPS_SERVICE_URL", "http://google-maps:8005")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def google_maps_place_photo(request):
    """
    Proxy endpoint for fetching place photos from Google Maps service.
    Used by frontend for display purposes - not sent to models.

    Authenticated + metered: every call hits the paid Google Places API
    (Text Search + photo), so the caller must be a known user and the
    request is billed as GOOGLE_MAPS/'places_photo' against their quota.
    Only whitelisted payload fields are forwarded upstream.
    """
    # Whitelist + validate the forwarded payload (never forward raw
    # client JSON to the internal service).
    data = request.data if isinstance(request.data, dict) else {}
    query = data.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 256:
        return Response(
            {"success": False, "error": "Invalid 'query'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    payload = {"query": query.strip()}
    for field, lo, hi in (("latitude", -90, 90), ("longitude", -180, 180)):
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or not (lo <= value <= hi):
            return Response(
                {"success": False, "error": f"Invalid '{field}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload[field] = value
    max_width = data.get("max_width", 400)
    if not isinstance(max_width, int) or not (1 <= max_width <= 1600):
        max_width = 400
    payload["max_width"] = max_width

    # Pre-check quota through the same GOOGLE_MAPS metering path as the
    # chat tools (google_maps_tools._check_quota, sync flavor here).
    from usage_quota.billing.service import get_billing_service
    from usage_quota.billing.operations import BillableOperation
    from usage_quota.exceptions import (
        FeatureNotAvailableException,
        QuotaExceededException,
    )
    from usage_quota.models import FeatureType, ServiceType
    from usage_quota.services.cost_calculator import get_cost_calculator

    endpoint = "places_photo"
    try:
        estimated_cost = get_cost_calculator().calculate_google_maps_cost(endpoint)
        get_billing_service().check_quota(
            user=request.user,
            service=ServiceType.GOOGLE_MAPS,
            estimated_cost=estimated_cost,
            feature=FeatureType.CHAT,
            feature_name='maps_invocation',
        )
    except (FeatureNotAvailableException, QuotaExceededException) as exc:
        return Response(
            {"success": False, "error": exc.code},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    except Exception:
        logger.error("[GoogleMapsProxy] quota pre-check failed", exc_info=True)

    try:
        with httpx_sync.Client(timeout=10.0) as client:
            response = client.post(
                f"{GOOGLE_MAPS_SERVICE_URL}/places/search-photo",
                json=payload
            )
        body = response.json()
        # Post-record on success only (mirrors google_maps_tools._record).
        if response.status_code == 200 and isinstance(body, dict) and body.get("success"):
            try:
                op = BillableOperation(
                    service=ServiceType.GOOGLE_MAPS,
                    feature=FeatureType.CHAT,
                    model_id=endpoint,
                    request_count=1,
                )
                get_billing_service().record_usage(
                    request.user, op, billing_origin='platform',
                )
            except Exception:
                logger.error(
                    "[GoogleMapsProxy] billing record_usage failed",
                    exc_info=True,
                )
        return Response(body, status=response.status_code)
    except httpx_sync.TimeoutException:
        return Response({"success": False, "error": "Request timed out. Please try again."}, status=504)
    except Exception as e:
        logger.error(f"[GoogleMapsProxy] Error: {e}")
        return Response({"success": False, "error": "An error occurred. Please try again."}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_generation_usage(request, generation_id):
    """Query OpenRouter for exact usage/cost of a generation (even interrupted ones).

    OpenRouter takes ~15-20 seconds to finalize generation data after stream completion.
    This endpoint retries with backoff until the data is available.
    """
    import time
    from llm.services.api_key_resolver import get_api_key_for_user

    api_key = get_api_key_for_user(request.user)
    if not api_key:
        return Response({"error": "No API key configured"}, status=400)

    # Retry with backoff: OpenRouter needs time to finalize generation data
    max_retries = 7
    delays = [2, 3, 3, 4, 4, 5, 5]  # Total wait: ~26 seconds

    try:
        with httpx_sync.Client(timeout=10.0) as client:
            for attempt in range(max_retries):
                response = client.get(
                    f"https://openrouter.ai/api/v1/generation?id={generation_id}",
                    headers={"Authorization": f"Bearer {api_key}"}
                )

                if response.status_code == 200:
                    gen_data = response.json().get("data", {})
                    prompt_tokens = gen_data.get("tokens_prompt", 0)
                    completion_tokens = gen_data.get("tokens_completion", 0)

                    return Response({
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens,
                        },
                        "cost": float(gen_data.get("total_cost", 0)),
                        "model": gen_data.get("model"),
                        "generation_id": generation_id,
                    })

                if response.status_code == 404 and attempt < max_retries - 1:
                    # Generation not finalized yet, wait and retry
                    time.sleep(delays[attempt])
                    continue

                # Non-404 error or exhausted retries
                return Response(
                    {"error": f"OpenRouter returned {response.status_code}"},
                    status=502
                )

    except httpx_sync.TimeoutException:
        return Response({"error": "OpenRouter timeout"}, status=504)
    except Exception as e:
        logger.error(f"[GenerationUsage] Error querying OpenRouter: {e}")
        return Response({"error": str(e)}, status=500)
