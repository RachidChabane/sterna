"""Pure parsing for the OpenRouter chat-completions SSE wire format.

Kept independent of any transport so the parsing rules — which line
prefixes carry a payload, which fields of a decoded chunk become
which `ProviderChunk`, which top-level shape signals a mid-stream
error — are unit-testable without an HTTP client.
"""

from __future__ import annotations

from typing import Iterable, Iterator, List, Optional

from .events import JsonDict, Usage
from .provider import (
    ProviderChunk,
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderImageChunk,
    ProviderReasoningDeltaChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)

DONE_MARKER = "[DONE]"
_DATA_PREFIX = "data: "
_DATA_PREFIX_NO_SPACE = "data:"


def sse_payload(line: str) -> Optional[str]:
    """The `data:` payload carried by one SSE line, or `None` for a blank line or comment.

    A comment line — a keep-alive OpenRouter sends to hold the
    connection open — starts with `:` and carries no payload.
    """
    if not line or line.startswith(":"):
        return None
    if line.startswith(_DATA_PREFIX):
        return line[len(_DATA_PREFIX):]
    if line.startswith(_DATA_PREFIX_NO_SPACE):
        return line[len(_DATA_PREFIX_NO_SPACE):].lstrip()
    return None


def iter_sse_payloads(lines: Iterable[str]) -> Iterator[str]:
    """Yield the `data:` payload of every line in `lines` that carries one."""
    for line in lines:
        payload = sse_payload(line)
        if payload is not None:
            yield payload


def extract_stream_error(raw: JsonDict) -> Optional[JsonDict]:
    """The `error` object of a mid-stream error payload, if this chunk is one."""
    error = raw.get("error")
    return error if isinstance(error, dict) else None


def parse_stream_chunk(raw: JsonDict) -> List[ProviderChunk]:
    """Convert one decoded chat-completion-chunk object into `ProviderChunk`s.

    Order matches how a caller should act on them: the generation id
    first (when this chunk carries one), then usage (a provider's
    final chunk carries both `finish_reason` and `usage` together, so
    usage must reach the caller before a done chunk that might end
    its read of the stream), then per-choice deltas and that choice's
    terminal chunk.
    """
    chunks: List[ProviderChunk] = []

    generation_id = raw.get("id")
    if generation_id:
        chunks.append(ProviderGenerationIdChunk(generation_id=generation_id))

    usage = raw.get("usage")
    if usage is not None:
        chunks.append(_parse_usage(usage))

    for choice in raw.get("choices") or []:
        delta = choice.get("delta") or {}
        chunks.extend(_parse_delta(delta))

        finish_reason = choice.get("finish_reason")
        if finish_reason is not None:
            chunks.append(ProviderDoneChunk(finish_reason=finish_reason))

    return chunks


def _parse_delta(delta: JsonDict) -> List[ProviderChunk]:
    chunks: List[ProviderChunk] = []

    content = delta.get("content")
    if content:
        chunks.append(ProviderContentDeltaChunk(content=content))

    chunks.extend(_parse_tool_call_deltas(delta.get("tool_calls")))
    chunks.extend(_parse_reasoning(delta))
    chunks.extend(_parse_images(delta.get("images")))

    return chunks


def _parse_tool_call_deltas(tool_call_deltas: Optional[List[JsonDict]]) -> List[ProviderChunk]:
    if not tool_call_deltas:
        return []

    chunks: List[ProviderChunk] = []
    for tool_call_delta in tool_call_deltas:
        function = tool_call_delta.get("function") or {}
        chunks.append(
            ProviderToolCallDeltaChunk(
                index=tool_call_delta.get("index", 0),
                id=tool_call_delta.get("id"),
                name=function.get("name"),
                arguments_delta=function.get("arguments"),
            )
        )
    return chunks


def _parse_reasoning(delta: JsonDict) -> List[ProviderChunk]:
    reasoning_details = delta.get("reasoning_details")
    if isinstance(reasoning_details, list) and reasoning_details:
        chunks: List[ProviderChunk] = []
        for detail in reasoning_details:
            detail_type = detail.get("type", "")
            if detail_type == "reasoning.text":
                text = detail.get("text")
            elif detail_type == "reasoning.summary":
                text = detail.get("summary")
            else:
                text = None
            if text:
                chunks.append(ProviderReasoningDeltaChunk(content=text))
        return chunks

    reasoning = delta.get("reasoning")
    if reasoning:
        return [ProviderReasoningDeltaChunk(content=reasoning)]

    return []


def _parse_images(images: Optional[List]) -> List[ProviderChunk]:
    if not images:
        return []

    chunks: List[ProviderChunk] = []
    for image in images:
        if isinstance(image, dict):
            image_url = (image.get("image_url") or {}).get("url") or image.get("url")
        else:
            image_url = image
        if image_url:
            chunks.append(ProviderImageChunk(image=image_url))
    return chunks


def _parse_usage(usage: JsonDict) -> ProviderUsageChunk:
    cost_details = usage.get("cost_details") or {}
    return ProviderUsageChunk(
        usage=Usage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
        cost=usage.get("cost"),
        upstream_inference_cost=cost_details.get("upstream_inference_cost"),
    )
