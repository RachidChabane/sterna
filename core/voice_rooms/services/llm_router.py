"""LLM Router for OpenRouter API integration."""

import asyncio
import json
import logging
from typing import AsyncIterator, Dict, List, Optional, TYPE_CHECKING

import httpx
from django.conf import settings

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)

# Retry configuration for rate limiting
MAX_RETRIES = 2
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 5.0  # seconds


class LLMRouter:
    """
    OpenRouter API client for LLM completions.

    Handles streaming completions from various LLM providers
    through the OpenRouter unified API.
    """

    def __init__(self, user: Optional['User'] = None):
        """
        Initialize the LLM router.

        Args:
            user: User for API key resolution and usage tracking
        """
        from llm.services.api_key_resolver import resolve_with_origin

        self._user = user
        self.api_key, self._billing_origin = resolve_with_origin(user=user)
        self.base_url = settings.OPENROUTER_API_BASE
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": settings.OPENROUTER_SITE_URL,
                "X-Title": "Sterna Voice Rooms",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def cleanup(self) -> None:
        """Cleanup HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _record_billing(
        self,
        model: str,
        usage: Optional[Dict] = None,
    ) -> None:
        """Record one OPENROUTER/VOICE_ROOM UsageLog row per completion.

        OpenRouter usually returns `usage.{prompt_tokens, completion_tokens}`;
        cost is computed via CatalogService since the API does not always
        include `cost` for every model.
        """
        if not self._user or not usage:
            return
        try:
            from asgiref.sync import sync_to_async
            from usage_quota.billing.service import get_billing_service
            from usage_quota.billing.operations import BillableOperation
            from usage_quota.services.cost_calculator import get_cost_calculator
            from usage_quota.models import ServiceType, FeatureType

            prompt_t = int(usage.get("prompt_tokens", 0) or 0)
            completion_t = int(usage.get("completion_tokens", 0) or 0)
            cost = get_cost_calculator().calculate_openrouter_cost(
                model_id=model,
                prompt_tokens=prompt_t,
                completion_tokens=completion_t,
            )
            op = BillableOperation(
                service=ServiceType.OPENROUTER,
                feature=FeatureType.VOICE_ROOM,
                model_id=model,
                prompt_tokens=prompt_t,
                completion_tokens=completion_t,
                cost_usd=cost,
            )
            await sync_to_async(get_billing_service().record_usage)(
                self._user, op, billing_origin=self._billing_origin,
            )
        except Exception:
            logger.error("llm_router.record_billing_failed", exc_info=True)

    async def stream_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> AsyncIterator[Dict]:
        """
        Stream a completion from the LLM.

        Args:
            model: Model ID (e.g., "openai/gpt-4o")
            messages: Conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stop: Stop sequences
            tools: Optional list of tool definitions
            tool_choice: Optional tool choice strategy

        Yields:
            Dict with either 'content' (text chunk) or 'tool_call' (tool call data)
        """
        if not self._client:
            await self.initialize()

        client = self._client
        if client is None:
            raise RuntimeError("LLMRouter.initialize() must be called before stream_completion()")

        # Tier gate: refuse the call when the user's plan disallows
        # voice rooms. The flag is shared with voice_session, so a
        # plan with voice_rooms=False rejects here too.
        if self._user is not None:
            from decimal import Decimal

            from usage_quota.models import FeatureType, ServiceType
            from usage_quota.services import get_quota_service
            quota = get_quota_service()
            await quota.acheck_quota(
                user=self._user,
                service=ServiceType.OPENROUTER,
                estimated_cost_usd=Decimal('0'),
                feature=FeatureType.VOICE_ROOM,
                feature_name='voice_llm',
            )

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens or settings.DEFAULT_MAX_TOKENS,
        }

        if stop:
            payload["stop"] = stop

        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
            logger.info(f"LLM request with {len(tools)} tools, tool_choice={tool_choice}")

        # Track tool call accumulation across chunks
        tool_calls_accumulator: Dict[int, Dict] = {}
        final_usage: Optional[Dict] = None

        retry_count = 0
        retry_delay = INITIAL_RETRY_DELAY

        while True:
            try:
                logger.info(f"LLM streaming request: model={model}")

                # Use regular POST instead of stream() to avoid "stream closed" issues
                # Then parse SSE events from the response body
                response = await client.post(
                    "/chat/completions",
                    json=payload,
                    timeout=120.0,  # Longer timeout for streaming responses
                )

                status_code = response.status_code

                # For error responses, handle specially
                if status_code >= 400:
                    error_body = response.text

                    # Handle rate limiting (429) with retry
                    if status_code == 429:
                        retry_count += 1
                        if retry_count <= MAX_RETRIES:
                            logger.warning(
                                f"Rate limited (429) for model {model}, "
                                f"retry {retry_count}/{MAX_RETRIES} after {retry_delay:.1f}s"
                            )
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                            continue  # Retry the request
                        else:
                            logger.error(
                                f"Rate limited (429) for model {model}, "
                                f"max retries ({MAX_RETRIES}) exceeded"
                            )

                    logger.error(f"HTTP {status_code} from OpenRouter for model {model}: {error_body[:500]}")
                    raise httpx.HTTPStatusError(
                        f"HTTP {status_code}",
                        request=response.request,
                        response=response
                    )

                # Parse SSE events from the response body
                response_text = response.text
                for line in response_text.split("\n"):
                    if not line:
                        continue

                    if line.startswith("data: "):
                        line = line[6:]

                    if line == "[DONE]":
                        # Yield any complete tool calls at the end
                        for idx, tool_call in tool_calls_accumulator.items():
                            if tool_call.get("function", {}).get("name"):
                                yield {"tool_call": tool_call}
                        break

                    try:
                        data = json.loads(line)
                        if data.get("usage"):
                            final_usage = data["usage"]
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})

                            # Handle content chunks
                            content = delta.get("content")
                            if content:
                                yield {"content": content}

                            # Handle tool call chunks
                            tool_call_chunks = delta.get("tool_calls", [])
                            for tc_chunk in tool_call_chunks:
                                idx = tc_chunk.get("index", 0)

                                if idx not in tool_calls_accumulator:
                                    tool_calls_accumulator[idx] = {
                                        "id": tc_chunk.get("id", ""),
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""}
                                    }

                                # Accumulate ID if present
                                if tc_chunk.get("id"):
                                    tool_calls_accumulator[idx]["id"] = tc_chunk["id"]

                                # Accumulate function data
                                func_chunk = tc_chunk.get("function", {})
                                if func_chunk.get("name"):
                                    tool_calls_accumulator[idx]["function"]["name"] = func_chunk["name"]
                                if func_chunk.get("arguments"):
                                    tool_calls_accumulator[idx]["function"]["arguments"] += func_chunk["arguments"]

                    except json.JSONDecodeError:
                        continue

                # Successfully processed response, exit retry loop
                if final_usage:
                    await self._record_billing(model, final_usage)
                break

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from OpenRouter: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error streaming from OpenRouter: {e}")
                raise

    async def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict:
        """
        Get a non-streaming completion from the LLM.

        Args:
            model: Model ID
            messages: Conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            tools: Optional list of tool definitions (OpenAI function calling format)
            tool_choice: Optional tool choice strategy ("auto", "none", or specific)

        Returns:
            Dict with 'content' and optionally 'tool_calls'
        """
        if not self._client:
            await self.initialize()

        client = self._client
        if client is None:
            raise RuntimeError("LLMRouter.initialize() must be called before complete()")

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens or settings.DEFAULT_MAX_TOKENS,
        }

        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        try:
            response = await client.post(
                "/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            await self._record_billing(model, data.get("usage"))

            choices = data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                result = {
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                }
                return result

            return {"content": "", "tool_calls": []}

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from OpenRouter: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error from OpenRouter: {e}")
            raise
