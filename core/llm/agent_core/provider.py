"""The port through which the agent execution loop reaches a model.

Defines the boundary between the loop and any specific model SDK or
HTTP client, so the loop depends on an abstraction rather than on a
concrete provider implementation: a `ModelProvider` streams a chat
completion for a `ChatCompletionRequest` as an async sequence of
typed `ProviderChunk`s, and raises a `provider_errors.ProviderError`
subtype when the request fails.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import AsyncIterator, ClassVar, List, Optional, Union

from .events import JsonDict, ToolCall, Usage

# --- Request shape ----------------------------------------------------

MessageRole = str
"""One of `"system"`, `"user"`, `"assistant"`, `"tool"` — the OpenAI-shaped role a `ProviderMessage` carries."""


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderMessage:
    """One message in the conversation sent to the model.

    `tool_calls` is populated on an assistant message that called
    tools; `tool_call_id`/`name` are populated on the tool-role
    message that answers one of those calls.
    """

    role: MessageRole
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclasses.dataclass(frozen=True, slots=True)
class ToolFunctionDefinition:
    """The `function` member of an OpenAI-shaped tool definition."""

    name: str
    description: str
    parameters: JsonDict


@dataclasses.dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One tool offered to the model, in OpenAI function-calling shape."""

    function: ToolFunctionDefinition
    type: str = "function"


@dataclasses.dataclass(frozen=True, slots=True)
class ChatCompletionRequest:
    """Everything needed to ask a provider for one streamed chat completion.

    `tool_choice` is passed through verbatim (a literal like `"auto"`
    or `"none"`, or a JSON object naming a specific tool) since its
    shape is defined by the wire protocol, not by this port.
    `extra` carries provider-specific fields the port has no opinion
    on (a reasoning-effort flag, a provider-routing preference).
    """

    model: str
    messages: List[ProviderMessage]
    tools: Optional[List[ToolDefinition]] = None
    tool_choice: Optional[Union[str, JsonDict]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    extra: Optional[JsonDict] = None


# --- Streamed chunk shape ----------------------------------------------

class ProviderChunkType(StrEnum):
    """Discriminates the payload shape of one `ProviderChunk`."""

    GENERATION_ID = "generation_id"
    CONTENT_DELTA = "content_delta"
    REASONING_DELTA = "reasoning_delta"
    IMAGE = "image"
    TOOL_CALL_DELTA = "tool_call_delta"
    USAGE = "usage"
    DONE = "done"


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderGenerationIdChunk:
    """The id of the generation the rest of this stream belongs to.

    Yielded once, before any other chunk, so a caller can look up
    precise billing for the generation even if the stream is
    interrupted right after.
    """

    chunk_type: ClassVar[ProviderChunkType] = ProviderChunkType.GENERATION_ID
    generation_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderContentDeltaChunk:
    """One streamed fragment of the model's visible reply."""

    chunk_type: ClassVar[ProviderChunkType] = ProviderChunkType.CONTENT_DELTA
    content: str


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderReasoningDeltaChunk:
    """One streamed fragment of the model's reasoning trace."""

    chunk_type: ClassVar[ProviderChunkType] = ProviderChunkType.REASONING_DELTA
    content: str


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderImageChunk:
    """One image produced by a model with image output."""

    chunk_type: ClassVar[ProviderChunkType] = ProviderChunkType.IMAGE
    image: str


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderToolCallDeltaChunk:
    """One fragment of one tool call, positioned by `index`.

    A single tool call arrives across several chunks sharing the
    same `index`: an id and function name first, then successive
    `arguments_delta` fragments to concatenate. Any field absent from
    a given fragment is `None`.
    """

    chunk_type: ClassVar[ProviderChunkType] = ProviderChunkType.TOOL_CALL_DELTA
    index: int
    id: Optional[str] = None
    name: Optional[str] = None
    arguments_delta: Optional[str] = None


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderUsageChunk:
    """Token and cost accounting for the generation.

    `cost` and `upstream_inference_cost` are `None` when the provider
    does not report cost accounting for the request.
    """

    chunk_type: ClassVar[ProviderChunkType] = ProviderChunkType.USAGE
    usage: Usage
    cost: Optional[float] = None
    upstream_inference_cost: Optional[float] = None


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderDoneChunk:
    """How the turn ended, for the choice this chunk reports on.

    `finish_reason` is the provider's raw value (`"stop"`,
    `"tool_calls"`, `"length"`, `"content_filter"`, ...); mapping it
    onto the wire-facing `events.FinishReason` is the caller's job,
    since the two vocabularies do not line up one-to-one. A
    `ProviderUsageChunk` can still follow this chunk in the same
    stream — it is not necessarily the last one.
    """

    chunk_type: ClassVar[ProviderChunkType] = ProviderChunkType.DONE
    finish_reason: Optional[str]


ProviderChunk = Union[
    ProviderGenerationIdChunk,
    ProviderContentDeltaChunk,
    ProviderReasoningDeltaChunk,
    ProviderImageChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
    ProviderDoneChunk,
]
"""Every payload shape a provider stream can yield."""


# --- The port ------------------------------------------------------------

class ModelProvider(ABC):
    """A model backend the agent execution loop can stream a turn from.

    Implementations raise a `provider_errors.ProviderError` subtype
    for any failure — an auth rejection, a rate limit, an overloaded
    backend — rather than letting a transport-specific exception
    escape the port.
    """

    @abstractmethod
    def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderChunk]:
        """Stream one chat completion as a sequence of `ProviderChunk`s."""
        raise NotImplementedError
