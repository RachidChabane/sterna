"""Separation of reasoning from answer text in a streamed response.

State machine. Models without native reasoning support wrap their chain
of thought in ``<think>...</think>``; this parser consumes content chunks
and classifies each fragment as ``content`` or ``reasoning``, holding back
a short lookahead so a tag split across two chunks is not mistaken for
prose.

It also enforces one hard invariant: a tool call must never appear inside
a reasoning block. When it does, the parser yields an ``error`` and stops
rather than letting the malformed call reach the tool dispatcher.
"""

import logging

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# How much of an offending reasoning block is logged for diagnosis.
REASONING_SNIPPET_CHARS = 300

# Tokens that must never appear inside a reasoning block: their presence
# means the model emitted a tool call where prose was expected.
TOOL_CALL_MARKERS_IN_REASONING = (
    'tool_call', 'brave_web_search', 'brave_image_search', 'brave_video_search',
    'brave_local_search', 'brave_news_search', 'geocode_address', 'get_directions',
    'search_nearby_places', 'get_air_quality', 'get_street_view',
    'list_files', 'read_file', 'write_file', 'execute_code',
    'tool__calls__begin', 'tool__call__begin', 'tool__sep', 'tool__call__end',
    '<tool_call', '</tool_call',
)

THINK_OPEN_TAG = '<think>'
THINK_CLOSE_TAG = '</think>'
# Bytes held back so a tag straddling two chunks is not emitted as prose.
# Sized to the longest tag we look for.
TAG_LOOKAHEAD = 8

EVENT_CONTENT = 'content'
EVENT_REASONING = 'reasoning'
EVENT_ERROR = 'error'
ERROR_TOOL_CALL_IN_REASONING = 'tool_call_in_reasoning'


def contains_tool_call_markers(reasoning_chunk: str) -> bool:
    """Whether a reasoning fragment smuggles a tool call.

    Whitespace is stripped first so spaced-out XML tags still match.
    """
    normalized_chunk = reasoning_chunk.replace(' ', '')
    return any(marker in normalized_chunk for marker in TOOL_CALL_MARKERS_IN_REASONING)


class ThinkingContentParser:
    """Splits a `<think>`-tagged token stream into content and reasoning."""

    def __init__(self, enable_reasoning: bool):
        self.enable_reasoning = enable_reasoning
        self.accumulated_buffer = ""
        self.in_think_block = False

    def reset(self) -> None:
        """Clear buffered state (called at the start of each iteration)."""
        self.accumulated_buffer = ""
        self.in_think_block = False

    def process(self, content: str):
        """
        Process content chunk and extract reasoning from <think>...</think> tags.

        Yields:
            Tuples of (event_type, content) where event_type is 'content' or 'reasoning'
        """
        if not self.enable_reasoning:
            # If reasoning is disabled, just return content as-is
            yield (EVENT_CONTENT, content)
            return

        self.accumulated_buffer += content

        while self.accumulated_buffer:
            if THINK_OPEN_TAG in self.accumulated_buffer and not self.in_think_block:
                think_start = self.accumulated_buffer.index(THINK_OPEN_TAG)

                # Content before <think> is regular response content
                before_think = self.accumulated_buffer[:think_start]
                if before_think:
                    yield (EVENT_CONTENT, before_think)

                self.accumulated_buffer = self.accumulated_buffer[think_start + len(THINK_OPEN_TAG):]
                self.in_think_block = True
                continue

            if THINK_CLOSE_TAG in self.accumulated_buffer and self.in_think_block:
                think_end = self.accumulated_buffer.index(THINK_CLOSE_TAG)

                # Content before </think> is reasoning content
                reasoning_chunk = self.accumulated_buffer[:think_end]
                if reasoning_chunk:
                    if contains_tool_call_markers(reasoning_chunk):
                        logger.error(
                            "langchain.tool_call_in_reasoning",
                            extra={"reasoning_snippet": reasoning_chunk[:REASONING_SNIPPET_CHARS]},
                        )
                        # Signal the caller to stop the stream gracefully.
                        yield (EVENT_ERROR, ERROR_TOOL_CALL_IN_REASONING)
                        return
                    yield (EVENT_REASONING, reasoning_chunk)

                self.accumulated_buffer = self.accumulated_buffer[think_end + len(THINK_CLOSE_TAG):]
                self.in_think_block = False
                continue

            # No complete tags found - emit what we can, keeping the
            # lookahead so a split tag is not mistaken for prose.
            if len(self.accumulated_buffer) > TAG_LOOKAHEAD:
                to_emit = self.accumulated_buffer[:-TAG_LOOKAHEAD]
                self.accumulated_buffer = self.accumulated_buffer[-TAG_LOOKAHEAD:]
                yield (EVENT_REASONING if self.in_think_block else EVENT_CONTENT, to_emit)
            break

    def flush(self):
        """Flush remaining buffer content at end of stream."""
        events = []
        if self.accumulated_buffer:
            events.append(
                (EVENT_REASONING if self.in_think_block else EVENT_CONTENT, self.accumulated_buffer)
            )
            self.reset()
        return events
