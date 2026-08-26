"""Renders a turn's typed events as the frames the V2 chat endpoint speaks.

`llm.agent_core` emits typed events and knows nothing about any
endpoint's format. The V2 stream-completion endpoint speaks a format
its clients parse as it stands, and that format differs from a plain
rendering of those events in six ways:

* every `usage_update` and the `done` event report the running totals
  of the whole turn, not the figures of the generation that just ended,
* `done` carries a `tool_cost` field alongside the generation costs,
* an announced or reported call carries the catalog's `display_name`,
  while the call embedded in a result entry carries the wire shape
  alone -- its three display fields omitted rather than sent as null,
* a stand-in call is announced once per turn, while the first real one
  is still streaming in, whenever the turn has file tools enabled,
* each call in a round is announced with one keep-alive before any of
  them is waited on, so a tool that returns immediately still produces
  one,
* a mid-stream failure is labelled generically, with the provider's own
  message left in `detail`.

Holding those here keeps them out of the loop and off the wire's
clients: the loop stays a pure state machine and the frontend keeps
reading the frames it already reads.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Mapping, Optional, Sequence

from ..agent_core import sse
from ..agent_core.events import (
    DoneEvent,
    ErrorEvent,
    EventType,
    FileToolExecutedEvent,
    FileToolExecutingEvent,
    GenerationIdEvent,
    JsonDict,
    StreamEvent,
    ToolCall,
    UsageUpdateEvent,
)
from .accounting import TurnAccounting

STREAM_ERROR_LABEL = "Stream error"
"""The label every mid-stream failure reaches a V2 client under."""

FIRST_KEEPALIVE_ELAPSED_SECONDS = 0
"""The reading on the keep-alive sent before a call is first waited on."""

PLACEHOLDER_TOOL_CALL: JsonDict = {
    "function": {"name": "...", "arguments": "{}"},
    "id": "loading",
    "type": "function",
}
"""The stand-in call announced while the first real one streams in."""

TOOL_CALLS_FIELD = "tool_calls"
RESULTS_FIELD = "results"
TOOL_CALL_FIELD = "tool_call"
USAGE_FIELD = "usage"
COST_FIELD = "cost"
PROMPT_COST_FIELD = "prompt_cost"
COMPLETION_COST_FIELD = "completion_cost"
TOOL_COST_FIELD = "tool_cost"
GENERATION_ID_FIELD = "generation_id"
GENERATION_IDS_FIELD = "generation_ids"
ERROR_FIELD = "error"
DISPLAY_NAME_FIELD = "display_name"
SERVER_ICON_URL_FIELD = "server_icon_url"
SERVER_ICON_INVERT_FIELD = "server_icon_invert"
ICON_URL_KEY = "url"
ICON_INVERT_KEY = "invert"
TOOL_FIELD = "tool"
ELAPSED_SECONDS_FIELD = "elapsed_seconds"

_WIRE_TOOL_CALL_ORDER = ("id", "type", "function")


class V2Wire:
    """Turns one turn's typed events into the V2 endpoint's SSE frames.

    One instance renders one turn: it carries that turn's running
    accounting and the once-per-turn stand-in announcement, so it
    cannot be shared between requests.
    """

    def __init__(
        self,
        accounting: TurnAccounting,
        *,
        display_names: Mapping[str, str],
        file_tools_enabled: bool,
        server_icons: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> None:
        self._accounting = accounting
        self._display_names = dict(display_names)
        self._server_icons = dict(server_icons or {})
        self._file_tools_enabled = file_tools_enabled
        self._placeholder_announced = False

    async def frames(self, events: AsyncIterator[StreamEvent]) -> AsyncIterator[str]:
        """The frames a client reads for `events`, in order.

        One `usage_update` is held back at a time: the stand-in
        announcement belongs in front of the `usage_update` that closes
        the generation whose calls it stands in for, and whether such
        calls exist is only known from the event that follows.
        """

        held: Optional[str] = None
        async for event in events:
            if isinstance(event, UsageUpdateEvent):
                for frame in self._flush(held):
                    yield frame
                held = self._usage_update_frame(event)
                continue

            for frame in self._preamble(event, held is not None):
                yield frame
            for frame in self._flush(held):
                yield frame
            held = None
            for frame in self._render(event):
                yield frame

        for frame in self._flush(held):
            yield frame

    # --- Frame assembly ------------------------------------------------

    def _flush(self, held: Optional[str]) -> List[str]:
        return [held] if held is not None else []

    def _preamble(self, event: StreamEvent, holding: bool) -> List[str]:
        """The stand-in announcement, when this event is what calls for it."""

        if not holding or self._placeholder_announced:
            return []
        if not self._file_tools_enabled or not isinstance(event, FileToolExecutingEvent):
            return []
        self._placeholder_announced = True
        return [
            sse.render_frame(
                str(EventType.FILE_TOOL_EXECUTING),
                {TOOL_CALLS_FIELD: [dict(PLACEHOLDER_TOOL_CALL)]},
            )
        ]

    def _render(self, event: StreamEvent) -> List[str]:
        if isinstance(event, GenerationIdEvent):
            self._accounting.record_generation_id(event.generation_id)
            return [sse.render_event(event)]
        if isinstance(event, FileToolExecutingEvent):
            return [self._announced_frame(event)] + self._first_keepalives(
                event.tool_calls
            )
        if isinstance(event, FileToolExecutedEvent):
            return [self._executed_frame(event)]
        if isinstance(event, DoneEvent):
            return [self._done_frame(event)]
        if isinstance(event, ErrorEvent):
            return [self._error_frame(event)]
        return [sse.render_event(event)]

    def _usage_update_frame(self, event: UsageUpdateEvent) -> str:
        self._accounting.record_generation_cost(
            usage=event.usage,
            cost=event.cost,
            prompt_cost=event.prompt_cost,
            completion_cost=event.completion_cost,
        )
        payload = sse.event_payload(event)
        payload.update(self._totals())
        return sse.render_frame(str(EventType.USAGE_UPDATE), payload)

    def _announced_frame(self, event: FileToolExecutingEvent) -> str:
        return sse.render_frame(
            str(EventType.FILE_TOOL_EXECUTING),
            {TOOL_CALLS_FIELD: self._named_calls(event.tool_calls)},
        )

    def _executed_frame(self, event: FileToolExecutedEvent) -> str:
        self._accounting.record_tool_results(event.results)
        return sse.render_frame(
            str(EventType.FILE_TOOL_EXECUTED),
            {
                TOOL_CALLS_FIELD: self._named_calls(event.tool_calls),
                RESULTS_FIELD: [_wire_shaped_result(result) for result in event.results],
            },
        )

    def _first_keepalives(self, calls: Sequence[ToolCall]) -> List[str]:
        return [
            sse.render_frame(
                str(EventType.HEARTBEAT),
                {
                    TOOL_FIELD: call.function.name,
                    ELAPSED_SECONDS_FIELD: FIRST_KEEPALIVE_ELAPSED_SECONDS,
                },
            )
            for call in calls
        ]

    def _done_frame(self, event: DoneEvent) -> str:
        payload = sse.event_payload(event)
        payload.update(self._totals())
        return sse.render_frame(
            str(EventType.DONE), _with_tool_cost(payload, self._accounting.tool_cost)
        )

    def _error_frame(self, event: ErrorEvent) -> str:
        return error_frame(event)

    # --- Shared figures ---------------------------------------------------

    def _totals(self) -> JsonDict:
        """The turn-wide figures that replace a generation's own."""

        accounting = self._accounting
        return {
            USAGE_FIELD: {
                "prompt_tokens": accounting.prompt_tokens,
                "completion_tokens": accounting.completion_tokens,
                "total_tokens": accounting.total_tokens,
            },
            COST_FIELD: accounting.reported_cost,
            PROMPT_COST_FIELD: accounting.prompt_cost,
            COMPLETION_COST_FIELD: accounting.completion_cost,
        }

    def _named_calls(self, calls: Sequence[ToolCall]) -> List[JsonDict]:
        return [self._named_call(call) for call in calls]

    def _named_call(self, call: ToolCall) -> JsonDict:
        name = call.function.name
        payload = sse.tool_call_payload(call)
        payload[DISPLAY_NAME_FIELD] = self._display_names.get(name, name)
        icon = self._server_icons.get(name)
        if icon:
            payload[SERVER_ICON_URL_FIELD] = icon.get(ICON_URL_KEY)
            payload[SERVER_ICON_INVERT_FIELD] = bool(icon.get(ICON_INVERT_KEY, False))
        return payload


def error_frame(event: ErrorEvent) -> str:
    """The frame a mid-stream failure reaches a V2 client as."""

    payload = sse.event_payload(event)
    payload[ERROR_FIELD] = STREAM_ERROR_LABEL
    return sse.render_frame(str(EventType.ERROR), payload)


def _wire_shaped_result(result: Mapping[str, object]) -> JsonDict:
    """One result entry whose embedded call carries the wire shape alone."""

    entry: Dict[str, object] = dict(result)
    call = entry.get(TOOL_CALL_FIELD)
    if isinstance(call, Mapping):
        entry[TOOL_CALL_FIELD] = _reordered(
            {name: value for name, value in call.items() if value is not None},
            _WIRE_TOOL_CALL_ORDER,
        )
    return entry


def _reordered(payload: JsonDict, order: Sequence[str]) -> JsonDict:
    rebuilt = {name: payload[name] for name in order if name in payload}
    rebuilt.update(
        {name: value for name, value in payload.items() if name not in rebuilt}
    )
    return rebuilt


def _with_tool_cost(payload: JsonDict, tool_cost: float) -> JsonDict:
    """`payload` with `tool_cost` placed where a V2 client reads it."""

    rebuilt: JsonDict = {}
    for name, value in payload.items():
        rebuilt[name] = value
        if name == COMPLETION_COST_FIELD:
            rebuilt[TOOL_COST_FIELD] = tool_cost
    if TOOL_COST_FIELD not in rebuilt:
        rebuilt[TOOL_COST_FIELD] = tool_cost
    return rebuilt
