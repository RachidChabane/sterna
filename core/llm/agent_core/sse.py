"""Renders a typed stream event as the Server-Sent Event a client reads.

One event becomes one frame: an `event:` line naming it, a `data:` line
carrying its JSON payload, and a blank line closing the frame. Nothing
here is specific to a web framework — a frame is a string, and whoever
owns the response decides how it is written.

The order of the fields inside a payload is part of the wire format, so
each payload is assembled in the order the wire declares rather than
taken from the order of the dataclass that carries it. An optional
field with no value is left out of the payload rather than sent as
`null`, which is what distinguishes a figure the loop has from one it
does not.
"""

from __future__ import annotations

import json

from .events import (
    Approval,
    CodingAgentCompletedEvent,
    CodingAgentQuestionEvent,
    CodingAgentStepEvent,
    ContentEvent,
    ContextCompactedEvent,
    ContextTrimmedEvent,
    DoneEvent,
    ErrorEvent,
    FileToolExecutedEvent,
    FileToolExecutingEvent,
    GenerationIdEvent,
    HeartbeatEvent,
    ImageEvent,
    JsonDict,
    PreviewStartedEvent,
    ReasoningEvent,
    StreamEvent,
    ToolCall,
    ToolCallRequestEvent,
    Usage,
    UsageUpdateEvent,
    WebSource,
    WebSourcesEvent,
)

EVENT_LINE_PREFIX = "event: "
DATA_LINE_PREFIX = "data: "
LINE_SEPARATOR = "\n"
FRAME_TERMINATOR = "\n\n"


def render_frame(event_name: str, payload: JsonDict) -> str:
    """One SSE frame carrying `payload` under `event_name`."""

    return (
        f"{EVENT_LINE_PREFIX}{event_name}{LINE_SEPARATOR}"
        f"{DATA_LINE_PREFIX}{json.dumps(payload)}{FRAME_TERMINATOR}"
    )


def render_event(event: StreamEvent) -> str:
    """The SSE frame for one typed stream event."""

    return render_frame(str(event.event_type), event_payload(event))


def event_payload(event: StreamEvent) -> JsonDict:
    """The JSON object one event puts on its `data:` line."""

    if isinstance(event, GenerationIdEvent):
        return {"generation_id": event.generation_id}
    if isinstance(event, ContentEvent):
        return {"content": event.content}
    if isinstance(event, ReasoningEvent):
        return {"content": event.content}
    if isinstance(event, ImageEvent):
        return {"image": event.image}
    if isinstance(event, HeartbeatEvent):
        return _present({"tool": event.tool, "elapsed_seconds": event.elapsed_seconds})
    if isinstance(event, UsageUpdateEvent):
        return {
            "usage": _usage_payload(event.usage),
            "cost": event.cost,
            "prompt_cost": event.prompt_cost,
            "completion_cost": event.completion_cost,
            "generation_id": event.generation_id,
            "generation_ids": list(event.generation_ids),
        }
    if isinstance(event, WebSourcesEvent):
        return {"sources": [_web_source_payload(source) for source in event.sources]}
    if isinstance(event, PreviewStartedEvent):
        return _present(
            {"port": event.port, "command": event.command, "pid": event.pid}
        )
    if isinstance(event, ContextTrimmedEvent):
        return {
            "trimmed_count": event.trimmed_count,
            "remaining_messages": event.remaining_messages,
        }
    if isinstance(event, ContextCompactedEvent):
        return _present(
            {
                "original_messages": event.original_messages,
                "compacted_messages": event.compacted_messages,
                "tokens_saved": event.tokens_saved,
                "original_tokens": event.original_tokens,
                "compacted_tokens": event.compacted_tokens,
                "compression_ratio": event.compression_ratio,
                "duration_ms": event.duration_ms,
            }
        )
    if isinstance(event, ToolCallRequestEvent):
        return {
            "approvals": [_approval_payload(approval) for approval in event.approvals],
            "tool_calls": [tool_call_payload(call) for call in event.tool_calls],
        }
    if isinstance(event, FileToolExecutingEvent):
        return {"tool_calls": [tool_call_payload(call) for call in event.tool_calls]}
    if isinstance(event, FileToolExecutedEvent):
        return {
            "tool_calls": [tool_call_payload(call) for call in event.tool_calls],
            "results": [dict(result) for result in event.results],
        }
    if isinstance(event, CodingAgentStepEvent):
        return _present(
            {
                "step_index": event.step_index,
                "type": event.type,
                "tool": event.tool,
                "content": event.content,
                "timestamp": event.timestamp,
            }
        )
    if isinstance(event, CodingAgentQuestionEvent):
        return _present({"question": event.question, "options": event.options})
    if isinstance(event, CodingAgentCompletedEvent):
        return {
            "success": event.success,
            "summary": event.summary,
            "files_modified": list(event.files_modified),
            "files_created": list(event.files_created),
            "duration_ms": event.duration_ms,
            "total_tokens": event.total_tokens,
            "steps": [dict(step) for step in event.steps],
        }
    if isinstance(event, DoneEvent):
        return _done_payload(event)
    if isinstance(event, ErrorEvent):
        return _error_payload(event)
    raise TypeError(f"no SSE payload is defined for {type(event).__name__}")


def _done_payload(event: DoneEvent) -> JsonDict:
    tool_calls = event.tool_calls
    generation_ids = event.generation_ids
    return _present(
        {
            "model": event.model,
            "finish_reason": str(event.finish_reason),
            "usage": _usage_payload(event.usage),
            "cost": event.cost,
            "prompt_cost": event.prompt_cost,
            "completion_cost": event.completion_cost,
            "tool_calls": (
                None
                if tool_calls is None
                else [tool_call_payload(call) for call in tool_calls]
            ),
            "tool_cost": event.tool_cost,
            "awaiting_approval": event.awaiting_approval,
            "approval_count": event.approval_count,
            "generation_id": event.generation_id,
            "generation_ids": None if generation_ids is None else list(generation_ids),
        }
    )


def _error_payload(event: ErrorEvent) -> JsonDict:
    payload = _present(
        {
            "error": event.error,
            "detail": event.detail,
            "code": str(event.code) if event.code is not None else None,
        }
    )
    payload.update(event.extra or {})
    return payload


def tool_call_payload(call: ToolCall) -> JsonDict:
    return _present(
        {
            "id": call.id,
            "type": call.type,
            "function": {
                "name": call.function.name,
                "arguments": call.function.arguments,
            },
            "display_name": call.display_name,
            "server_icon_url": call.server_icon_url,
            "server_icon_invert": call.server_icon_invert,
        }
    )


def _approval_payload(approval: Approval) -> JsonDict:
    return {
        "id": approval.id,
        "tool_id": approval.tool_id,
        "tool_name": approval.tool_name,
        "tool_description": approval.tool_description,
        "server_name": approval.server_name,
        "arguments": dict(approval.arguments),
        "status": approval.status,
    }


def _usage_payload(usage: Usage) -> JsonDict:
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def _web_source_payload(source: WebSource) -> JsonDict:
    return {"url": source.url, "title": source.title}


def _present(fields: JsonDict) -> JsonDict:
    """`fields` without the entries that carry no value, order preserved."""

    return {name: value for name, value in fields.items() if value is not None}


