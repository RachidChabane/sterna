"""Typed model for the events the agent execution loop streams.

Both legacy streaming implementations — the hand-rolled OpenAI-client
loop and the LangChain-based agent — speak a shared vocabulary over
Server-Sent Events: a bare event name plus a JSON data payload. This
module gives that vocabulary a typed home: one dataclass per event
name, plus the enums for the values embedded inside a few of them
(`finish_reason`, an error's `code`). A single definition here is what
lets the execution loop built on top of it, and the harness that
replays it against recorded transcripts, agree on what each event
carries without re-deriving the shape from raw JSON on either side.

`EVENT_PAYLOAD_TYPES` maps every `EventType` to the dataclass that
carries its payload, so a reader (or a future deserializer) can go
from the wire name straight to the type without a chain of `if`s.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any, ClassVar, Dict, List, Optional, Union

JsonDict = Dict[str, Any]


class EventType(StrEnum):
    """The `event:` field every streamed event carries on the wire."""

    GENERATION_ID = "generation_id"
    CONTENT = "content"
    REASONING = "reasoning"
    IMAGE = "image"
    HEARTBEAT = "heartbeat"
    USAGE_UPDATE = "usage_update"
    WEB_SOURCES = "web_sources"
    PREVIEW_STARTED = "preview_started"
    CONTEXT_TRIMMED = "context_trimmed"
    CONTEXT_COMPACTED = "context_compacted"
    TOOL_CALL_REQUEST = "tool_call_request"
    FILE_TOOL_EXECUTING = "file_tool_executing"
    FILE_TOOL_EXECUTED = "file_tool_executed"
    CODING_AGENT_STEP = "coding_agent_step"
    CODING_AGENT_QUESTION = "coding_agent_question"
    CODING_AGENT_COMPLETED = "coding_agent_completed"
    DONE = "done"
    ERROR = "error"


class FinishReason(StrEnum):
    """The `finish_reason` a `done` event reports."""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    CANCELLED = "cancelled"
    INVALID_TOOLS = "invalid_tools"


class ErrorCode(StrEnum):
    """The machine-readable `code` an `error` event may carry.

    Not every `error` event carries one — a bare provider failure
    reports only `error`/`detail`, with no `code` field at all.
    """

    NO_TOOL_SUPPORT = "NO_TOOL_SUPPORT"
    CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    FEATURE_NOT_AVAILABLE = "FEATURE_NOT_AVAILABLE"


REASONING_ERROR_SLUG = "reasoning_error"
"""The `error` field value used when the model attempted an invalid
operation mid-reasoning. It fills the `error` field itself rather than
a `code`, so it is a plain constant rather than an `ErrorCode` member.
"""


# --- Shared value types -------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class ToolCallFunction:
    """The `function` member of an OpenAI-shaped tool call."""

    name: str
    arguments: str


@dataclasses.dataclass(frozen=True, slots=True)
class ToolCall:
    """An OpenAI-shaped tool call, optionally enriched for display."""

    id: str
    function: ToolCallFunction
    type: str = "function"
    display_name: Optional[str] = None
    server_icon_url: Optional[str] = None
    server_icon_invert: Optional[bool] = None


@dataclasses.dataclass(frozen=True, slots=True)
class Usage:
    """Token counts for one generation."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclasses.dataclass(frozen=True, slots=True)
class Approval:
    """A catalog-tool call awaiting user approval before it can run."""

    id: str
    tool_id: str
    tool_name: str
    tool_description: str
    server_name: str
    arguments: JsonDict
    status: str


@dataclasses.dataclass(frozen=True, slots=True)
class WebSource:
    """One search result surfaced to the frontend as a citation."""

    url: str
    title: str


# --- Event payloads -------------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class GenerationIdEvent:
    """Identifies the provider generation the following events belong to.

    A turn that calls tools and then continues emits this more than
    once: once per round-trip to the model.
    """

    event_type: ClassVar[EventType] = EventType.GENERATION_ID
    generation_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class ContentEvent:
    """One streamed fragment of the model's visible reply."""

    event_type: ClassVar[EventType] = EventType.CONTENT
    content: str


@dataclasses.dataclass(frozen=True, slots=True)
class ReasoningEvent:
    """One streamed fragment of the model's reasoning trace."""

    event_type: ClassVar[EventType] = EventType.REASONING
    content: str


@dataclasses.dataclass(frozen=True, slots=True)
class ImageEvent:
    """One image produced by a model with image output."""

    event_type: ClassVar[EventType] = EventType.IMAGE
    image: str


@dataclasses.dataclass(frozen=True, slots=True)
class HeartbeatEvent:
    """A keep-alive sent while a long-running tool call is in flight.

    Carries no `tool`/`elapsed_seconds` when it is a generic keep-alive
    rather than progress on a specific tool call.
    """

    event_type: ClassVar[EventType] = EventType.HEARTBEAT
    tool: Optional[str] = None
    elapsed_seconds: Optional[int] = None


@dataclasses.dataclass(frozen=True, slots=True)
class UsageUpdateEvent:
    """Running token/cost totals, sent so a stopped stream still has figures."""

    event_type: ClassVar[EventType] = EventType.USAGE_UPDATE
    usage: Usage
    cost: float
    prompt_cost: float
    completion_cost: float
    generation_id: str
    generation_ids: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True, slots=True)
class WebSourcesEvent:
    """The citations backing a web-search tool call."""

    event_type: ClassVar[EventType] = EventType.WEB_SOURCES
    sources: List[WebSource]


@dataclasses.dataclass(frozen=True, slots=True)
class PreviewStartedEvent:
    """A live preview process the `start_preview` tool launched."""

    event_type: ClassVar[EventType] = EventType.PREVIEW_STARTED
    port: Optional[int]
    command: Optional[str]
    pid: Optional[int]


@dataclasses.dataclass(frozen=True, slots=True)
class ContextTrimmedEvent:
    """The oldest message was dropped to fit the model's context window."""

    event_type: ClassVar[EventType] = EventType.CONTEXT_TRIMMED
    trimmed_count: int
    remaining_messages: int


@dataclasses.dataclass(frozen=True, slots=True)
class ContextCompactedEvent:
    """Older messages were summarized to fit the model's context window.

    `original_tokens`/`compacted_tokens`/`compression_ratio`/`duration_ms`
    are only present when the compactor measured them.
    """

    event_type: ClassVar[EventType] = EventType.CONTEXT_COMPACTED
    original_messages: int
    compacted_messages: int
    tokens_saved: int
    original_tokens: Optional[int] = None
    compacted_tokens: Optional[int] = None
    compression_ratio: Optional[float] = None
    duration_ms: Optional[int] = None


@dataclasses.dataclass(frozen=True, slots=True)
class ToolCallRequestEvent:
    """Catalog tool calls that need user approval before they can run."""

    event_type: ClassVar[EventType] = EventType.TOOL_CALL_REQUEST
    approvals: List[Approval]
    tool_calls: List[ToolCall]


@dataclasses.dataclass(frozen=True, slots=True)
class FileToolExecutingEvent:
    """One or more tool calls have started running.

    A placeholder call (id `"loading"`, function name `"..."`) may
    appear first, before the real tool call has fully streamed in.
    """

    event_type: ClassVar[EventType] = EventType.FILE_TOOL_EXECUTING
    tool_calls: List[ToolCall]


@dataclasses.dataclass(frozen=True, slots=True)
class FileToolExecutedEvent:
    """One or more tool calls finished running.

    `results` is left as raw JSON objects: the two legacy streaming
    paths shape a result entry differently (an OpenAI tool-role
    message versus a `{tool_call, result, success}` triple).
    """

    event_type: ClassVar[EventType] = EventType.FILE_TOOL_EXECUTED
    tool_calls: List[ToolCall]
    results: List[JsonDict]


@dataclasses.dataclass(frozen=True, slots=True)
class CodingAgentStepEvent:
    """One step of progress from a long-running coding-agent tool call."""

    event_type: ClassVar[EventType] = EventType.CODING_AGENT_STEP
    step_index: int
    type: str
    tool: Optional[str]
    content: Optional[str]
    timestamp: Optional[str]


@dataclasses.dataclass(frozen=True, slots=True)
class CodingAgentQuestionEvent:
    """A coding-agent tool call is blocked on a question for the user."""

    event_type: ClassVar[EventType] = EventType.CODING_AGENT_QUESTION
    question: Optional[str]
    options: Optional[List[str]]


@dataclasses.dataclass(frozen=True, slots=True)
class CodingAgentCompletedEvent:
    """A coding-agent tool call finished, successfully or not."""

    event_type: ClassVar[EventType] = EventType.CODING_AGENT_COMPLETED
    success: bool
    summary: Optional[str]
    files_modified: List[str]
    files_created: List[str]
    duration_ms: int
    total_tokens: int
    steps: List[JsonDict]


@dataclasses.dataclass(frozen=True, slots=True)
class DoneEvent:
    """The stream's terminal event: how the turn ended, and its totals.

    `usage` is the zero-valued `Usage(0, 0, 0)` for a turn that never
    reached the model (cancellation, invalid tools).
    """

    event_type: ClassVar[EventType] = EventType.DONE
    model: str
    finish_reason: FinishReason
    usage: Usage
    cost: float
    prompt_cost: Optional[float] = None
    completion_cost: Optional[float] = None
    tool_cost: Optional[float] = None
    tool_calls: Optional[List[ToolCall]] = None
    awaiting_approval: Optional[bool] = None
    approval_count: Optional[int] = None
    generation_id: Optional[str] = None
    generation_ids: Optional[List[str]] = None


@dataclasses.dataclass(frozen=True, slots=True)
class ErrorEvent:
    """A failure ended the turn.

    `code` is present only for the handful of errors the frontend
    reacts to programmatically; `extra` carries the additional fields
    a quota-exceeded error attaches from the underlying exception.
    """

    event_type: ClassVar[EventType] = EventType.ERROR
    error: str
    detail: Optional[str] = None
    code: Optional[ErrorCode] = None
    extra: Optional[JsonDict] = None


StreamEvent = Union[
    GenerationIdEvent,
    ContentEvent,
    ReasoningEvent,
    ImageEvent,
    HeartbeatEvent,
    UsageUpdateEvent,
    WebSourcesEvent,
    PreviewStartedEvent,
    ContextTrimmedEvent,
    ContextCompactedEvent,
    ToolCallRequestEvent,
    FileToolExecutingEvent,
    FileToolExecutedEvent,
    CodingAgentStepEvent,
    CodingAgentQuestionEvent,
    CodingAgentCompletedEvent,
    DoneEvent,
    ErrorEvent,
]
"""Every payload type an agent-core stream can emit, keyed by shape."""

EVENT_PAYLOAD_TYPES: Dict[EventType, type] = {
    payload_type.event_type: payload_type
    for payload_type in (
        GenerationIdEvent,
        ContentEvent,
        ReasoningEvent,
        ImageEvent,
        HeartbeatEvent,
        UsageUpdateEvent,
        WebSourcesEvent,
        PreviewStartedEvent,
        ContextTrimmedEvent,
        ContextCompactedEvent,
        ToolCallRequestEvent,
        FileToolExecutingEvent,
        FileToolExecutedEvent,
        CodingAgentStepEvent,
        CodingAgentQuestionEvent,
        CodingAgentCompletedEvent,
        DoneEvent,
        ErrorEvent,
    )
}
"""Maps the wire event name to the dataclass carrying its payload."""
