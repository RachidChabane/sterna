"""The node that closes a turn with its `done` event.

Reached whenever the turn ends normally: the model answered without
calling tools, or the loop stopped because it had taken as many model
calls as it is allowed. A turn ended by a provider failure never
arrives here — an `error` event is terminal on its own.

A provider's `finish_reason` vocabulary is wider than the one the
stream speaks, so it is mapped rather than passed through. When the
loop stops with calls still pending, the reason reported is
`tool_calls` and the unanswered calls ride along on the event, which
is how a caller tells that outcome apart from a completed answer.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from ..events import DoneEvent, FinishReason
from .dependencies import GraphDependencies
from .emission import EventStream
from .state import AgentTurnState

_PROVIDER_FINISH_REASONS: Mapping[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "function_call": FinishReason.TOOL_CALLS,
    "length": FinishReason.STOP,
    "content_filter": FinishReason.STOP,
}


def finish_reason_for(state: AgentTurnState) -> FinishReason:
    """How the turn ended, in the vocabulary the stream speaks."""

    if state["pending_tool_calls"]:
        return FinishReason.TOOL_CALLS
    raw = state["finish_reason"]
    if raw is None:
        return FinishReason.STOP
    return _PROVIDER_FINISH_REASONS.get(raw, FinishReason.STOP)


async def finalize_node(
    state: AgentTurnState, deps: GraphDependencies, stream: EventStream
) -> Dict[str, Any]:
    """Emit the turn's `done` event."""

    accounting = state["accounting"]
    pending = state["pending_tool_calls"]
    generation_ids = state["generation_ids"]
    stream.emit(
        DoneEvent(
            model=deps.config.model,
            finish_reason=finish_reason_for(state),
            usage=accounting.usage,
            cost=accounting.cost,
            prompt_cost=accounting.prompt_cost,
            completion_cost=accounting.completion_cost,
            tool_calls=list(pending) or None,
            generation_id=generation_ids[-1] if generation_ids else None,
            generation_ids=list(generation_ids) or None,
        )
    )
    return {}
