"""How a node puts a typed event on the caller's stream.

LangGraph's custom stream mode carries whatever a node writes through
to the consumer unchanged and in real time, so a node emits an
`events.StreamEvent` instance directly rather than a serialized form.
`EventStream` wraps that writer so a node never touches LangGraph's
streaming API itself, and so a test can collect what a node emitted by
handing it a list.

`Heartbeat` covers the one case where events must keep flowing while a
node is blocked: a long-running tool call. It owns a background task
that emits a keep-alive at a fixed interval, and it holds the writer it
was given rather than looking one up, so it works regardless of how the
task's context was copied.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Callable, List, Optional, Sequence, Type

from ..events import HeartbeatEvent, StreamEvent

EventSink = Callable[[StreamEvent], None]
"""Accepts one event and forwards it to whoever is consuming the turn."""


class EventStream:
    """The channel a node emits typed events on."""

    def __init__(self, sink: EventSink) -> None:
        self._sink = sink

    def emit(self, event: StreamEvent) -> None:
        self._sink(event)

    def emit_all(self, events: Sequence[StreamEvent]) -> None:
        for event in events:
            self._sink(event)

    @classmethod
    def collecting(cls, into: List[StreamEvent]) -> "EventStream":
        """A stream that appends every event to `into` instead of forwarding it."""

        return cls(into.append)


class Heartbeat:
    """Emits keep-alives for a named tool call until the call finishes.

    Used as an async context manager around the awaited call. An
    `interval_seconds` of `None` makes it inert, which is how a caller
    with its own keep-alive channel — and every test — disables it.
    """

    def __init__(
        self,
        stream: EventStream,
        *,
        tool: str,
        interval_seconds: Optional[float],
    ) -> None:
        self._stream = stream
        self._tool = tool
        self._interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task[None]] = None

    async def __aenter__(self) -> "Heartbeat":
        if self._interval_seconds is not None and self._interval_seconds > 0:
            self._task = asyncio.create_task(self._pump(self._interval_seconds))
        return self

    async def __aexit__(
        self,
        _exception_type: Optional[Type[BaseException]],
        _exception: Optional[BaseException],
        _traceback: Optional[TracebackType],
    ) -> None:
        """Stop the pump, whether the call finished or raised."""

        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _pump(self, interval_seconds: float) -> None:
        started_at = time.monotonic()
        while True:
            await asyncio.sleep(interval_seconds)
            elapsed = int(time.monotonic() - started_at)
            self._stream.emit(HeartbeatEvent(tool=self._tool, elapsed_seconds=elapsed))
