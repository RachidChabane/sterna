"""
Chat handler for Consigliere AI.

Manages chat interactions with the Consigliere using the user's selected model.
"""

import logging
import time
from typing import Dict, List, Any
from decimal import Decimal

from llm.client import OpenRouterClient
from llm.exceptions import OpenRouterException
from ..prompts import CONSIGLIERE_SYSTEM_PROMPT
from ..config import ModelParametersDefaults as MPD

logger = logging.getLogger(__name__)


class ConsiglierChatHandler:
    """
    Handles chat interactions with the Consigliere AI.

    Uses the user's currently selected model to power the Consigliere's responses.
    """

    def __init__(self, current_model: str, user=None):
        """
        Initialize chat handler.

        Args:
            current_model: Model ID to use for Consigliere responses
            user: User object for API key resolution
        """
        self.client = OpenRouterClient(user=user, request_source='consigliere')
        self.model = current_model

    def chat(
        self,
        messages: List[Dict[str, str]],
        context: str,
        temperature: float = MPD.TEMPERATURE,
        max_tokens: int = MPD.MAX_TOKENS,
        top_p: float = MPD.TOP_P,
        top_k: int = MPD.TOP_K,
        frequency_penalty: float = MPD.FREQUENCY_PENALTY,
        presence_penalty: float = MPD.PRESENCE_PENALTY,
        repetition_penalty: float = MPD.REPETITION_PENALTY,
        min_p: float = MPD.MIN_P,
        top_a: float = MPD.TOP_A,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a Consigliere response.

        Args:
            messages: Conversation history (user and assistant messages)
            context: Context string about the conversation being analyzed
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            frequency_penalty: Frequency penalty parameter
            presence_penalty: Presence penalty parameter
            repetition_penalty: Repetition penalty parameter
            min_p: Minimum probability parameter
            top_a: Top-a sampling parameter
            stream: Enable streaming (not yet implemented)

        Returns:
            Dictionary with response, metadata, and usage info

        Note:
            Default parameter values are defined in config.ModelParametersDefaults
        """
        # Build system message with context
        system_message = CONSIGLIERE_SYSTEM_PROMPT.format(context=context)

        # Prepare messages for API
        api_messages = [{"role": "system", "content": system_message}]
        api_messages.extend(messages)

        try:
            start_time = time.time()

            # Call OpenRouter
            response = self.client.complete(
                model=self.model,
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                repetition_penalty=repetition_penalty,
                min_p=min_p,
                top_a=top_a,
                stream=stream,
            )

            end_time = time.time()
            latency = end_time - start_time

            # Extract response content
            content = response.get("content", "")
            usage = response.get("usage", {})
            model_used = response.get("model", self.model)

            # Calculate cost (from usage)
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = prompt_tokens + completion_tokens

            # Get detailed pricing breakdown
            cost_breakdown = self._estimate_cost_detailed(model_used, prompt_tokens, completion_tokens)

            return {
                "content": content,
                "model_used": model_used,
                "tokens_used": total_tokens,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost": cost_breakdown["total_cost"],
                "prompt_cost": cost_breakdown["prompt_cost"],
                "completion_cost": cost_breakdown["completion_cost"],
                "latency": latency,
                "usage": usage,
            }

        except OpenRouterException as e:
            logger.error(f"OpenRouter error in Consigliere chat: {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error in Consigliere chat: {e}")
            raise

    def _estimate_cost_detailed(
        self, model_id: str, prompt_tokens: int, completion_tokens: int
    ) -> Dict[str, Decimal]:
        """
        Estimate cost breakdown based on tokens.

        Args:
            model_id: Model identifier
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Dictionary with prompt_cost, completion_cost, and total_cost
        """
        # Import here to avoid circular imports
        from llm.catalog_service import CatalogService

        try:
            catalog_service = CatalogService()
            cost_details = catalog_service.estimate_cost_detailed(
                model_id, prompt_tokens, completion_tokens
            )
            return cost_details

        except Exception as e:
            logger.warning(f"Could not fetch pricing for {model_id}: {e}")

            # Fallback: rough estimates
            price_per_1k_tokens = Decimal("0.002")  # Default estimate
            prompt_cost = (Decimal(str(prompt_tokens)) / 1000) * price_per_1k_tokens
            completion_cost = (Decimal(str(completion_tokens)) / 1000) * price_per_1k_tokens
            return {
                "prompt_cost": prompt_cost,
                "completion_cost": completion_cost,
                "total_cost": prompt_cost + completion_cost,
            }

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        context: str,
        temperature: float = MPD.TEMPERATURE,
        max_tokens: int = MPD.MAX_TOKENS,
        top_p: float = MPD.TOP_P,
        top_k: int = MPD.TOP_K,
        frequency_penalty: float = MPD.FREQUENCY_PENALTY,
        presence_penalty: float = MPD.PRESENCE_PENALTY,
        repetition_penalty: float = MPD.REPETITION_PENALTY,
        min_p: float = MPD.MIN_P,
        top_a: float = MPD.TOP_A,
    ):
        """
        Generate a streaming Consigliere response.

        Args:
            messages: Conversation history
            context: Context string
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            frequency_penalty: Frequency penalty parameter
            presence_penalty: Presence penalty parameter
            repetition_penalty: Repetition penalty parameter
            min_p: Minimum probability parameter
            top_a: Top-a sampling parameter

        Yields:
            SSE-formatted events with 'event' and 'data' keys:
            - {"event": "content", "data": {"content": "..."}}
            - {"event": "done", "data": {"usage": {...}, "cost": ..., "latency": ...}}
            - {"event": "error", "data": {"error": "..."}}

        Note:
            Default parameter values are defined in config.ModelParametersDefaults
        """
        # Build system message
        system_message = CONSIGLIERE_SYSTEM_PROMPT.format(context=context)

        # Prepare messages
        api_messages = [{"role": "system", "content": system_message}]
        api_messages.extend(messages)

        start_time = time.time()
        accumulated_content = []

        try:
            # Use OpenRouterClient's complete_stream method
            for chunk in self.client.complete_stream(
                model=self.model,
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                repetition_penalty=repetition_penalty,
                min_p=min_p,
                top_a=top_a,
            ):
                event_type = chunk.get("event")
                event_data = chunk.get("data", {})

                if event_type == "content":
                    # Accumulate content and yield chunk
                    content = event_data.get("content", "")
                    if content:
                        accumulated_content.append(content)
                    yield chunk

                elif event_type == "done":
                    # Calculate latency
                    end_time = time.time()
                    latency = end_time - start_time

                    # Get usage and cost from OpenRouter
                    usage = event_data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    model_used = event_data.get("model", self.model)

                    # Calculate detailed cost breakdown
                    cost_breakdown = self._estimate_cost_detailed(
                        model_used, prompt_tokens, completion_tokens
                    )

                    # Yield final event with enhanced metadata
                    yield {
                        "event": "done",
                        "data": {
                            "usage": usage,
                            "cost": float(cost_breakdown["total_cost"]),
                            "prompt_cost": float(cost_breakdown["prompt_cost"]),
                            "completion_cost": float(cost_breakdown["completion_cost"]),
                            "latency": latency,
                            "model": model_used,
                            "content": "".join(accumulated_content),
                        }
                    }

                elif event_type == "error":
                    # Forward error event
                    yield chunk

        except OpenRouterException as e:
            logger.error(f"OpenRouter error in streaming chat: {e}")
            yield {
                "event": "error",
                "data": {"error": str(e)}
            }
            raise

        except Exception as e:
            logger.error(f"Unexpected error in streaming chat: {e}")
            yield {
                "event": "error",
                "data": {"error": str(e)}
            }
            raise

    def format_conversation_context(
        self, session_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        Format session messages for API consumption.

        Args:
            session_messages: List of ConsigliereMessage objects (as dicts)

        Returns:
            List of formatted messages for API
        """
        formatted = []

        for msg in session_messages:
            formatted.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        return formatted
