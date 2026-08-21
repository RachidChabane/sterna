"""Recovery from a 413 "context too large" on the LangChain path.

Retry strategy. On 413 the conversation is summarized down and the whole
turn is replayed once; a 413 on the replay is terminal.

There are two entry points because the agent catches 413 twice -- once as
`openai.APIError` and once as a generic exception raised by some wrapper
-- and the two branches emit deliberately different copy and different
`context_compacted` payloads. They are kept as two methods on purpose:
only the compactor construction is shared.
"""

import logging
from typing import Any, AsyncGenerator, Callable, Dict, List

import openai

from ...context_compaction import (
    CharacterBasedTokenEstimator,
    CompactionConfig,
    CompactionStrategy,
    ContextCompactor,
    OpenAICompatibleSummarizer,
    get_model_context_limit,
)
from ..sse_events import EVENT_CONTEXT_COMPACTED, context_too_large_event

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# Compaction tuning for the post-413 emergency pass.
COMPACTION_THRESHOLD_PERCENTAGE = 0.50
COMPACTION_PRESERVE_RECENT_MESSAGES = 4
COMPACTION_SUMMARY_MAX_TOKENS = 2048

DETAIL_EXHAUSTED_API_ERROR = (
    "The conversation context is too large even after automatic summarization. "
    "Please try one of the following:\n"
    "• Start a new conversation\n"
    "• Delete some earlier messages"
)
DETAIL_EXHAUSTED_GENERIC = (
    "The conversation context is too large even after automatic summarization. "
    "Please try starting a new conversation."
)
DETAIL_NOT_COMPACTED_API_ERROR = (
    "The conversation context is too large for the API. "
    "Please try starting a new conversation."
)
DETAIL_NOT_COMPACTED_GENERIC = (
    "The conversation context is too large. Please start a new conversation."
)
DETAIL_COMPACTION_FAILED_API_ERROR = (
    "The conversation context is too large and automatic summarization failed. "
    "Please try starting a new conversation."
)
DETAIL_COMPACTION_FAILED_GENERIC = (
    "Context too large and summarization failed. Please start a new conversation."
)


class ContextCompactionRetry:
    """Summarize-and-replay recovery for an over-long conversation."""

    def __init__(self, model_id: str, resolve_summarizer_endpoint: Callable):
        self._model_id = model_id
        self._resolve_summarizer_endpoint = resolve_summarizer_endpoint

    async def _build_compactor(self) -> ContextCompactor:
        config = CompactionConfig(
            enabled=True,
            strategy=CompactionStrategy.PERCENTAGE,
            threshold_percentage=COMPACTION_THRESHOLD_PERCENTAGE,
            preserve_system_prompt=True,
            preserve_first_user_message=True,
            preserve_recent_messages=COMPACTION_PRESERVE_RECENT_MESSAGES,
            summary_max_tokens=COMPACTION_SUMMARY_MAX_TOKENS,
        )

        sum_key, sum_base_url, sum_model = await self._resolve_summarizer_endpoint()
        summarizer = OpenAICompatibleSummarizer(
            client=openai.AsyncOpenAI(api_key=sum_key, base_url=sum_base_url),
            model=sum_model,
        )

        return ContextCompactor(
            config=config,
            summarizer=summarizer,
            token_estimator=CharacterBasedTokenEstimator(),
        )

    async def after_api_error(
        self,
        messages: List[Dict[str, Any]],
        already_retried: bool,
        replay: Callable[[List[Dict[str, Any]]], AsyncGenerator],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle a 413 surfaced as `openai.APIError`."""
        logger.warning("[LangChain] 413 Request Entity Too Large - context too large for API")

        if already_retried:
            yield context_too_large_event(DETAIL_EXHAUSTED_API_ERROR)
            return

        logger.info("[LangChain] Attempting context compaction after 413 error...")
        try:
            compactor = await self._build_compactor()
            result = await compactor.compact(messages, get_model_context_limit(self._model_id))

            if not result.was_compacted:
                # Compaction didn't help (not enough messages to compact)
                yield context_too_large_event(DETAIL_NOT_COMPACTED_API_ERROR)
                return

            logger.info(
                f"[LangChain] Context compacted after 413: "
                f"{result.metrics.original_message_count} -> {result.metrics.compacted_message_count} messages, "
                f"saved {result.metrics.tokens_saved:,} tokens"
            )
            yield {
                "event": EVENT_CONTEXT_COMPACTED,
                "data": {
                    "original_messages": result.metrics.original_message_count,
                    "compacted_messages": result.metrics.compacted_message_count,
                    "original_tokens": result.metrics.original_token_estimate,
                    "compacted_tokens": result.metrics.compacted_token_estimate,
                    "tokens_saved": result.metrics.tokens_saved,
                    "compression_ratio": round(result.metrics.compression_ratio, 2),
                    "duration_ms": result.metrics.summarization_duration_ms,
                },
            }

            async for event in replay(result.compacted_messages):
                yield event

        except Exception:
            logger.error("langchain.compaction_failed_after_413", exc_info=True)
            yield context_too_large_event(DETAIL_COMPACTION_FAILED_API_ERROR)

    async def after_generic_error(
        self,
        messages: List[Dict[str, Any]],
        already_retried: bool,
        replay: Callable[[List[Dict[str, Any]]], AsyncGenerator],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle a 413 that surfaced as a plain exception from a wrapper."""
        logger.warning("[LangChain] 413 Request Entity Too Large (generic exception)")

        if already_retried:
            yield context_too_large_event(DETAIL_EXHAUSTED_GENERIC)
            return

        logger.info("[LangChain] Attempting context compaction after 413 error (generic)...")
        try:
            compactor = await self._build_compactor()
            result = await compactor.compact(messages, get_model_context_limit(self._model_id))

            if not result.was_compacted:
                yield context_too_large_event(DETAIL_NOT_COMPACTED_GENERIC)
                return

            logger.info(
                f"[LangChain] Context compacted after 413: "
                f"{result.metrics.original_message_count} -> {result.metrics.compacted_message_count} messages"
            )
            yield {
                "event": EVENT_CONTEXT_COMPACTED,
                "data": {
                    "original_messages": result.metrics.original_message_count,
                    "compacted_messages": result.metrics.compacted_message_count,
                    "tokens_saved": result.metrics.tokens_saved,
                },
            }

            async for event in replay(result.compacted_messages):
                yield event

        except Exception:
            logger.error("langchain.compaction_failed", exc_info=True)
            yield context_too_large_event(DETAIL_COMPACTION_FAILED_GENERIC)
