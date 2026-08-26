"""Renders a turn's typed events as the frames the V1 chat endpoint speaks.

`llm.agent_core` emits typed events and knows nothing about any
endpoint's format. The V1 stream-completion endpoint speaks a format
its clients parse as it stands, and that format differs from a plain
rendering of those events in seven ways:

* token and cost figures reach a client only on the terminal `done`
  event, and they are the running totals of the whole turn rather than
  the figures of the generation that just ended,
* each generation's cost figures are quantized to 8 decimal places as
  they fold into those totals,
* `done` reports the model, the finish reason and those totals, without
  naming the provider generations the turn spanned,
* a round of tool calls is announced once, after the calls have run,
  never as they start,
* a result is the OpenAI tool-role message that will be sent back to
  the model, not a call/result/success triple,
* a mid-stream failure carries the user-facing sentence alone, with no
  operator detail, machine code, or status attached,
* reasoning traces and generated images ride on `done` as
  `reasoning_content` and `images` rather than as frames of their own.

V1's event vocabulary is closed: an event outside it -- a keep-alive, a
citation, a context-relief notice -- is swallowed rather than shown to
a client that has never parsed one.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, AsyncIterator, List, Mapping

from ..agent_core import sse
from ..agent_core.events import (
    ContentEvent,
    DoneEvent,
    ErrorEvent,
    EventType,
    FileToolExecutedEvent,
    GenerationIdEvent,
    ImageEvent,
    JsonDict,
    ReasoningEvent,
    StreamEvent,
    ToolCallRequestEvent,
    UsageUpdateEvent,
)
from .accounting import TurnAccounting

TOOL_ROLE = "tool"

ROLE_FIELD = "role"
TOOL_CALL_ID_FIELD = "tool_call_id"
NAME_FIELD = "name"
CONTENT_FIELD = "content"
TOOL_CALLS_FIELD = "tool_calls"
RESULTS_FIELD = "results"
TOOL_CALL_FIELD = "tool_call"
RESULT_FIELD = "result"
USAGE_FIELD = "usage"
COST_FIELD = "cost"
PROMPT_COST_FIELD = "prompt_cost"
COMPLETION_COST_FIELD = "completion_cost"
MODEL_FIELD = "model"
FINISH_REASON_FIELD = "finish_reason"
AWAITING_APPROVAL_FIELD = "awaiting_approval"
APPROVAL_COUNT_FIELD = "approval_count"
REASONING_CONTENT_FIELD = "reasoning_content"
IMAGES_FIELD = "images"
ERROR_FIELD = "error"
ID_FIELD = "id"
TYPE_FIELD = "type"
FUNCTION_FIELD = "function"

PROMPT_TOKENS = "prompt_tokens"
COMPLETION_TOKENS = "completion_tokens"
TOTAL_TOKENS = "total_tokens"

_WIRE_TOOL_CALL_ORDER = (ID_FIELD, TYPE_FIELD, FUNCTION_FIELD)

COST_QUANTUM = Decimal("0.00000001")
"""The precision -- 8 decimal places -- a generation's cost is quantized to."""


def _quantized(value: float) -> float:
    """`value`, rounded to `COST_QUANTUM`'s 8 decimal places, as a `float`.

    Routed through `Decimal(str(value))` rather than `Decimal(value)`:
    the latter reproduces the binary float's exact (and often
    long-tailed) value before rounding it, while the former rounds the
    same decimal digits `repr(value)` would show.
    """

    return float(Decimal(str(value)).quantize(COST_QUANTUM))


class V1Wire:
    """Turns one turn's typed events into the V1 endpoint's SSE frames.

    One instance renders one turn: it carries that turn's running
    accounting and the reasoning and images accumulated for its `done`
    event, so it cannot be shared between requests.
    """

    def __init__(self, accounting: TurnAccounting) -> None:
        self._accounting = accounting
        self._reasoning: List[str] = []
        self._images: List[Any] = []

    async def frames(self, events: AsyncIterator[StreamEvent]) -> AsyncIterator[str]:
        """The frames a client reads for `events`, in order."""

        async for event in events:
            for frame in self._render(event):
                yield frame

    # --- Frame assembly ------------------------------------------------

    def _render(self, event: StreamEvent) -> List[str]:
        if isinstance(event, GenerationIdEvent):
            self._accounting.record_generation_id(event.generation_id)
            return [sse.render_event(event)]
        if isinstance(event, ContentEvent):
            return [sse.render_event(event)]
        if isinstance(event, ReasoningEvent):
            self._reasoning.append(event.content)
            return []
        if isinstance(event, ImageEvent):
            self._images.append(event.image)
            return []
        if isinstance(event, UsageUpdateEvent):
            self._record(event)
            return []
        if isinstance(event, FileToolExecutedEvent):
            return [self._executed_frame(event)]
        if isinstance(event, ToolCallRequestEvent):
            return [sse.render_event(event)]
        if isinstance(event, DoneEvent):
            return [self._done_frame(event)]
        if isinstance(event, ErrorEvent):
            return [error_frame(event)]
        return []

    def _record(self, event: UsageUpdateEvent) -> None:
        self._accounting.record_generation_cost(
            usage=event.usage,
            cost=_quantized(event.cost),
            prompt_cost=_quantized(event.prompt_cost),
            completion_cost=_quantized(event.completion_cost),
        )

    def _executed_frame(self, event: FileToolExecutedEvent) -> str:
        self._accounting.record_tool_results(event.results)
        return sse.render_frame(
            str(EventType.FILE_TOOL_EXECUTED),
            {
                TOOL_CALLS_FIELD: [
                    _wire_shaped_call(sse.tool_call_payload(call))
                    for call in event.tool_calls
                ],
                RESULTS_FIELD: [_tool_role_message(entry) for entry in event.results],
            },
        )

    def _done_frame(self, event: DoneEvent) -> str:
        return sse.render_frame(str(EventType.DONE), self._done_payload(event))

    def _done_payload(self, event: DoneEvent) -> JsonDict:
        """What a V1 client reads off the terminal event.

        The generation costs are the turn's own: what the tools spent
        is billed separately and never folded into the figure a V1
        client is shown.
        """

        accounting = self._accounting
        payload: JsonDict = {
            MODEL_FIELD: event.model,
            FINISH_REASON_FIELD: str(event.finish_reason),
            USAGE_FIELD: {
                PROMPT_TOKENS: accounting.prompt_tokens,
                COMPLETION_TOKENS: accounting.completion_tokens,
                TOTAL_TOKENS: accounting.total_tokens,
            },
            COST_FIELD: accounting.cost,
            PROMPT_COST_FIELD: accounting.prompt_cost,
            COMPLETION_COST_FIELD: accounting.completion_cost,
        }
        if event.tool_calls is not None:
            payload[TOOL_CALLS_FIELD] = [
                _wire_shaped_call(sse.tool_call_payload(call))
                for call in event.tool_calls
            ]
        if event.awaiting_approval is not None:
            payload[AWAITING_APPROVAL_FIELD] = event.awaiting_approval
        if event.approval_count is not None:
            payload[APPROVAL_COUNT_FIELD] = event.approval_count
        if self._reasoning:
            payload[REASONING_CONTENT_FIELD] = "".join(self._reasoning)
        if self._images:
            payload[IMAGES_FIELD] = list(self._images)
        return payload


def error_frame(event: ErrorEvent) -> str:
    """The frame a mid-stream failure reaches a V1 client as."""

    return sse.render_frame(str(EventType.ERROR), {ERROR_FIELD: event.error})


def _tool_role_message(entry: Mapping[str, Any]) -> JsonDict:
    """One result entry, as the tool-role message V1 puts on the wire.

    The content is serialized the way the tool's own executor
    serializes it, so a non-ASCII result reaches a client as the
    characters themselves rather than as escapes.
    """

    call = entry[TOOL_CALL_FIELD]
    return {
        ROLE_FIELD: TOOL_ROLE,
        TOOL_CALL_ID_FIELD: call[ID_FIELD],
        NAME_FIELD: call[FUNCTION_FIELD][NAME_FIELD],
        CONTENT_FIELD: json.dumps(entry[RESULT_FIELD], ensure_ascii=False),
    }


def _wire_shaped_call(payload: JsonDict) -> JsonDict:
    """One announced call, carrying the wire shape alone.

    V1 streams a call as the provider spelled it: the three display
    fields a catalog lookup would add are left out.
    """

    return {name: payload[name] for name in _WIRE_TOOL_CALL_ORDER if name in payload}
