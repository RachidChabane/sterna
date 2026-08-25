"""
OpenRouter client for unified LLM access.
"""

import time
import logging
import requests
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from decimal import Decimal

from django.conf import settings

from .exceptions import (
    OpenRouterException,
    RateLimitException,
    InvalidResponseException,
    ContextLimitExceededException,
)
from usage_quota.exceptions import QuotaExceededException
from usage_quota.models import ServiceType, FeatureType
from usage_quota.billing import get_billing_service, BillableOperation
from .constants import (
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOP_P,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MAX,
)
from .context_utils import calculate_dynamic_max_tokens
from .error_messages import error_payload
from .reasoning_filter import ReasoningFilter

if TYPE_CHECKING:
    from django.http import HttpRequest
    from authentication.models import User

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """Client for OpenRouter API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        user: Optional['User'] = None,
        request: Optional['HttpRequest'] = None,
        request_source: str = 'unknown',
        model_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize OpenRouter client.

        Args:
            api_key: Explicit API key (highest priority)
            user: User to get key for (uses their personal key if available)
            request: Request to extract user from
            request_source: Source identifier for usage tracking
                (e.g., 'chat', 'voice_room', 'mcp_discovery')
            model_id: Model this client will serve (optional). When given
                and the user has a provider-scoped BYOK key for the
                model's first-party provider, requests are routed
                DIRECTLY to that provider's OpenAI-compatible endpoint.
                When absent, behavior is unchanged (OpenRouter).
            base_url: Explicit base URL override (used together with an
                explicit api_key, e.g. by LangChainStreamingAgent's
                direct client). Defaults to OpenRouter.
        """
        from .services.api_key_resolver import resolve_endpoint
        from .provider_registry import (
            OPENROUTER_BASE_URL,
            is_openrouter_url,
            provider_for_model,
        )
        from usage_quota.constants import BILLING_ORIGIN_PLATFORM

        # Store for usage logging
        self._user = user
        self._request_source = request_source

        # Resolve API key with priority: explicit > user > request > env.
        # When an explicit api_key is passed (tests, mcp_discovery) we can't
        # tell BYOK from system — default to 'platform' so we never undercount.
        if api_key:
            self.api_key = api_key
            self._billing_origin = BILLING_ORIGIN_PLATFORM
            self.base_url = base_url or OPENROUTER_BASE_URL
            # Direct-provider routing only applies with a non-OpenRouter
            # base_url (the caller resolved the endpoint already).
            self._provider_slug = (
                provider_for_model(model_id)
                if not is_openrouter_url(self.base_url)
                else None
            )
        else:
            # Extract user from request if not provided
            if not user and request and hasattr(request, 'user') and request.user.is_authenticated:
                self._user = request.user

            (
                self.api_key,
                self.base_url,
                self._billing_origin,
                self._provider_slug,
            ) = resolve_endpoint(
                user=self._user, request=request, model_id=model_id,
            )

        if not self.api_key:
            raise ValueError("OpenRouter API key is required")

        self._is_openrouter = is_openrouter_url(self.base_url)

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        # OpenRouter-specific attribution headers must NOT be sent to
        # direct provider endpoints.
        if self._is_openrouter:
            self.session.headers.update(
                {
                    "HTTP-Referer": settings.OPENROUTER_SITE_URL,
                    "X-Title": "Sterna",
                }
            )

    # kwargs keys that are OpenRouter extensions and would be rejected by
    # (or are meaningless to) direct provider OpenAI-compatible endpoints.
    OPENROUTER_ONLY_PARAMS = frozenset({
        'plugins', 'transforms', 'route', 'provider', 'models',
        'top_k', 'repetition_penalty', 'min_p', 'top_a',
    })

    def _request_model(self, model: str) -> str:
        """Model id to send upstream.

        Direct-provider calls use the native model name (prefix and any
        ``:variant`` suffix stripped); OpenRouter keeps the full slug.
        """
        if self._provider_slug:
            from .provider_registry import native_model_name
            return native_model_name(model)
        return model

    def _strip_openrouter_only_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Drop OpenRouter-only params when calling a provider directly."""
        if self._is_openrouter:
            return kwargs
        dropped = {k for k in kwargs if k in self.OPENROUTER_ONLY_PARAMS}
        if dropped:
            logger.info(
                f"[BYOK] Dropping OpenRouter-only params for direct "
                f"provider call: {sorted(dropped)}"
            )
        return {k: v for k, v in kwargs.items() if k not in self.OPENROUTER_ONLY_PARAMS}

    def _map_request_source_to_feature(self, request_source: str) -> str:
        """Map request_source to FeatureType for quota tracking.

        Every ``request_source=`` value used when constructing an
        OpenRouterClient should have an entry here, or its UsageLog rows
        fall through to FeatureType.OTHER (mis-categorized in per-feature
        analytics).
        """
        mapping = {
            'chat': FeatureType.CHAT,
            'chat_stream': FeatureType.CHAT,
            'chat_fallback': FeatureType.CHAT,
            'voice_room': FeatureType.VOICE_ROOM,
            'voice_room_generation': FeatureType.VOICE_ROOM,
            'code_session': FeatureType.CODE_SESSION,
            # Code-session optimization pipeline helpers — billed under
            # CODE_SESSION alongside the parent coding-agent run.
            'scout': FeatureType.CODE_SESSION,
            'summarizer': FeatureType.CODE_SESSION,
            'orchestrator': FeatureType.CODE_SESSION,
            'history_pruner': FeatureType.CODE_SESSION,
            'agent_generation': FeatureType.CODE_SESSION,
            'search': FeatureType.SEARCH,
            'consigliere': FeatureType.CONSIGLIERE,
            # Consigliere AI analyzer — billed under CONSIGLIERE, not OTHER.
            'ai_analyzer': FeatureType.CONSIGLIERE,
            'mcp_discovery': FeatureType.OTHER,
            'unknown': FeatureType.OTHER,
        }
        return mapping.get(request_source, FeatureType.OTHER)

    def _check_quota_preflight(
        self,
        model: str,
        estimated_tokens: int = 4000,
    ) -> None:
        """
        Pre-flight quota check before making an API call.

        Args:
            model: Model ID to use
            estimated_tokens: Estimated total tokens for the request

        Raises:
            QuotaExceededException: If user would exceed quota
        """
        if not self._user:
            # No user context - skip quota check (e.g., system calls)
            return

        from usage_quota.services import get_cost_calculator

        billing = get_billing_service()
        cost_calculator = get_cost_calculator()

        # Estimate cost for pre-flight check
        estimated_cost = cost_calculator.estimate_openrouter_cost(
            model_id=model,
            estimated_tokens=estimated_tokens,
        )

        feature = self._map_request_source_to_feature(self._request_source)

        status = billing.check_quota(
            user=self._user,
            service=ServiceType.OPENROUTER,
            estimated_cost=estimated_cost,
            feature=feature,
            assume_origin=self._billing_origin,
        )

        if not status.allowed:
            from usage_quota.messages import format_quota_error_message
            from django.utils import timezone
            from datetime import timedelta

            # Determine limit type and get appropriate values
            limit_type = status.denial_reason or "weekly"
            if limit_type == "session":
                limit_usd = status.session_limit_usd
                used_usd = status.session_used_usd
                remaining_usd = status.session_remaining_usd
                window_end = timezone.now() + timedelta(seconds=status.session_resets_in_seconds)
            else:
                limit_usd = status.weekly_limit_usd
                used_usd = status.weekly_used_usd
                remaining_usd = status.weekly_remaining_usd
                window_end = timezone.now() + timedelta(seconds=status.weekly_resets_in_seconds)

            message = format_quota_error_message(limit_type, window_end)

            raise QuotaExceededException(
                message=message,
                limit_usd=limit_usd,
                used_usd=used_usd,
                remaining_usd=remaining_usd,
                limit_type=limit_type,
            )

    def _log_usage(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        request_id: Optional[str] = None,
    ):
        """Log usage for monitoring and billing via centralized BillingService."""
        if not self._user:
            # No user context - skip usage logging (e.g., system calls)
            logger.debug("Skipping usage logging - no user context")
            return

        feature = self._map_request_source_to_feature(self._request_source)

        # Create billable operation
        operation = BillableOperation(
            service=ServiceType.OPENROUTER,
            feature=feature,
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=Decimal(str(cost_usd)),
            request_id=request_id or '',
        )

        # Record via centralized billing service
        billing = get_billing_service()
        billing.record_usage(self._user, operation, billing_origin=self._billing_origin)

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models from OpenRouter."""
        try:
            response = self._make_request("GET", "/models")
            return response.get("data", [])
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            raise OpenRouterException(f"Failed to list models: {e}")

    def list_providers(self) -> List[Dict[str, Any]]:
        """List available providers from OpenRouter with their policies and capabilities."""
        try:
            response = self._make_request("GET", "/providers")
            return response.get("data", [])
        except Exception as e:
            logger.error(f"Failed to list providers: {e}")
            raise OpenRouterException(f"Failed to list providers: {e}")

    def _requires_cache_control(self, model: str) -> bool:
        """
        Check if model requires explicit cache_control breakpoints.

        Most providers (OpenAI, DeepSeek, Groq) have automatic caching.
        Anthropic and Gemini require explicit cache_control markers.

        See: https://openrouter.ai/docs/guides/best-practices/prompt-caching
        """
        model_lower = model.lower()
        return any(provider in model_lower for provider in ["anthropic", "claude", "gemini", "google"])

    # Provider-specific cache configuration
    # See: https://openrouter.ai/docs/guides/best-practices/prompt-caching
    CACHE_CONFIG = {
        "anthropic": {
            "max_breakpoints": 4,
            "ttl_seconds": 300,
            "min_tokens": 0,
            "strategy": "distribute",  # Distribute breakpoints evenly
        },
        "gemini": {
            "max_breakpoints": 1,  # Only last breakpoint is used
            "ttl_seconds": 300,
            "min_tokens": 4096,
            "strategy": "last",  # Single breakpoint at end of cacheable content
        },
    }

    def _get_cache_config(self, model: str) -> dict | None:
        """Get cache configuration for a model, or None if automatic caching."""
        model_lower = model.lower()
        if "anthropic" in model_lower or "claude" in model_lower:
            return self.CACHE_CONFIG["anthropic"]
        elif "gemini" in model_lower or "google" in model_lower:
            return self.CACHE_CONFIG["gemini"]
        # OpenAI, DeepSeek, Groq, etc. use automatic caching
        return None

    def _apply_cache_control(self, messages: List[Dict], model: str) -> List[Dict]:
        """
        Apply cache_control to message content for providers that need it.

        Provider strategies:
        - Anthropic: Up to 4 breakpoints, distributed evenly through conversation
        - Gemini: Single breakpoint (only last is used), placed at end of static content
        - OpenAI/DeepSeek/Groq: Automatic caching, no config needed

        Args:
            messages: List of messages
            model: Model ID

        Returns:
            Messages with cache_control applied (for supported models)
        """
        config = self._get_cache_config(model)
        if not config:
            # Provider uses automatic caching
            return messages

        total = len(messages)
        if total == 0:
            return messages

        strategy = config["strategy"]
        max_breakpoints = config["max_breakpoints"]

        # Calculate cache positions based on strategy
        if strategy == "last":
            # Gemini: Single breakpoint, place at last static message
            # For agent loops, cache up to the second-to-last message
            # (the last message is the new content being added)
            cache_positions = {max(0, total - 2)} if total > 1 else {0}

        else:  # "distribute" strategy (Anthropic)
            # Always cache system (0) and user task (1)
            cache_positions = {0, 1} if total > 1 else {0}

            history_count = total - 2
            remaining = max_breakpoints - len(cache_positions)

            if history_count > 0 and remaining > 0:
                # Distribute remaining breakpoints evenly through history
                step = history_count // (remaining + 1)
                if step > 0:
                    for i in range(1, remaining + 1):
                        pos = 2 + (step * i) - 1
                        if pos < total:
                            cache_positions.add(pos)

        # Apply cache_control at calculated positions
        # Only apply to messages that can safely be converted to multipart:
        # - System messages: YES
        # - User messages: YES
        # - Assistant messages: NO (may have tool_calls structure)
        # - Tool messages: NO (require tool_call_id field)
        result = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Only apply cache_control to system and user messages
            can_cache = role in ("system", "user")
            should_cache = (
                i in cache_positions and
                can_cache and
                isinstance(content, str) and
                content
            )

            if should_cache:
                result.append({
                    "role": role,
                    "content": [{
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"}
                    }]
                })
            else:
                result.append(msg)

        return result

    def _inject_system_prompt(
        self,
        messages: List[Dict[str, str]],
        enable_mcp_tools: bool = False,
        enable_reasoning: bool = False,
        enable_file_tools: bool = False,
        enable_image_generation: bool = False,
        has_mcp_tools: bool = False,
        mcp_tools: Optional[List] = None,
    ) -> List[Dict[str, str]]:
        """
        Build and inject system prompt based on active features.

        Extracts any existing system message, combines it with capability prompts,
        and injects it back at the start of messages.

        Args:
            messages: Original messages list
            enable_mcp_tools: Whether MCP tools are enabled
            enable_reasoning: Whether extended reasoning is enabled
            enable_file_tools: Whether file manipulation tools are enabled
            enable_image_generation: Whether image generation is enabled
            has_mcp_tools: Whether MCP tools are actually available
            mcp_tools: List of MCP tools (for dynamic prompts)

        Returns:
            Messages list with combined system prompt
        """
        # Lazy import to avoid Django app-loading order issues (see
        # llm/__init__.py docstring).
        from .agent.prompt_assembly import (
            build_direct_completion_system_prompt,
            split_custom_system_prompt,
        )

        custom_prompt, other_messages = split_custom_system_prompt(messages)
        combined_prompt = build_direct_completion_system_prompt(
            custom_prompt=custom_prompt,
            enable_reasoning=enable_reasoning,
            enable_file_tools=enable_file_tools,
            enable_image_generation=enable_image_generation,
            mcp_tools=mcp_tools if (enable_mcp_tools and has_mcp_tools) else None,
        )

        # If we have a system prompt, inject it at the start
        if combined_prompt:
            return [{"role": "system", "content": combined_prompt}] + other_messages
        else:
            return other_messages

    def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        top_p: float = DEFAULT_TOP_P,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        enable_mcp_tools: bool = False,
        enable_reasoning: bool = False,
        enable_file_tools: bool = False,
        enable_image_generation: bool = False,
        has_mcp_tools: bool = False,
        mcp_tools: Optional[List] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate completion using specified model.

        Args:
            model: Model ID to use
            messages: List of messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Top-p sampling parameter
            stream: Whether to stream the response
            tools: Optional list of tools in OpenAI format
            tool_choice: Optional tool choice strategy ("auto", "none", or {"type": "function", "function": {"name": "..."}})
            enable_mcp_tools: Whether MCP tools are enabled
            enable_reasoning: Whether extended reasoning is enabled
            enable_file_tools: Whether file manipulation tools are enabled
            enable_image_generation: Whether image generation is enabled
            has_mcp_tools: Whether MCP tools are actually available
            mcp_tools: List of MCP tools (for dynamic prompts)
            **kwargs: Additional parameters to pass to the API

        Returns:
            Dictionary with content, usage, and cost information

        Raises:
            QuotaExceededException: If user would exceed their usage quota
        """
        # Pre-flight quota check
        self._check_quota_preflight(model, estimated_tokens=max_tokens * 2)

        # Build and inject system prompt based on active features
        messages = self._inject_system_prompt(
            messages,
            enable_mcp_tools=enable_mcp_tools,
            enable_reasoning=enable_reasoning,
            enable_file_tools=enable_file_tools,
            enable_image_generation=enable_image_generation,
            has_mcp_tools=has_mcp_tools,
            mcp_tools=mcp_tools,
        )

        # Apply cache_control for Anthropic/Gemini models
        # This enables prompt caching to reduce costs on repeated calls.
        # cache_control is an OpenRouter/Anthropic message extension — do
        # not send it on direct provider OpenAI-compatible calls.
        if self._is_openrouter:
            messages = self._apply_cache_control(messages, model)

        # Calculate dynamic max_tokens based on model's context limit and prompt size
        # This prevents context overflow errors by adjusting max_tokens automatically
        actual_max_tokens = calculate_dynamic_max_tokens(
            model_id=model,
            messages=messages,
            configured_max_tokens=max_tokens
        )

        # Build reasoning object if enabled (OpenRouter native reasoning support)
        reasoning_obj = None
        if enable_reasoning:
            from .reasoning_options import build_reasoning_option

            reasoning_obj = build_reasoning_option(
                model=model,
                reasoning_effort=kwargs.pop("reasoning_effort", None),
                reasoning_max_tokens=kwargs.pop("reasoning_max_tokens", None),
            )

        payload = {
            "model": self._request_model(model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": actual_max_tokens,
            "top_p": top_p,
            "stream": stream,
            **self._strip_openrouter_only_kwargs(kwargs),
        }

        # Add reasoning object if enabled (OpenRouter-specific parameter —
        # direct providers would reject it)
        if reasoning_obj and self._is_openrouter:
            payload["reasoning"] = reasoning_obj

        # Add tools if provided
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        # Log tools info at INFO level for debugging tool calls
        if tools:
            logger.info(f"[OpenRouter] Sending {len(tools)} tools to model {model}")
            logger.debug(f"[OpenRouter] Full payload: {payload}")
        else:
            logger.debug(f"Sending completion request to OpenRouter - Model: {model}")

        try:
            response = self._make_request("POST", "/chat/completions", json=payload)

            # Extract response and usage
            if "choices" in response and response["choices"]:
                message = response["choices"][0].get("message", {})
                content = message.get("content", "")
                tool_calls = message.get("tool_calls", [])
                # Extract reasoning/thinking content if present (from extended thinking)
                reasoning = message.get("reasoning", "") or message.get("reasoning_content", "")

                # Log tool calls from response
                if tools:
                    finish_reason_raw = response["choices"][0].get("finish_reason", "unknown")
                    logger.info(f"[OpenRouter] Response finish_reason={finish_reason_raw}, tool_calls={len(tool_calls)}")
                usage = response.get("usage", {})

                # Log cache effectiveness for monitoring
                prompt_tokens = usage.get("prompt_tokens", 0)
                cache_discount = response.get("cache_discount", 0)
                cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
                if cache_discount > 0 or cached_tokens > 0:
                    logger.info(f"[OpenRouter Cache] prompt_tokens={prompt_tokens}, cached_tokens={cached_tokens}, cache_discount={cache_discount}")
                costs = self._calculate_cost(model, usage)

                # Extract finish_reason from the response
                finish_reason = response["choices"][0].get("finish_reason", "stop")

                result = {
                    "content": content,
                    # Direct providers return the native model name — keep
                    # the full slug so pricing lookups and frontend display
                    # stay consistent.
                    "model": response.get("model", model) if self._is_openrouter else model,
                    "finish_reason": finish_reason,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    "cost": costs["total_cost"],
                    "prompt_cost": costs["prompt_cost"],
                    "completion_cost": costs["completion_cost"],
                }

                # Include tool_calls if present
                if tool_calls:
                    result["tool_calls"] = tool_calls

                # Include reasoning if present
                if reasoning:
                    result["reasoning"] = reasoning

                # Log usage for monitoring
                self._log_usage(
                    model_id=result["model"],
                    prompt_tokens=result["usage"]["prompt_tokens"],
                    completion_tokens=result["usage"]["completion_tokens"],
                    cost_usd=float(result["cost"]),
                )

                return result
            else:
                raise InvalidResponseException(
                    "Invalid response format from OpenRouter"
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for model {model}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                try:
                    logger.error(f"Response body: {e.response.text}")
                except Exception:
                    logger.error("Could not read response body")
            raise OpenRouterException(f"Request failed: {e}")

    def complete_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        top_p: float = DEFAULT_TOP_P,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        enable_mcp_tools: bool = False,
        enable_reasoning: bool = False,
        enable_file_tools: bool = False,
        enable_image_generation: bool = False,
        has_mcp_tools: bool = False,
        mcp_tools: Optional[List] = None,
        output_modalities: Optional[List[str]] = None,
        **kwargs,
    ):
        """
        Generate completion with streaming (yields chunks as they arrive).

        Args:
            model: Model ID to use
            messages: List of messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Top-p sampling parameter
            tools: Optional list of tools in OpenAI format
            enable_mcp_tools: Whether MCP tools are enabled
            enable_reasoning: Whether extended reasoning is enabled
            enable_file_tools: Whether file manipulation tools are enabled
            enable_image_generation: Whether image generation is enabled
            has_mcp_tools: Whether MCP tools are actually available
            mcp_tools: List of MCP tools (for dynamic prompts)
            output_modalities: Model's output modalities (e.g., ["text", "image"] for image generation)
            tool_choice: Optional tool choice strategy
            **kwargs: Additional parameters

        Yields:
            dict: Chunks in SSE format with 'event' and 'data' keys

        Raises:
            QuotaExceededException: If user would exceed their usage quota
        """
        import json

        # Pre-flight quota check
        self._check_quota_preflight(model, estimated_tokens=max_tokens * 2)

        # Build and inject system prompt based on active features
        messages = self._inject_system_prompt(
            messages,
            enable_mcp_tools=enable_mcp_tools,
            enable_reasoning=enable_reasoning,
            enable_file_tools=enable_file_tools,
            enable_image_generation=enable_image_generation,
            has_mcp_tools=has_mcp_tools,
            mcp_tools=mcp_tools,
        )

        # Build reasoning filter from system prompt (before cache_control transforms it)
        reasoning_filter = None
        if enable_reasoning:
            system_prompt_text = ""
            for msg in messages:
                if msg.get("role") == "system":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        system_prompt_text = " ".join(
                            part.get("text", "") for part in content if part.get("type") == "text"
                        )
                    else:
                        system_prompt_text = content
                    break
            if system_prompt_text:
                reasoning_filter = ReasoningFilter(system_prompt_text)

        # Apply cache_control for Anthropic/Gemini models (OpenRouter
        # message extension — not sent on direct provider calls)
        if self._is_openrouter:
            messages = self._apply_cache_control(messages, model)

        # Calculate dynamic max_tokens based on model's context limit and prompt size
        # This prevents context overflow errors by adjusting max_tokens automatically
        try:
            actual_max_tokens = calculate_dynamic_max_tokens(
                model_id=model,
                messages=messages,
                configured_max_tokens=max_tokens
            )
        except ContextLimitExceededException as e:
            # Yield error event and stop
            logger.error(f"Context limit exceeded in streaming: {e}")
            yield {
                "event": "error",
                "data": {
                    "error": "Conversation too long for selected model",
                    "detail": str(e)
                }
            }
            return

        # Build reasoning object if enabled (OpenRouter native reasoning support)
        reasoning_obj = None
        if enable_reasoning:
            from .reasoning_options import build_reasoning_option

            reasoning_obj = build_reasoning_option(
                model=model,
                reasoning_effort=kwargs.pop("reasoning_effort", None),
                reasoning_max_tokens=kwargs.pop("reasoning_max_tokens", None),
            )

        payload = {
            "model": self._request_model(model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": actual_max_tokens,
            "top_p": top_p,
            "stream": True,
            **self._strip_openrouter_only_kwargs(kwargs),
        }

        # Add reasoning object if enabled (OpenRouter-specific parameter —
        # direct providers would reject it)
        if reasoning_obj and self._is_openrouter:
            payload["reasoning"] = reasoning_obj

        # Direct providers only include token usage in the final stream
        # chunk when explicitly requested (OpenRouter sends it always).
        if not self._is_openrouter:
            payload["stream_options"] = {"include_usage": True}

        # Add tools if provided
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        # Add modalities for image generation models
        # Only set if model supports image output (avoids errors on text-only models)
        # OpenRouter-only: image generation stays on OpenRouter in V1.
        if output_modalities and "image" in output_modalities and self._is_openrouter:
            payload["modalities"] = output_modalities
            logger.info(f"[ImageGen] Enabled image generation with modalities: {output_modalities}")

        url = f"{self.base_url}/chat/completions"

        logger.debug(f"Starting streaming completion - Model: {model}")

        # DEBUG: Log message structure for Amazon models to debug 400 errors
        if "amazon" in model.lower() or "nova" in model.lower():
            logger.info(f"[DEBUG-AMAZON] Sending {len(messages)} messages to API")
            for i, m in enumerate(messages):
                role = m.get('role', 'unknown')
                content = m.get('content')
                has_tc = 'tool_calls' in m
                content_type = type(content).__name__
                if isinstance(content, list):
                    content_summary = f"array with {len(content)} elements: {[c.get('type', 'unknown') for c in content]}"
                elif isinstance(content, str):
                    content_summary = f"string len={len(content)}"
                else:
                    content_summary = f"{content_type}"
                logger.info(f"[DEBUG-AMAZON] msg[{i}]: role={role}, content={content_summary}, has_tool_calls={has_tc}")

        try:
            # Streaming mode
            response = self.session.post(url, json=payload, stream=True, timeout=60)
            response.raise_for_status()

            # Force UTF-8 encoding for proper Unicode support (Arabic, accents, etc.)
            # Without this, requests may incorrectly detect encoding as ISO-8859-1
            response.encoding = 'utf-8'

            # Track usage for cost calculation
            accumulated_content = []
            accumulated_reasoning = []  # Track reasoning content separately
            accumulated_filtered_reasoning = []  # Track filtered reasoning for done event
            accumulated_tool_calls = []  # Track tool calls for function calling
            accumulated_images = []  # Track generated images for image generation models
            usage_data = None
            model_used = model
            finish_reason_final = None
            reasoning_content_final = None  # Store complete reasoning from final chunk
            generation_id = None  # OpenRouter generation ID for precise usage lookup

            # Buffer for parsing <think>...</think> tags
            accumulated_buffer = ""
            in_think_block = False
            LOOKAHEAD = 8  # Keep last 8 chars to avoid cutting "</think>" tag

            # Read the response line by line (SSE format)
            for line in response.iter_lines(decode_unicode=True):
                if not line or line.startswith(":"):
                    # Skip empty lines and comments
                    continue

                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix

                    # Check for end of stream
                    if data_str.strip() == "[DONE]":
                        # Flush remaining buffer before completing
                        if accumulated_buffer:
                            if enable_reasoning and in_think_block:
                                # Remaining content is reasoning
                                accumulated_reasoning.append(accumulated_buffer)
                                filtered_chunk = reasoning_filter.filter_chunk(accumulated_buffer) if reasoning_filter else accumulated_buffer
                                if filtered_chunk:
                                    accumulated_filtered_reasoning.append(filtered_chunk)
                                    yield {
                                        "event": "reasoning",
                                        "data": {"content": filtered_chunk}
                                    }
                            else:
                                # Remaining content is regular response
                                accumulated_content.append(accumulated_buffer)
                                yield {
                                    "event": "content",
                                    "data": {"content": accumulated_buffer}
                                }
                            accumulated_buffer = ""

                        # Flush reasoning filter buffer
                        if reasoning_filter:
                            flushed = reasoning_filter.flush()
                            if flushed:
                                accumulated_filtered_reasoning.append(flushed)
                                yield {
                                    "event": "reasoning",
                                    "data": {"content": flushed}
                                }

                        # Log stream completion details
                        content_chunks_count = len(accumulated_content)
                        logger.info(f"Stream finished - Model: {model_used}, Content chunks: {content_chunks_count}, "
                                   f"Has usage data: {usage_data is not None}, Finish reason: {finish_reason_final}")


                        # CRITICAL: Detect empty streams (model returned no content)
                        # Differentiate between token limit issues vs model unavailability vs tool calls
                        # NOTE: For image generation models, images count as valid content even if no text
                        if content_chunks_count == 0 and len(accumulated_images) == 0:
                            # Check WHY the stream is empty based on finish_reason
                            if finish_reason_final == "tool_calls" and accumulated_tool_calls:
                                # This is NORMAL - model is making a tool call without additional text
                                # Continue to normal completion handling
                                logger.info(f"Model {model_used} returned tool calls without content (normal behavior)")
                            elif finish_reason_final == "length":
                                # Model hit max_tokens before generating any content
                                # This indicates conversation is too long or max_tokens too small
                                logger.error(f"Empty stream due to token limit - Model: {model_used}, finish_reason: length")
                                yield {
                                    "event": "error",
                                    "data": {
                                        "error": "Token limit reached before content generation",
                                        "detail": (
                                            f"The model '{model_used}' reached its token limit without generating any content.\n\n"
                                            f"**Suggestions:**\n"
                                            f"• Increase the Max Tokens parameter in settings\n"
                                            f"• Use a model with a larger context window\n"
                                            f"• Clear some old messages from the conversation"
                                        )
                                    }
                                }
                                break
                            else:
                                # Model unavailable, rate-limited, or internal error
                                logger.error(f"Empty stream detected for model {model_used} - no content received (finish_reason: {finish_reason_final})")
                                yield {
                                    "event": "error",
                                    "data": {
                                        "error": "Model returned no response",
                                        "detail": f"The model '{model_used}' completed the request but returned no content. "
                                                 f"This may indicate the model is temporarily unavailable, rate-limited, "
                                                 f"or encountered an internal error. Please try again or select a different model."
                                    }
                                }
                                break
                        elif content_chunks_count == 0 and len(accumulated_images) > 0:
                            # Image generation models can return ONLY images without text - this is valid
                            logger.info(f"Model {model_used} returned {len(accumulated_images)} image(s) without text content (normal for image generation)")

                        # Normal completion - send 'done' event with metadata
                        if usage_data:
                            costs = self._calculate_cost(model_used, usage_data)
                            done_data = {
                                "usage": usage_data,
                                "cost": float(costs["total_cost"]),
                                "prompt_cost": float(costs["prompt_cost"]),
                                "completion_cost": float(costs["completion_cost"]),
                                "model": model_used,
                                "finish_reason": finish_reason_final,
                                "generation_id": generation_id,
                            }

                            # Log usage for monitoring. request_id carries the
                            # OpenRouter generation id so the abort-settlement
                            # task (llm.tasks.settle_aborted_generations) can
                            # tell already-billed iterations from unbilled ones.
                            self._log_usage(
                                model_id=model_used,
                                prompt_tokens=usage_data.get("prompt_tokens", 0),
                                completion_tokens=usage_data.get("completion_tokens", 0),
                                cost_usd=float(costs["total_cost"]),
                                request_id=generation_id,
                            )

                            # Include filtered reasoning_content if available
                            if accumulated_filtered_reasoning:
                                done_data["reasoning_content"] = "".join(accumulated_filtered_reasoning)
                            elif reasoning_content_final:
                                # Final chunk reasoning — apply a one-shot filter
                                if reasoning_filter:
                                    done_data["reasoning_content"] = reasoning_filter.filter_text(reasoning_content_final)
                                else:
                                    done_data["reasoning_content"] = reasoning_content_final

                            # Include tool_calls if present (for function calling)
                            if accumulated_tool_calls:
                                done_data["tool_calls"] = accumulated_tool_calls

                            # Include images if present (for image generation)
                            if accumulated_images:
                                done_data["images"] = accumulated_images
                                logger.info(f"[ImageGen] Completed with {len(accumulated_images)} image(s)")

                            yield {
                                "event": "done",
                                "data": done_data
                            }
                        else:
                            # No usage data but we have content - send 'done' with default values
                            logger.warning(f"Stream finished without usage data for model {model_used}, but content was received")
                            done_data = {
                                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                                "cost": 0.0,
                                "prompt_cost": 0.0,
                                "completion_cost": 0.0,
                                "model": model_used,
                                "finish_reason": finish_reason_final or "unknown",
                                "generation_id": generation_id,
                            }

                            # Include filtered reasoning_content if available
                            if accumulated_filtered_reasoning:
                                done_data["reasoning_content"] = "".join(accumulated_filtered_reasoning)
                            elif reasoning_content_final:
                                if reasoning_filter:
                                    rf = ReasoningFilter(system_prompt_text="", config=reasoning_filter._config)
                                    rf._fingerprints = reasoning_filter._fingerprints
                                    done_data["reasoning_content"] = rf.filter_chunk(reasoning_content_final) + rf.flush()
                                else:
                                    done_data["reasoning_content"] = reasoning_content_final

                            # Include tool_calls if present (for function calling)
                            if accumulated_tool_calls:
                                done_data["tool_calls"] = accumulated_tool_calls

                            # Include images if present (for image generation)
                            if accumulated_images:
                                done_data["images"] = accumulated_images

                            yield {
                                "event": "done",
                                "data": done_data
                            }
                        break

                    try:
                        chunk = json.loads(data_str)

                        # Capture generation ID from first chunk (for precise usage lookup)
                        if not generation_id and chunk.get("id"):
                            generation_id = chunk["id"]
                            # Emit immediately so downstream has it before any abort
                            yield {
                                "event": "generation_id",
                                "data": {"generation_id": generation_id}
                            }

                        # Update model if provided. Direct providers return
                        # the native model name — keep the full slug there so
                        # pricing lookups and frontend display stay consistent.
                        if chunk.get("model") and self._is_openrouter:
                            model_used = chunk["model"]

                        # Extract content delta
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            choice = chunk["choices"][0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")

                            # NOTE: OpenRouter doesn't send annotations in streaming mode
                            # We extract sources from markdown links after streaming completes (see [DONE] section)

                            # Extract tool calls if present (for function calling)
                            if "tool_calls" in delta:
                                tool_calls_delta = delta["tool_calls"]
                                for tool_call_chunk in tool_calls_delta:
                                    index = tool_call_chunk.get("index", 0)

                                    # Ensure we have a slot for this tool call
                                    while len(accumulated_tool_calls) <= index:
                                        accumulated_tool_calls.append({
                                            "id": None,
                                            "type": "function",
                                            "function": {"name": None, "arguments": ""}
                                        })

                                    # Update tool call at this index
                                    if "id" in tool_call_chunk:
                                        accumulated_tool_calls[index]["id"] = tool_call_chunk["id"]

                                    if "function" in tool_call_chunk:
                                        func = tool_call_chunk["function"]
                                        if "name" in func:
                                            accumulated_tool_calls[index]["function"]["name"] = func["name"]
                                        if "arguments" in func:
                                            # Arguments come in chunks, accumulate them
                                            # Skip empty placeholders like "{}" that some providers send initially
                                            new_args = func["arguments"]
                                            current_args = accumulated_tool_calls[index]["function"]["arguments"]

                                            # If current is empty or just "{}", replace instead of accumulate
                                            if current_args in ("", "{}"):
                                                accumulated_tool_calls[index]["function"]["arguments"] = new_args
                                            # If new args is just "{}", ignore it (placeholder)
                                            elif new_args != "{}":
                                                accumulated_tool_calls[index]["function"]["arguments"] += new_args

                            # Handle OpenRouter native reasoning (reasoning_details array)
                            # OpenRouter sends reasoning in delta.reasoning_details as an array
                            if enable_reasoning and "reasoning_details" in delta:
                                reasoning_details = delta.get("reasoning_details", [])
                                if reasoning_details and isinstance(reasoning_details, list):
                                    for detail in reasoning_details:
                                        detail_type = detail.get('type', '')
                                        reasoning_chunk = None

                                        # Extract text based on detail type
                                        if detail_type == 'reasoning.text':
                                            reasoning_chunk = detail.get('text', '')
                                        elif detail_type == 'reasoning.summary':
                                            reasoning_chunk = detail.get('summary', '')
                                        # Note: reasoning.encrypted is not displayed

                                        if reasoning_chunk:
                                            accumulated_reasoning.append(reasoning_chunk)
                                            filtered_chunk = reasoning_filter.filter_chunk(reasoning_chunk) if reasoning_filter else reasoning_chunk
                                            if filtered_chunk:
                                                accumulated_filtered_reasoning.append(filtered_chunk)
                                                yield {
                                                    "event": "reasoning",
                                                    "data": {"content": filtered_chunk}
                                                }
                                            logger.debug(f"[REASONING] Emitted reasoning chunk ({detail_type}): {len(reasoning_chunk)} chars")

                            # Handle legacy reasoning field (e.g., OpenAI o1, some older OpenRouter models)
                            # Only emit reasoning events if reasoning is enabled
                            elif enable_reasoning:
                                reasoning_delta = delta.get("reasoning", "")
                                if reasoning_delta:
                                    accumulated_reasoning.append(reasoning_delta)
                                    filtered_chunk = reasoning_filter.filter_chunk(reasoning_delta) if reasoning_filter else reasoning_delta
                                    if filtered_chunk:
                                        accumulated_filtered_reasoning.append(filtered_chunk)
                                        yield {
                                            "event": "reasoning",
                                            "data": {"content": filtered_chunk}
                                        }
                                    logger.debug(f"[REASONING] Emitted legacy reasoning chunk: {len(reasoning_delta)} chars")

                            # Handle image generation - extract images from delta or message
                            # Images can be strings (data URLs) or dicts with url/data fields
                            images_in_delta = delta.get("images", [])
                            if images_in_delta:
                                for img in images_in_delta:
                                    # Extract the actual data URL from the dict structure
                                    if isinstance(img, dict):
                                        # OpenRouter format: {'type': 'image_url', 'image_url': {'url': 'data:...'}}
                                        if 'image_url' in img and 'url' in img['image_url']:
                                            image_url = img['image_url']['url']
                                        elif 'url' in img:
                                            image_url = img['url']
                                        else:
                                            logger.warning(f"[ImageGen] Unknown image dict format: {img}")
                                            continue
                                    else:
                                        image_url = img

                                    if image_url and image_url not in accumulated_images:
                                        accumulated_images.append(image_url)
                                        logger.info(f"[ImageGen] Received image in delta: {image_url[:50]}...")
                                        yield {
                                            "event": "image",
                                            "data": {"image": image_url}
                                        }

                            # Also check for images in message object (for final chunks)
                            message = choice.get("message", {})
                            if message:
                                images_in_message = message.get("images", [])
                                if images_in_message:
                                    for img in images_in_message:
                                        # Extract the actual data URL from the dict structure (same as delta handling)
                                        if isinstance(img, dict):
                                            # OpenRouter format: {'type': 'image_url', 'image_url': {'url': 'data:...'}}
                                            if 'image_url' in img and 'url' in img['image_url']:
                                                image_url = img['image_url']['url']
                                            elif 'url' in img:
                                                image_url = img['url']
                                            else:
                                                logger.warning(f"[ImageGen] Unknown image dict format in message: {img}")
                                                continue
                                        else:
                                            image_url = img

                                        if image_url and image_url not in accumulated_images:
                                            accumulated_images.append(image_url)
                                            logger.info(f"[ImageGen] Received image in message: {image_url[:50]}...")
                                            yield {
                                                "event": "image",
                                                "data": {"image": image_url}
                                            }

                            # Track finish reason
                            finish_reason = choice.get("finish_reason")
                            if finish_reason:
                                finish_reason_final = finish_reason
                                logger.debug(f"Stream finished: {finish_reason}")

                            if content:
                                # Add content to buffer for tag parsing
                                accumulated_buffer += content

                                # Process buffer for <think>...</think> tags (only if reasoning is enabled)
                                while accumulated_buffer and enable_reasoning:
                                    # Check for <think> tag
                                    if '<think>' in accumulated_buffer and not in_think_block:
                                        think_start = accumulated_buffer.index('<think>')

                                        # Content before <think> is regular response content
                                        before_think = accumulated_buffer[:think_start]
                                        if before_think:
                                            accumulated_content.append(before_think)
                                            yield {
                                                "event": "content",
                                                "data": {"content": before_think}
                                            }

                                        # Remove everything up to and including <think>
                                        accumulated_buffer = accumulated_buffer[think_start + 7:]  # len('<think>') = 7
                                        in_think_block = True
                                        continue

                                    # Check for </think> tag
                                    if '</think>' in accumulated_buffer and in_think_block:
                                        think_end = accumulated_buffer.index('</think>')

                                        # Content before </think> is reasoning content
                                        reasoning_chunk = accumulated_buffer[:think_end]
                                        if reasoning_chunk:
                                            accumulated_reasoning.append(reasoning_chunk)
                                            filtered_chunk = reasoning_filter.filter_chunk(reasoning_chunk) if reasoning_filter else reasoning_chunk
                                            if filtered_chunk:
                                                accumulated_filtered_reasoning.append(filtered_chunk)
                                                yield {
                                                    "event": "reasoning",
                                                    "data": {"content": filtered_chunk}
                                                }

                                        # Remove everything up to and including </think>
                                        accumulated_buffer = accumulated_buffer[think_end + 8:]  # len('</think>') = 8
                                        in_think_block = False

                                        # Continue to process any remaining content after </think>
                                        continue

                                    # Emit content from buffer (keeping LOOKAHEAD chars for next iteration)
                                    if len(accumulated_buffer) > LOOKAHEAD:
                                        # Emit everything except last LOOKAHEAD chars
                                        to_emit = accumulated_buffer[:-LOOKAHEAD]
                                        accumulated_buffer = accumulated_buffer[-LOOKAHEAD:]

                                        if in_think_block:
                                            # Inside thinking block - emit as reasoning
                                            accumulated_reasoning.append(to_emit)
                                            filtered_chunk = reasoning_filter.filter_chunk(to_emit) if reasoning_filter else to_emit
                                            if filtered_chunk:
                                                accumulated_filtered_reasoning.append(filtered_chunk)
                                                yield {
                                                    "event": "reasoning",
                                                    "data": {"content": filtered_chunk}
                                                }
                                        else:
                                            # Outside thinking block - emit as regular content
                                            accumulated_content.append(to_emit)
                                            yield {
                                                "event": "content",
                                                "data": {"content": to_emit}
                                            }

                                    # Exit loop - wait for more chunks
                                    break

                                # If reasoning is disabled, emit buffer content directly (no tag parsing)
                                if not enable_reasoning and len(accumulated_buffer) > LOOKAHEAD:
                                    to_emit = accumulated_buffer[:-LOOKAHEAD]
                                    accumulated_buffer = accumulated_buffer[-LOOKAHEAD:]
                                    accumulated_content.append(to_emit)
                                    yield {
                                        "event": "content",
                                        "data": {"content": to_emit}
                                    }

                        # Extract usage if present (usually in last chunk).
                        # NOTE: with stream_options.include_usage, direct
                        # providers send "usage": null on non-final chunks —
                        # guard against None, not just absence.
                        if chunk.get("usage"):
                            usage_data = {
                                "prompt_tokens": chunk["usage"].get("prompt_tokens", 0),
                                "completion_tokens": chunk["usage"].get("completion_tokens", 0),
                                "total_tokens": chunk["usage"].get("total_tokens", 0),
                            }

                        # Extract reasoning_content from final chunk if present (for reasoning models)
                        # Some models include the full reasoning in the final response
                        if "reasoning_content" in chunk:
                            reasoning_content_final = chunk["reasoning_content"]

                            # Emit reasoning_content immediately as streaming event
                            if reasoning_content_final and not accumulated_reasoning:
                                if reasoning_filter:
                                    filtered_final = reasoning_filter.filter_text(reasoning_content_final)
                                    if filtered_final:
                                        accumulated_filtered_reasoning.append(filtered_final)
                                        yield {
                                            "event": "reasoning",
                                            "data": {"content": filtered_final}
                                        }
                                else:
                                    yield {
                                        "event": "reasoning",
                                        "data": {"content": reasoning_content_final}
                                    }

                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse SSE chunk: {e}")
                        continue

        except requests.exceptions.RequestException as e:
            logger.error(f"Streaming request failed for model {model}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                try:
                    logger.error(f"Response body: {e.response.text}")
                except Exception:
                    logger.error("Could not read response body")
            # error_payload keeps raw provider text (URLs, key fragments) out
            # of the UI and attaches a machine code for actionable errors
            # (invalid/missing key, insufficient credits).
            yield {
                "event": "error",
                "data": error_payload(e)
            }
            # Return instead of raising to avoid sending duplicate error events
            return

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"

        logger.debug(f"Making {method} request to {url}")

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(method, url, **kwargs)

                logger.debug(f"Response status: {response.status_code}")

                if response.status_code == 429:
                    # Rate limited
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(min(retry_after, RETRY_BACKOFF_MAX))
                        continue
                    raise RateLimitException("Rate limit exceeded")

                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed on attempt {attempt + 1}/{MAX_RETRIES}: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response status: {e.response.status_code}")
                    try:
                        logger.error(f"Response body: {e.response.text}")
                    except Exception:
                        logger.error("Could not read response body")

                if attempt < MAX_RETRIES - 1:
                    backoff = min(RETRY_BACKOFF_BASE**attempt, RETRY_BACKOFF_MAX)
                    time.sleep(backoff)
                    continue
                raise

        raise OpenRouterException(f"Failed after {MAX_RETRIES} attempts")

    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> Dict[str, Decimal]:
        """
        Calculate estimated cost based on token usage with detailed breakdown.

        Returns:
            Dictionary with prompt_cost, completion_cost, and total_cost
        """
        from .catalog_service import CatalogService

        # Use catalog service for accurate pricing
        catalog = CatalogService(self)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return catalog.estimate_cost_detailed(model, prompt_tokens, completion_tokens)

    def check_model_availability(self, model: str) -> bool:
        """
        Check if a model is available for use.

        Args:
            model: Model identifier

        Returns:
            True if model is available
        """
        from .catalog_service import CatalogService

        catalog = CatalogService(self)
        return catalog.check_model_availability(model)

    def complete_with_fallback(
        self,
        models: List[str],
        messages: List[Dict[str, str]],
        max_cost: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Complete with automatic fallback to alternative models.

        Args:
            models: List of models in order of preference
            messages: Chat messages
            max_cost: Maximum cost limit in USD
            **kwargs: Additional parameters for completion

        Returns:
            Completion result from first successful model

        Raises:
            OpenRouterException: If all models fail
            CostLimitException: If cost limit would be exceeded
        """
        from .catalog_service import CatalogService
        from .rate_limiter import RateLimiter

        catalog = CatalogService(self)
        rate_limiter = RateLimiter()

        errors = []

        for model in models:
            try:
                # Check model availability
                if not self.check_model_availability(model):
                    errors.append(f"{model}: Not available")
                    continue

                # Check cost limit if specified
                if max_cost is not None:
                    # Estimate cost (rough estimate based on max tokens)
                    max_tokens = kwargs.get("max_tokens", DEFAULT_MAX_TOKENS)
                    # Assume prompt is roughly same size as max completion
                    estimated_cost = catalog.estimate_cost(
                        model, max_tokens, max_tokens
                    )

                    if float(estimated_cost) > max_cost:
                        errors.append(
                            f"{model}: Exceeds cost limit (${estimated_cost:.4f} > ${
                                max_cost
                            })"
                        )
                        continue

                # Check rate limit
                allowed, retry_after = rate_limiter.check_rate_limit(model)
                if not allowed:
                    errors.append(
                        f"{model}: Rate limited (retry after {retry_after:.1f}s)"
                    )
                    continue

                # Try completion
                logger.info(f"Attempting completion with {model}")
                result = self.complete(model, messages, **kwargs)

                # Add fallback info to result
                result["model_used"] = model
                result["fallback_attempts"] = len(errors)

                return result

            except Exception as e:
                errors.append(f"{model}: {str(e)}")
                logger.warning(f"Model {model} failed: {e}")
                continue

        # All models failed
        error_msg = "All models failed:\n" + "\n".join(errors)
        raise OpenRouterException(error_msg)

    def get_generation_metadata(self) -> Dict[str, Any]:
        """
        Get metadata about the last generation request.

        Returns:
            Dictionary with generation metadata
        """
        try:
            response = self._make_request("GET", "/generation")
            return response
        except Exception as e:
            logger.error(f"Failed to get generation metadata: {e}")
            return {}

    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics for the API key.

        Returns:
            Dictionary with usage statistics
        """
        try:
            # Note: This endpoint might not be available yet in OpenRouter
            # Including for future compatibility
            response = self._make_request("GET", "/usage")
            return response
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            return {}
