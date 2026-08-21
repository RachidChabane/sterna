"""
Context Compaction Service

Implements automatic conversation compaction similar to Coding Agent.
When conversation context approaches the model's limit, this service:
1. Detects when compaction is needed based on token thresholds
2. Generates a structured summary of the conversation
3. Replaces the message history with the summary
4. Allows the conversation to continue seamlessly

Architecture follows SOLID principles:
- Single Responsibility: Each class has one focused purpose
- Open/Closed: Extensible via abstract base classes
- Liskov Substitution: Summarizers are interchangeable
- Interface Segregation: Small, focused interfaces
- Dependency Inversion: Depends on abstractions, not concretions

Usage:
    compactor = ContextCompactor(
        config=CompactionConfig(threshold_percentage=0.80),
        summarizer=ClaudeSummarizer(client=openai_client)
    )

    result = await compactor.compact_if_needed(
        messages=messages,
        model_context_limit=128000
    )

    if result.was_compacted:
        messages = result.compacted_messages
"""

import re
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Protocol
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Average characters per token (conservative estimate for multilingual content)
CHARS_PER_TOKEN = 4

# Default summary prompt based on Anthropic's recommendations
DEFAULT_SUMMARY_PROMPT = """You are summarizing a conversation to allow it to continue beyond context limits.

Create a comprehensive continuation summary that preserves everything needed to continue this conversation seamlessly. The summary should allow the conversation to continue as if it never stopped.

Include:

1. **USER'S ORIGINAL REQUEST**
   - The core task or question the user asked
   - Success criteria and constraints mentioned
   - Any specific requirements or preferences stated

2. **CONVERSATION PROGRESS**
   - What has been accomplished so far
   - Key decisions made and their rationale
   - Important code snippets, file paths, or technical details discussed
   - Any errors encountered and how they were resolved

3. **CURRENT STATE**
   - Where we left off in the task
   - Any pending actions or incomplete work
   - Files that were created, modified, or are being worked on

4. **CONTEXT TO PRESERVE**
   - User preferences discovered during conversation
   - Technical constraints or environment details
   - Names, IDs, URLs, or other specific identifiers mentioned
   - **Spark IDs**: If any sparks were created via create_spark tool, include their exact IDs (UUID format) so they can be updated later
   - Code patterns or architectural decisions established

5. **NEXT STEPS**
   - What should happen next to continue the task
   - Any questions that were pending

Format the summary clearly with the sections above. Be comprehensive but concise.
Wrap your entire response in <summary></summary> tags."""

# Minimum messages to keep (system + at least one exchange)
MIN_MESSAGES_TO_KEEP = 3

# Default context limits by model family (tokens)
DEFAULT_CONTEXT_LIMITS = {
    "gpt-4": 128000,
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385,
    "claude-3": 200000,
    "claude-3.5": 200000,
    "claude-3-5": 200000,
    "claude-sonnet": 200000,
    "claude-opus": 200000,
    "claude-haiku": 200000,
    "default": 128000,
}


# =============================================================================
# Data Classes
# =============================================================================

class CompactionStrategy(str, Enum):
    """Strategy for when to trigger compaction."""
    PERCENTAGE = "percentage"  # Trigger at X% of context limit
    TOKEN_COUNT = "token_count"  # Trigger at specific token count
    MESSAGE_COUNT = "message_count"  # Trigger after N messages


@dataclass
class CompactionConfig:
    """Configuration for context compaction behavior.

    Attributes:
        enabled: Whether compaction is enabled
        strategy: When to trigger compaction
        threshold_percentage: Trigger at this % of context limit (0.0-1.0)
        threshold_tokens: Trigger at this token count (if strategy is TOKEN_COUNT)
        threshold_messages: Trigger after this many messages (if strategy is MESSAGE_COUNT)
        summary_model: Model to use for summarization (None = use same model)
        summary_max_tokens: Max tokens for the summary response
        preserve_system_prompt: Always keep the system prompt
        preserve_first_user_message: Keep the first user message for context
        preserve_recent_messages: Number of recent messages to always keep
        custom_summary_prompt: Custom prompt for summarization (None = use default)
        notify_on_compaction: Whether to emit events when compaction occurs
    """
    enabled: bool = True
    strategy: CompactionStrategy = CompactionStrategy.PERCENTAGE
    threshold_percentage: float = 0.80  # 80% of context limit
    threshold_tokens: int = 100000
    threshold_messages: int = 50
    summary_model: Optional[str] = None
    summary_max_tokens: int = 4096
    preserve_system_prompt: bool = True
    preserve_first_user_message: bool = True
    preserve_recent_messages: int = 2  # Keep last N messages before summary request
    custom_summary_prompt: Optional[str] = None
    notify_on_compaction: bool = True

    def get_summary_prompt(self) -> str:
        """Get the summary prompt to use."""
        return self.custom_summary_prompt or DEFAULT_SUMMARY_PROMPT

    def get_threshold_tokens(self, model_context_limit: int) -> int:
        """Calculate the token threshold based on strategy."""
        if self.strategy == CompactionStrategy.PERCENTAGE:
            return int(model_context_limit * self.threshold_percentage)
        elif self.strategy == CompactionStrategy.TOKEN_COUNT:
            return self.threshold_tokens
        else:
            # For message count strategy, return a high number (checked separately)
            return model_context_limit


@dataclass
class CompactionMetrics:
    """Metrics about a compaction operation.

    Attributes:
        original_message_count: Number of messages before compaction
        original_token_estimate: Estimated tokens before compaction
        compacted_message_count: Number of messages after compaction
        compacted_token_estimate: Estimated tokens after compaction
        tokens_saved: Tokens saved by compaction
        compression_ratio: Ratio of compacted to original size
        summarization_duration_ms: Time taken to generate summary
    """
    original_message_count: int = 0
    original_token_estimate: int = 0
    compacted_message_count: int = 0
    compacted_token_estimate: int = 0
    tokens_saved: int = 0
    compression_ratio: float = 1.0
    summarization_duration_ms: int = 0

    def calculate_derived_metrics(self):
        """Calculate derived metrics after setting base values."""
        self.tokens_saved = self.original_token_estimate - self.compacted_token_estimate
        if self.original_token_estimate > 0:
            self.compression_ratio = self.compacted_token_estimate / self.original_token_estimate


@dataclass
class CompactionResult:
    """Result of a compaction operation.

    Attributes:
        was_compacted: Whether compaction was performed
        compacted_messages: The resulting message list (original if not compacted)
        summary_text: The generated summary (None if not compacted)
        metrics: Detailed metrics about the compaction
        error: Error message if compaction failed
    """
    was_compacted: bool
    compacted_messages: List[Dict[str, Any]]
    summary_text: Optional[str] = None
    metrics: CompactionMetrics = field(default_factory=CompactionMetrics)
    error: Optional[str] = None

    @classmethod
    def unchanged(cls, messages: List[Dict[str, Any]]) -> "CompactionResult":
        """Create a result indicating no compaction was needed."""
        return cls(
            was_compacted=False,
            compacted_messages=messages,
            metrics=CompactionMetrics(
                original_message_count=len(messages),
                compacted_message_count=len(messages),
            )
        )

    @classmethod
    def failed(cls, messages: List[Dict[str, Any]], error: str) -> "CompactionResult":
        """Create a result indicating compaction failed."""
        return cls(
            was_compacted=False,
            compacted_messages=messages,
            error=error,
            metrics=CompactionMetrics(
                original_message_count=len(messages),
                compacted_message_count=len(messages),
            )
        )


# =============================================================================
# Token Estimation
# =============================================================================

class TokenEstimator(Protocol):
    """Protocol for token estimation strategies."""

    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in a text string."""
        ...

    def estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate the total tokens in a list of messages."""
        ...


class CharacterBasedTokenEstimator:
    """Estimates tokens based on character count.

    Uses a configurable characters-per-token ratio.
    Fast and works without requiring a tokenizer library.
    """

    def __init__(self, chars_per_token: float = CHARS_PER_TOKEN):
        """Initialize with characters per token ratio.

        Args:
            chars_per_token: Average characters per token (default: 4)
        """
        self.chars_per_token = chars_per_token

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens from character count."""
        if not text:
            return 0
        return max(1, int(len(text) / self.chars_per_token))

    def estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate total tokens across all messages.

        Accounts for message structure overhead (~4 tokens per message).
        """
        total = 0
        message_overhead = 4  # Approximate overhead for role, etc.

        for message in messages:
            total += message_overhead
            content = message.get("content", "")

            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                # Handle structured content (text blocks, tool calls, etc.)
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            total += self.estimate_tokens(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            # Tool calls have name + input
                            total += self.estimate_tokens(block.get("name", ""))
                            total += self.estimate_tokens(str(block.get("input", {})))
                        elif block.get("type") == "tool_result":
                            total += self.estimate_tokens(str(block.get("content", "")))
                    elif isinstance(block, str):
                        total += self.estimate_tokens(block)

            # Account for tool_calls in OpenAI format
            tool_calls = message.get("tool_calls", [])
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    func = tool_call.get("function", {})
                    total += self.estimate_tokens(func.get("name", ""))
                    total += self.estimate_tokens(func.get("arguments", ""))

        return total


# =============================================================================
# Summarization
# =============================================================================

class MessageSummarizer(ABC):
    """Abstract base class for conversation summarizers.

    Implementations generate summaries of conversation history
    that preserve context for continuation.
    """

    @abstractmethod
    async def summarize(
        self,
        messages: List[Dict[str, Any]],
        summary_prompt: str,
        max_tokens: int = 4096,
    ) -> Tuple[str, int]:
        """Generate a summary of the conversation.

        Args:
            messages: The conversation messages to summarize
            summary_prompt: Prompt instructing how to summarize
            max_tokens: Maximum tokens for the summary

        Returns:
            Tuple of (summary_text, tokens_used)

        Raises:
            SummarizationError: If summarization fails
        """
        pass

    def extract_summary_content(self, response_text: str) -> str:
        """Extract summary from <summary></summary> tags.

        Args:
            response_text: The full response from the summarizer

        Returns:
            The extracted summary, or full response if tags not found
        """
        # Try to extract content from summary tags
        match = re.search(r'<summary>(.*?)</summary>', response_text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: return the whole response
        logger.warning("Summary tags not found in response, using full response")
        return response_text.strip()


class SummarizationError(Exception):
    """Raised when summarization fails."""
    pass


class OpenAICompatibleSummarizer(MessageSummarizer):
    """Summarizer using OpenAI-compatible API (works with OpenRouter, etc.).

    Uses the same client/API as the main conversation but can use
    a different model for summarization if configured.
    """

    def __init__(
        self,
        client: Any,  # OpenAI or compatible client
        model: Optional[str] = None,
        default_model: str = "gpt-4o",
    ):
        """Initialize the summarizer.

        Args:
            client: OpenAI-compatible async client
            model: Specific model to use (None = use default)
            default_model: Fallback model if none specified
        """
        self.client = client
        self.model = model or default_model

    async def summarize(
        self,
        messages: List[Dict[str, Any]],
        summary_prompt: str,
        max_tokens: int = 4096,
    ) -> Tuple[str, int]:
        """Generate summary using the OpenAI-compatible API."""
        try:
            # Build the summarization request
            # Include conversation history + summary prompt
            summary_messages = messages.copy()
            summary_messages.append({
                "role": "user",
                "content": summary_prompt
            })

            # Remove tool definitions for summarization (not needed, saves tokens)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=summary_messages,
                max_tokens=max_tokens,
                temperature=0.3,  # Lower temperature for consistent summaries
            )

            summary_text = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0

            # Extract from summary tags
            extracted = self.extract_summary_content(summary_text)

            return extracted, tokens_used

        except Exception as e:
            logger.error(f"Summarization failed: {e}", exc_info=True)
            raise SummarizationError(f"Failed to generate summary: {e}") from e


class LangChainSummarizer(MessageSummarizer):
    """Summarizer using LangChain chat model.

    Integrates with existing LangChain infrastructure.
    """

    def __init__(
        self,
        chat_model: Any,  # LangChain BaseChatModel
    ):
        """Initialize with a LangChain chat model.

        Args:
            chat_model: LangChain chat model instance
        """
        self.chat_model = chat_model

    async def summarize(
        self,
        messages: List[Dict[str, Any]],
        summary_prompt: str,
        max_tokens: int = 4096,
    ) -> Tuple[str, int]:
        """Generate summary using LangChain chat model."""
        try:
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

            # Convert dict messages to LangChain format
            lc_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                # Handle structured content
                if isinstance(content, list):
                    # Extract text content
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = "\n".join(text_parts)

                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
                else:
                    lc_messages.append(HumanMessage(content=content))

            # Add summary request
            lc_messages.append(HumanMessage(content=summary_prompt))

            # Generate summary
            response = await self.chat_model.ainvoke(lc_messages)

            summary_text = response.content
            # LangChain doesn't always provide token counts
            tokens_used = getattr(response, "usage_metadata", {}).get("total_tokens", 0)

            # Extract from summary tags
            extracted = self.extract_summary_content(summary_text)

            return extracted, tokens_used

        except Exception as e:
            logger.error(f"LangChain summarization failed: {e}", exc_info=True)
            raise SummarizationError(f"Failed to generate summary: {e}") from e


# =============================================================================
# Context Compactor
# =============================================================================

class ContextCompactor:
    """Orchestrates context compaction for conversations.

    Monitors conversation size and triggers compaction when thresholds
    are exceeded. Generates summaries and rebuilds the message list
    to allow conversations to continue beyond context limits.

    Example:
        compactor = ContextCompactor(
            config=CompactionConfig(threshold_percentage=0.80),
            summarizer=OpenAICompatibleSummarizer(client),
            token_estimator=CharacterBasedTokenEstimator()
        )

        result = await compactor.compact_if_needed(
            messages=conversation_messages,
            model_context_limit=128000
        )

        if result.was_compacted:
            # Use compacted messages for next API call
            messages = result.compacted_messages
    """

    def __init__(
        self,
        config: CompactionConfig,
        summarizer: MessageSummarizer,
        token_estimator: Optional[TokenEstimator] = None,
    ):
        """Initialize the context compactor.

        Args:
            config: Compaction configuration
            summarizer: Summarizer implementation to use
            token_estimator: Token estimator (default: CharacterBasedTokenEstimator)
        """
        self.config = config
        self.summarizer = summarizer
        self.token_estimator = token_estimator or CharacterBasedTokenEstimator()

    def needs_compaction(
        self,
        messages: List[Dict[str, Any]],
        model_context_limit: int,
    ) -> Tuple[bool, int]:
        """Check if compaction is needed.

        Args:
            messages: Current conversation messages
            model_context_limit: Model's context window size in tokens

        Returns:
            Tuple of (needs_compaction, current_token_count)
        """
        if not self.config.enabled:
            return False, 0

        # Check message count threshold
        if self.config.strategy == CompactionStrategy.MESSAGE_COUNT:
            if len(messages) >= self.config.threshold_messages:
                token_estimate = self.token_estimator.estimate_messages_tokens(messages)
                return True, token_estimate
            return False, 0

        # Check token threshold
        token_estimate = self.token_estimator.estimate_messages_tokens(messages)
        threshold = self.config.get_threshold_tokens(model_context_limit)

        needs_it = token_estimate >= threshold

        if needs_it:
            logger.info(
                f"[Compaction] Threshold exceeded: {token_estimate:,} tokens >= "
                f"{threshold:,} threshold ({self.config.threshold_percentage:.0%} of {model_context_limit:,})"
            )

        return needs_it, token_estimate

    def _extract_messages_to_preserve(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract messages that should be preserved vs summarized.

        Returns:
            Tuple of (preserved_start, to_summarize, preserved_end)
        """
        preserved_start = []
        preserved_end = []

        if not messages:
            return [], [], []

        start_idx = 0
        end_idx = len(messages)

        # Preserve system prompt if configured
        if self.config.preserve_system_prompt and messages[0].get("role") == "system":
            preserved_start.append(messages[0])
            start_idx = 1

        # Preserve first user message if configured
        if self.config.preserve_first_user_message and start_idx < len(messages):
            for i in range(start_idx, len(messages)):
                if messages[i].get("role") == "user":
                    preserved_start.append(messages[i])
                    start_idx = i + 1
                    break

        # Preserve recent messages
        if self.config.preserve_recent_messages > 0:
            preserve_count = min(self.config.preserve_recent_messages, len(messages) - start_idx)
            if preserve_count > 0:
                end_idx = len(messages) - preserve_count
                preserved_end = messages[end_idx:]

        # Messages to summarize
        to_summarize = messages[start_idx:end_idx]

        # Ensure we have enough messages to actually summarize
        if len(to_summarize) < MIN_MESSAGES_TO_KEEP:
            # Not enough to summarize, return original
            return messages, [], []

        return preserved_start, to_summarize, preserved_end

    async def compact(
        self,
        messages: List[Dict[str, Any]],
        model_context_limit: int,
    ) -> CompactionResult:
        """Perform compaction on the message list.

        Args:
            messages: Current conversation messages
            model_context_limit: Model's context window size in tokens

        Returns:
            CompactionResult with compacted messages
        """
        start_time = time.time()
        metrics = CompactionMetrics()
        metrics.original_message_count = len(messages)
        metrics.original_token_estimate = self.token_estimator.estimate_messages_tokens(messages)

        # Extract messages to preserve vs summarize
        preserved_start, to_summarize, preserved_end = self._extract_messages_to_preserve(messages)

        if not to_summarize:
            logger.warning("[Compaction] Not enough messages to summarize, skipping")
            return CompactionResult.unchanged(messages)

        logger.info(
            f"[Compaction] Compacting {len(to_summarize)} messages "
            f"(preserving {len(preserved_start)} start, {len(preserved_end)} end)"
        )

        try:
            # Generate summary of the middle messages
            # Include preserved_start for context but don't include in summary
            context_messages = preserved_start + to_summarize

            summary_text, tokens_used = await self.summarizer.summarize(
                messages=context_messages,
                summary_prompt=self.config.get_summary_prompt(),
                max_tokens=self.config.summary_max_tokens,
            )

            # Build compacted message list
            compacted_messages = []

            # Add preserved start (system prompt, first user message)
            compacted_messages.extend(preserved_start)

            # Add summary as an assistant message with clear marker
            summary_message = {
                "role": "assistant",
                "content": f"[Previous conversation summarized due to context limits]\n\n{summary_text}"
            }
            compacted_messages.append(summary_message)

            # Add preserved end (recent messages)
            compacted_messages.extend(preserved_end)

            # Calculate metrics
            duration_ms = int((time.time() - start_time) * 1000)
            metrics.compacted_message_count = len(compacted_messages)
            metrics.compacted_token_estimate = self.token_estimator.estimate_messages_tokens(compacted_messages)
            metrics.summarization_duration_ms = duration_ms
            metrics.calculate_derived_metrics()

            logger.info(
                f"[Compaction] Complete: {metrics.original_message_count} -> "
                f"{metrics.compacted_message_count} messages, "
                f"{metrics.original_token_estimate:,} -> {metrics.compacted_token_estimate:,} tokens "
                f"({metrics.compression_ratio:.1%} of original, saved {metrics.tokens_saved:,} tokens) "
                f"in {duration_ms}ms"
            )

            return CompactionResult(
                was_compacted=True,
                compacted_messages=compacted_messages,
                summary_text=summary_text,
                metrics=metrics,
            )

        except SummarizationError as e:
            logger.error(f"[Compaction] Summarization failed: {e}")
            return CompactionResult.failed(messages, str(e))
        except Exception as e:
            logger.error(f"[Compaction] Unexpected error: {e}", exc_info=True)
            return CompactionResult.failed(messages, str(e))

    async def compact_if_needed(
        self,
        messages: List[Dict[str, Any]],
        model_context_limit: int,
    ) -> CompactionResult:
        """Check if compaction is needed and perform it if so.

        This is the main entry point for automatic compaction.

        Args:
            messages: Current conversation messages
            model_context_limit: Model's context window size in tokens

        Returns:
            CompactionResult (may or may not have been compacted)
        """
        needs_it, token_count = self.needs_compaction(messages, model_context_limit)

        if not needs_it:
            return CompactionResult.unchanged(messages)

        return await self.compact(messages, model_context_limit)


# =============================================================================
# Utility Functions
# =============================================================================

def get_model_context_limit(model_id: str) -> int:
    """Get the context limit for a model.

    Args:
        model_id: The model identifier (e.g., "gpt-4o", "claude-3-sonnet")

    Returns:
        Context limit in tokens
    """
    model_lower = model_id.lower()

    # Check for exact or partial matches
    for key, limit in DEFAULT_CONTEXT_LIMITS.items():
        if key in model_lower:
            return limit

    # Default fallback
    return DEFAULT_CONTEXT_LIMITS["default"]


def create_compactor_for_langchain(
    chat_model: Any,
    config: Optional[CompactionConfig] = None,
) -> ContextCompactor:
    """Factory function to create a compactor for LangChain usage.

    Args:
        chat_model: LangChain chat model instance
        config: Optional custom configuration

    Returns:
        Configured ContextCompactor instance
    """
    return ContextCompactor(
        config=config or CompactionConfig(),
        summarizer=LangChainSummarizer(chat_model),
        token_estimator=CharacterBasedTokenEstimator(),
    )


def create_compactor_for_openai(
    client: Any,
    model: Optional[str] = None,
    config: Optional[CompactionConfig] = None,
) -> ContextCompactor:
    """Factory function to create a compactor for OpenAI-compatible APIs.

    Args:
        client: OpenAI-compatible async client
        model: Model to use for summarization
        config: Optional custom configuration

    Returns:
        Configured ContextCompactor instance
    """
    return ContextCompactor(
        config=config or CompactionConfig(),
        summarizer=OpenAICompatibleSummarizer(client, model=model),
        token_estimator=CharacterBasedTokenEstimator(),
    )
