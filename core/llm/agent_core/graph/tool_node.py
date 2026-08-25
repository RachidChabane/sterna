"""The node that answers the pending tool calls and feeds the results back.

Calls that may run now do so concurrently, each under its own
keep-alive, and each produces one tool-role message appended to the
conversation so the next generation can read it. A call still waiting
on the user's sign-off stays pending and is left for the round after
the pause. Three outcomes are answered the same way
— as a result the model can reason about rather than as a failure that
ends the turn: a call naming a tool the registry does not hold, a call
the user denied, and a handler that raised.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from typing import Any, Dict, FrozenSet, Optional, Sequence, Tuple

from ..events import (
    FileToolExecutedEvent,
    FileToolExecutingEvent,
    JsonDict,
    ToolCall,
)
from ..provider import ProviderMessage
from ..registry import ToolDefinition
from .approval_nodes import partition_by_gate
from .dependencies import GraphDependencies
from .emission import EventStream, Heartbeat
from .ports import ToolApprovalDecision
from .state import AgentTurnState

TOOL_ROLE = "tool"
UNKNOWN_TOOL_ERROR = "No tool named {name} is available."
DENIED_ERROR = "The user declined to run this tool."
HANDLER_ERROR = "The tool failed: {reason}"


@dataclasses.dataclass(frozen=True, slots=True)
class ToolOutcome:
    """What one tool call produced, ready for both the stream and the model."""

    call: ToolCall
    result: JsonDict
    success: bool

    def as_message(self) -> ProviderMessage:
        return ProviderMessage(
            role=TOOL_ROLE,
            content=json.dumps(self.result),
            tool_call_id=self.call.id,
            name=self.call.function.name,
        )

    def as_result_entry(self) -> JsonDict:
        return {
            "tool_call": dataclasses.asdict(self.call),
            "result": self.result,
            "success": self.success,
        }


async def tool_node(
    state: AgentTurnState, deps: GraphDependencies, stream: EventStream
) -> Dict[str, Any]:
    """Run every pending call and append one tool-role message per call."""

    decisions = state["decisions"]
    calls, deferred = partition_by_gate(state["pending_tool_calls"], decisions, deps)
    if not calls:
        return {"pending_tool_calls": deferred, "decisions": []}

    stream.emit(FileToolExecutingEvent(tool_calls=list(calls)))
    denied = _denied_call_ids(decisions)
    outcomes = await asyncio.gather(
        *(_run_one(call, call.id in denied, deps, stream) for call in calls)
    )

    stream.emit(
        FileToolExecutedEvent(
            tool_calls=list(calls),
            results=[outcome.as_result_entry() for outcome in outcomes],
        )
    )
    for outcome in outcomes:
        stream.emit_all(deps.tool_result_events.derive(outcome.call, outcome.result))

    return {
        "messages": state["messages"] + [outcome.as_message() for outcome in outcomes],
        "pending_tool_calls": deferred,
        "decisions": [],
    }


def _denied_call_ids(decisions: Sequence[ToolApprovalDecision]) -> FrozenSet[str]:
    return frozenset(
        decision.tool_call_id for decision in decisions if not decision.approved
    )


async def _run_one(
    call: ToolCall, is_denied: bool, deps: GraphDependencies, stream: EventStream
) -> ToolOutcome:
    definition = deps.registry.get(call.function.name)
    if definition is None:
        return _failure(call, UNKNOWN_TOOL_ERROR.format(name=call.function.name))
    if is_denied:
        return _failure(call, DENIED_ERROR)

    arguments, decode_error = _decode_arguments(call)
    if decode_error is not None:
        return _failure(call, decode_error)

    async with Heartbeat(
        stream,
        tool=call.function.name,
        interval_seconds=deps.config.heartbeat_interval_seconds,
    ):
        return await _invoke(call, definition, arguments, deps)


async def _invoke(
    call: ToolCall, definition: ToolDefinition, arguments: JsonDict, deps: GraphDependencies
) -> ToolOutcome:
    try:
        result = await definition.handler(arguments, deps.tool_context)
    except Exception as error:  # a tool's failure is an answer, not the turn's end
        return _failure(call, HANDLER_ERROR.format(reason=error))
    return ToolOutcome(call=call, result=result, success=bool(result.get("success", True)))


def _decode_arguments(call: ToolCall) -> Tuple[JsonDict, Optional[str]]:
    raw = call.function.arguments or "{}"
    try:
        decoded = json.loads(raw)
    except ValueError as error:
        return {}, f"The tool arguments were not valid JSON: {error}"
    if not isinstance(decoded, dict):
        return {}, "The tool arguments must be a JSON object."
    return decoded, None


def _failure(call: ToolCall, error: str) -> ToolOutcome:
    return ToolOutcome(call=call, result={"success": False, "error": error}, success=False)
