"""Relieving context-window pressure before a generation is requested.

The agent core hands its `ContextWindowPort` the history it is about
to send and takes back the history to send instead, plus the events
explaining any change. `llm.context_compaction` already owns that
work: it measures the conversation, summarizes the older part when it
crosses the configured share of the model's window, and reports what
it saved.

The compactor speaks the OpenAI-shaped message mappings the endpoints
exchange, so the port translates in both directions. A message the
compactor left untouched is handed back as the object that came in,
so nothing a summarizer does not understand -- a tool call, the id a
tool result answers -- is lost in translation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import openai

from ..agent_core.events import ContextCompactedEvent, StreamEvent
from ..agent_core.graph.ports import ContextRelief
from ..agent_core.provider import ProviderMessage
from ..context_compaction import (
    CharacterBasedTokenEstimator,
    CompactionConfig,
    CompactionStrategy,
    ContextCompactor,
    OpenAICompatibleSummarizer,
    get_model_context_limit,
)

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

COMPACTION_THRESHOLD_PERCENTAGE = 0.50
"""Share of the model's window at which the older history is summarized."""

COMPACTION_PRESERVE_RECENT_MESSAGES = 4
COMPACTION_SUMMARY_MAX_TOKENS = 2048

ROLE_FIELD = "role"
CONTENT_FIELD = "content"

COMPACTION_ROUNDING = 2
"""Decimal places the compression ratio is reported to."""


class CompactingContextWindow:
    """Summarizes the older history when the model's window fills up."""

    def __init__(self, *, summarizer_endpoint, model_id: str) -> None:
        self._summarizer_endpoint = summarizer_endpoint
        self._model_id = model_id
        self._compactor: Optional[ContextCompactor] = None

    async def relieve(
        self, messages: Sequence[ProviderMessage], *, model: str
    ) -> ContextRelief:
        original = list(messages)
        try:
            compactor = await self._build_compactor()
            result = await compactor.compact_if_needed(
                [_as_mapping(message) for message in original],
                get_model_context_limit(model or self._model_id),
            )
        except Exception:
            logger.error("agent_service.context_relief_failed", exc_info=True)
            return ContextRelief(messages=original)

        if not result.was_compacted:
            return ContextRelief(messages=original)

        return ContextRelief(
            messages=_as_provider_messages(result.compacted_messages, original),
            events=(_compacted_event(result.metrics),),
        )

    async def _build_compactor(self) -> ContextCompactor:
        if self._compactor is not None:
            return self._compactor
        api_key, base_url, model = await self._summarizer_endpoint()
        self._compactor = ContextCompactor(
            config=CompactionConfig(
                enabled=True,
                strategy=CompactionStrategy.PERCENTAGE,
                threshold_percentage=COMPACTION_THRESHOLD_PERCENTAGE,
                preserve_system_prompt=True,
                preserve_first_user_message=True,
                preserve_recent_messages=COMPACTION_PRESERVE_RECENT_MESSAGES,
                summary_max_tokens=COMPACTION_SUMMARY_MAX_TOKENS,
            ),
            summarizer=OpenAICompatibleSummarizer(
                client=openai.AsyncOpenAI(api_key=api_key, base_url=base_url),
                model=model,
            ),
            token_estimator=CharacterBasedTokenEstimator(),
        )
        return self._compactor


def _compacted_event(metrics) -> StreamEvent:
    return ContextCompactedEvent(
        original_messages=metrics.original_message_count,
        compacted_messages=metrics.compacted_message_count,
        tokens_saved=metrics.tokens_saved,
        original_tokens=metrics.original_token_estimate,
        compacted_tokens=metrics.compacted_token_estimate,
        compression_ratio=round(metrics.compression_ratio, COMPACTION_ROUNDING),
        duration_ms=metrics.summarization_duration_ms,
    )


def _as_mapping(message: ProviderMessage) -> Dict[str, Any]:
    return {ROLE_FIELD: message.role, CONTENT_FIELD: message.content or ""}


def _as_provider_messages(
    compacted: Sequence[Dict[str, Any]], original: Sequence[ProviderMessage]
) -> List[ProviderMessage]:
    """The compacted history, keeping the original object where one survived.

    A message the compactor carried through unchanged is matched by its
    role and content, so the tool call it carries -- which the mapping
    the compactor works in does not represent -- survives.
    """

    survivors = {
        (message.role, message.content or ""): message for message in original
    }
    return [
        survivors.get(
            (entry.get(ROLE_FIELD, ""), entry.get(CONTENT_FIELD, "")),
            ProviderMessage(
                role=entry.get(ROLE_FIELD, ""), content=entry.get(CONTENT_FIELD, "")
            ),
        )
        for entry in compacted
    ]
