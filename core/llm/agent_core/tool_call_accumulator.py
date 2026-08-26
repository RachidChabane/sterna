"""Reassembles streamed tool-call deltas into complete `events.ToolCall`s.

A provider streams one tool call across several
`provider.ProviderToolCallDeltaChunk` fragments sharing the same
`index`: an id and function name first, then successive
`arguments_delta` fragments to concatenate into the final JSON
arguments string. Some providers additionally emit a placeholder
`"{}"` fragment before the real arguments start — that placeholder
must be discarded rather than concatenated, or the accumulated string
stops being valid JSON.

A call that arrives with no id at all is given one here. Everything
downstream addresses a call by its id — the tool-role message that
answers it, the approval record a user acts on, the set of calls a
round is still waiting for — so a call with no id could be answered
but never matched, and two of them could not be told apart.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .events import ToolCall, ToolCallFunction
from .provider import ProviderToolCallDeltaChunk

_EMPTY_ARGUMENTS_PLACEHOLDER = "{}"

SYNTHESIZED_ID_PREFIX = "call_"
SYNTHESIZED_ID_HEX_DIGITS = 16


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
        """The tool calls accumulated so far, in first-seen index order.

        An id minted for a call that arrived without one is kept, so
        asking twice names the same call both times.
        """
        calls = []
        for pending in (self._by_index[index] for index in self._order):
            if not pending.id:
                pending.id = _synthesized_id()
            calls.append(
                ToolCall(
                    id=pending.id,
                    function=ToolCallFunction(
                        name=pending.name or "", arguments=pending.arguments
                    ),
                )
            )
        return calls

    def __bool__(self) -> bool:
        return bool(self._order)


def _synthesized_id() -> str:
    """An id for a call the provider sent without one."""

    return f"{SYNTHESIZED_ID_PREFIX}{uuid.uuid4().hex[:SYNTHESIZED_ID_HEX_DIGITS]}"
