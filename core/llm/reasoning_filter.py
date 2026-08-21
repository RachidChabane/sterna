"""
Reasoning Content Filter for System Prompt Leak Prevention

Filters reasoning/thinking content server-side before it reaches the frontend.
Uses fingerprint-based sliding window matching to detect when the LLM echoes
or paraphrases system prompt content in its reasoning output.

The system prompt remains fully intact for the LLM — only the reasoning
output displayed to users is filtered.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ReasoningFilterConfig:
    """Configuration for the reasoning content filter."""
    min_ngram_size: int = 4
    max_ngram_size: int = 8
    buffer_word_count: int = 12
    redaction_text: str = "[...]"
    enabled: bool = True
    excluded_section_ids: Set[str] = field(default_factory=lambda: {"language", "datetime"})


def _normalize_text(text: str) -> str:
    """Normalize text for fingerprint comparison.

    Lowercases, strips markdown formatting, collapses whitespace.
    """
    text = text.lower()
    # Strip markdown formatting characters
    text = re.sub(r'[#*_\[\](){}|>`~]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_ngrams(words: List[str], min_n: int, max_n: int) -> Set[str]:
    """Extract word-level n-grams from a list of normalized words."""
    ngrams = set()
    for n in range(min_n, max_n + 1):
        for i in range(len(words) - n + 1):
            ngram = " ".join(words[i:i + n])
            ngrams.add(ngram)
    return ngrams


class ReasoningFilter:
    """
    Filters reasoning content to prevent system prompt leaks.

    Uses fingerprint-based sliding window matching:
    1. Extracts word-level n-gram fingerprints from the system prompt
    2. Buffers incoming reasoning chunks in a sliding window
    3. Checks buffer against fingerprints, redacts matches
    """

    def __init__(self, system_prompt: str, config: Optional[ReasoningFilterConfig] = None):
        self._config = config or ReasoningFilterConfig()
        self._fingerprints: Set[str] = set()
        # Buffer stores (original_word, normalized_word) tuples
        self._buffer: List[Tuple[str, str]] = []
        self._partial_chunk: str = ""  # Leftover text that doesn't end on a word boundary

        if self._config.enabled and system_prompt:
            self._build_fingerprints(system_prompt)

        logger.debug(
            f"[ReasoningFilter] Initialized: {len(self._fingerprints)} fingerprints, "
            f"enabled={self._config.enabled}"
        )

    @classmethod
    def from_prompt_sections(
        cls,
        sections: list,
        config: Optional[ReasoningFilterConfig] = None,
    ) -> "ReasoningFilter":
        """Create a filter from PromptSection objects, respecting excluded sections."""
        config = config or ReasoningFilterConfig()
        instance = cls.__new__(cls)
        instance._config = config
        instance._fingerprints = set()
        instance._buffer = []
        instance._partial_chunk = ""

        if not config.enabled:
            return instance

        for section in sections:
            section_id = getattr(section, 'id', '')
            if section_id in config.excluded_section_ids:
                continue
            content = getattr(section, 'content', '')
            if content:
                normalized = _normalize_text(content)
                words = normalized.split()
                if len(words) >= config.min_ngram_size:
                    instance._fingerprints |= _extract_ngrams(
                        words, config.min_ngram_size, config.max_ngram_size
                    )

        logger.debug(
            f"[ReasoningFilter] from_prompt_sections: {len(instance._fingerprints)} fingerprints"
        )
        return instance

    def _build_fingerprints(self, system_prompt: str) -> None:
        """Extract n-gram fingerprints from the system prompt."""
        # Split into sections by double newline
        sections = system_prompt.split("\n\n")

        for section_text in sections:
            normalized = _normalize_text(section_text)
            words = normalized.split()
            if len(words) < self._config.min_ngram_size:
                continue
            self._fingerprints |= _extract_ngrams(
                words, self._config.min_ngram_size, self._config.max_ngram_size
            )

    def _check_ngrams_in_buffer(self, buffer_words: List[Tuple[str, str]]) -> Optional[Tuple[int, int]]:
        """Check if any n-gram in the buffer matches a fingerprint.

        Returns (start_index, end_index) of the first match, or None.
        Checks largest n-grams first for greedy matching.
        """
        normalized_words = [nw for _, nw in buffer_words]
        max_n = min(self._config.max_ngram_size, len(normalized_words))

        for n in range(max_n, self._config.min_ngram_size - 1, -1):
            for i in range(len(normalized_words) - n + 1):
                ngram = " ".join(normalized_words[i:i + n])
                if ngram in self._fingerprints:
                    return (i, i + n)
        return None

    def filter_chunk(self, chunk: str) -> str:
        """Process a streaming chunk through the sliding window filter.

        Returns safe content to emit, or empty string if still buffering.
        """
        if not self._config.enabled or not self._fingerprints:
            return chunk

        # Combine with any leftover partial text
        text = self._partial_chunk + chunk
        self._partial_chunk = ""

        # Split into words, preserving the original text
        # If text doesn't end with whitespace, the last "word" might be partial
        tokens = re.split(r'(\s+)', text)
        # tokens alternates: [word, space, word, space, ..., word?]
        # Build word tuples, tracking original text
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token and not token.isspace():
                # Check if this is the last token and text doesn't end with whitespace
                if i == len(tokens) - 1 and text and not text[-1].isspace():
                    # This word might be incomplete, hold it
                    self._partial_chunk = token
                else:
                    # Complete word — include trailing whitespace
                    trailing = tokens[i + 1] if i + 1 < len(tokens) and tokens[i + 1].isspace() else ""
                    original = token + trailing
                    normalized = _normalize_text(token)
                    if normalized:
                        self._buffer.append((original, normalized))
            i += 1

        # Now check buffer for matches and emit safe content
        output_parts = []

        while True:
            match = self._check_ngrams_in_buffer(self._buffer)

            if match is not None:
                start, end = match
                # Emit words before the match
                for orig, _ in self._buffer[:start]:
                    output_parts.append(orig)
                # Emit redaction
                output_parts.append(self._config.redaction_text)
                # Keep words after the match
                self._buffer = self._buffer[end:]
                # Continue checking for more matches in remaining buffer
                continue

            # No match found
            if len(self._buffer) > self._config.buffer_word_count:
                # Emit oldest words, keep trailing window
                emit_count = len(self._buffer) - self._config.buffer_word_count
                for orig, _ in self._buffer[:emit_count]:
                    output_parts.append(orig)
                self._buffer = self._buffer[emit_count:]

            break

        return "".join(output_parts)

    def filter_text(self, text: str) -> str:
        """Filter a complete text in one pass (non-streaming).

        Creates a temporary sliding window and processes the entire text at once.
        Does not affect the streaming buffer state.
        """
        if not self._config.enabled or not self._fingerprints or not text:
            return text

        # Save current state
        saved_buffer = self._buffer
        saved_partial = self._partial_chunk
        self._buffer = []
        self._partial_chunk = ""

        result = self.filter_chunk(text) + self.flush()

        # Restore state
        self._buffer = saved_buffer
        self._partial_chunk = saved_partial

        return result

    def flush(self) -> str:
        """Emit all remaining buffer content at end of stream, with a final check."""
        if not self._config.enabled or not self._fingerprints:
            result = self._partial_chunk
            self._partial_chunk = ""
            self._buffer = []
            return result

        # Add any remaining partial chunk as a word
        if self._partial_chunk:
            normalized = _normalize_text(self._partial_chunk)
            if normalized:
                self._buffer.append((self._partial_chunk, normalized))
            self._partial_chunk = ""

        # Final match check on remaining buffer
        output_parts = []

        while True:
            match = self._check_ngrams_in_buffer(self._buffer)
            if match is not None:
                start, end = match
                for orig, _ in self._buffer[:start]:
                    output_parts.append(orig)
                output_parts.append(self._config.redaction_text)
                self._buffer = self._buffer[end:]
                continue
            break

        # Emit everything remaining
        for orig, _ in self._buffer:
            output_parts.append(orig)
        self._buffer = []

        return "".join(output_parts)
