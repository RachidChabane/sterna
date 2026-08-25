"""Reassembles streamed tool-call deltas into complete `events.ToolCall`s.

A provider streams one tool call across several
`provider.ProviderToolCallDeltaChunk` fragments sharing the same
`index`: an id and function name first, then successive
`arguments_delta` fragments to concatenate into the final JSON
arguments string. Some providers additionally emit a placeholder
`"{}"` fragment before the real arguments start — that placeholder
must be discarded rather than concatenated, or the accumulated string
stops being valid JSON.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .events import ToolCall, ToolCallFunction
from .provider import ProviderToolCallDeltaChunk

_EMPTY_ARGUMENTS_PLACEHOLDER = "{}"


class _PendingToolCall:
    __slots__ = ("id", "name", "arguments")

    def __init__(self) -> None:
        self.id: Optional[str] = None
        self.name: Optional[str] = None
        self.arguments: str = ""


class ToolCallAccumulator:
    """Absorbs `ProviderToolCallDeltaChunk`s and yields the completed tool calls."""

    def __init__(self) -> None:
        self._by_index: Dict[int, _PendingToolCall] = {}
        self._order: List[int] = []

    def absorb(self, delta: ProviderToolCallDeltaChunk) -> None:
        """Merge one tool-call fragment into the call at its index."""
        pending = self._by_index.get(delta.index)
        if pending is None:
            pending = _PendingToolCall()
            self._by_index[delta.index] = pending
            self._order.append(delta.index)

        if delta.id is not None:
            pending.id = delta.id
        if delta.name is not None:
            pending.name = delta.name
        if delta.arguments_delta is not None:
            pending.arguments = self._merge_arguments(pending.arguments, delta.arguments_delta)

    @staticmethod
    def _merge_arguments(current: str, incoming: str) -> str:
        if current in ("", _EMPTY_ARGUMENTS_PLACEHOLDER):
            return incoming
        if incoming == _EMPTY_ARGUMENTS_PLACEHOLDER:
            return current
        return current + incoming

    def tool_calls(self) -> List[ToolCall]:
        """The tool calls accumulated so far, in first-seen index order."""
        return [
            ToolCall(
                id=pending.id or "",
                function=ToolCallFunction(name=pending.name or "", arguments=pending.arguments),
            )
            for pending in (self._by_index[index] for index in self._order)
        ]

    def __bool__(self) -> bool:
        return bool(self._order)
