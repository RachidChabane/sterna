"""How a node puts a typed event on the caller's stream.

LangGraph's custom stream mode carries whatever a node writes through
to the consumer unchanged and in real time, so a node emits an
`events.StreamEvent` instance directly rather than a serialized form.
`EventStream` wraps that writer so a node never touches LangGraph's
streaming API itself, and so a test can collect what a node emitted by
handing it a list.

`Heartbeat` and `ProgressPump` cover the one case where events must
keep flowing while a node is blocked: a long-running tool call. Each
owns a background task that emits at a fixed interval -- a keep-alive
for the one, whatever the call's progress channel reports for the
other -- and each holds the writer it was given rather than looking
one up, so both work regardless of how the task's context was copied.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import TracebackType
from typing import Callable, List, Optional, Sequence, Type

from ..events import HeartbeatEvent, StreamEvent
from .ports import ToolProgressWatch

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

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


class _IntervalPump:
    """A background task that emits on a fixed interval while a call runs.

    Used as an async context manager around the awaited call, and
    stopped whether that call finished or raised. An
    `interval_seconds` of `None` makes it inert, which is how a caller
    with its own channel — and every test — disables it.

    A tick that raises is logged and the pump carries on: a channel
    that only reports on a call must never be what ends it.
    """

    def __init__(self, *, interval_seconds: Optional[float]) -> None:
        self._interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task[None]] = None

    async def __aenter__(self) -> "_IntervalPump":
        interval_seconds = self._interval_seconds
        if interval_seconds is not None and interval_seconds > 0:
            self._task = asyncio.create_task(self._pump(interval_seconds))
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
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await self._tick()
            except Exception:
                logger.warning(
                    "agent_core.pump_tick_failed",
                    extra={"pump": type(self).__name__},
                    exc_info=True,
                )

    async def _tick(self) -> None:
        raise NotImplementedError


class Heartbeat(_IntervalPump):
    """Emits keep-alives for a named tool call until the call finishes."""

    def __init__(
        self,
        stream: EventStream,
        *,
        tool: str,
        interval_seconds: Optional[float],
    ) -> None:
        super().__init__(interval_seconds=interval_seconds)
        self._stream = stream
        self._tool = tool
        self._started_at = time.monotonic()

    async def _tick(self) -> None:
        elapsed = int(time.monotonic() - self._started_at)
        self._stream.emit(HeartbeatEvent(tool=self._tool, elapsed_seconds=elapsed))


class ProgressPump(_IntervalPump):
    """Emits what a watched tool call reports until the call finishes.

    A `watch` of `None` makes it inert, which is the answer a progress
    port gives for every call it has no reporting for.
    """

    def __init__(
        self,
        stream: EventStream,
        *,
        watch: Optional[ToolProgressWatch],
        interval_seconds: Optional[float],
    ) -> None:
        super().__init__(interval_seconds=interval_seconds if watch else None)
        self._stream = stream
        self._watch = watch

    async def _tick(self) -> None:
        if self._watch is None:
            return
        self._stream.emit_all(await self._watch.poll())
