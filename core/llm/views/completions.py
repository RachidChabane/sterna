"""
Views for OpenRouter completions.
"""

import json
import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse

from ..client import OpenRouterClient
from ..rate_limiter import RateLimiter
from ..exceptions import ContextLimitExceededException
from ..error_messages import error_payload, get_user_friendly_error
from ..serializers import (
    CompletionRequestSerializer,
    CompletionResponseSerializer,
    FallbackCompletionRequestSerializer,
    CostEstimateRequestSerializer,
    CostEstimateResponseSerializer,
    BatchCostEstimateRequestSerializer,
    BatchCostEstimateResponseSerializer,
    RateLimitInfoSerializer,
    UsageStatsSerializer,
)
from ..services.cost_estimation_service import (
    estimate_single_cost,
    estimate_batch_cost as estimate_batch_cost_service,
)

logger = logging.getLogger(__name__)


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

        # The turn itself runs on the agent core: see
        # llm.agent_service.v1_endpoint for the tools it offers, the
        # calls it stops on, and the frames it speaks.
        from llm.agent_service.v1_endpoint import v1_streaming_response
        return v1_streaming_response(request=request, data=data)

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

        response_data = estimate_single_cost(
            data["model_id"], data["prompt_tokens"], data["completion_tokens"]
        )

        response_serializer = CostEstimateResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data)

    @action(detail=False, methods=["post"], url_path='estimate-batch-cost')
    def estimate_batch_cost(self, request):
        """Estimate cost for multiple models.

        Prefer `typed_text` + `files_text` for accurate estimation. Falls back to
        `prompt_text` + optional `estimated_completion_tokens` for backward compatibility.
        """
        serializer = BatchCostEstimateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        response_data = estimate_batch_cost_service(data)

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


