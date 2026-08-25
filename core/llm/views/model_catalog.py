"""
Views for the OpenRouter model catalog.
"""

import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.cache import cache
from django.utils.decorators import method_decorator

from exceptions import apply_ratelimit

from ..models import ModelCatalog
from ..client import OpenRouterClient
from ..catalog_service import CatalogService
from ..utils import exclude_blacklisted_providers, is_provider_blacklisted
from ..serializers import (
    ModelCatalogSerializer,
    ModelAvailabilitySerializer,
    CatalogRefreshResponseSerializer,
    ModelTierSerializer,
    ModelFilterSerializer,
    ModelComparisonRequestSerializer,
)
from ..constants import MODEL_TIERS
from ..comparison_service import ModelComparisonService
from ..comparison_config import ComparisonConstraints, ComparisonPriorities, CapabilityWeights
from ..services.model_catalog_query import build_model_list_response, models_with_icons_queryset

logger = logging.getLogger(__name__)


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

        response_data = build_model_list_response(
            filters, request.query_params, self.get_queryset()
        )
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
        icon_queryset = models_with_icons_queryset(base_queryset)

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

