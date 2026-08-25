"""The pause a gated tool call takes while it waits for the user.

The pause is split across two nodes because LangGraph resumes an
interrupted node by re-executing it from the top. Opening approval
records is a side effect and must happen exactly once, so it lives in
`approval_request_node`, which never interrupts. Waiting is pure — it
reads what the previous node stored and interrupts on it — so
`approval_gate_node` can be replayed on resume with no consequence.

The value carried out through the interrupt is the request itself; the
runner turns it into the `tool_call_request` and `done` events a
caller sees, and the value carried back in is the list of decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from langgraph.types import interrupt

from ..events import ToolCall
from ..registry import ToolApproval, ToolDefinition
from .dependencies import GraphDependencies
from .ports import ApprovalDecision, ToolApprovalDecision
from .state import AgentTurnState, ApprovalRequest


def gated_calls(
    tool_calls: Sequence[ToolCall], deps: GraphDependencies
) -> List[Tuple[ToolCall, ToolDefinition]]:
    """The pending calls whose tool requires the user's sign-off.

    A call naming a tool the registry does not hold is not gated: the
    tool node answers it with an error instead, so the user is never
    asked to approve something that cannot run.
    """

    gated: List[Tuple[ToolCall, ToolDefinition]] = []
    for call in tool_calls:
        definition = deps.registry.get(call.function.name)
        if definition is not None and definition.approval is ToolApproval.REQUIRED:
            gated.append((call, definition))
    return gated


async def approval_request_node(
    state: AgentTurnState, deps: GraphDependencies
) -> Dict[str, Any]:
    """Open one approval record per gated call and store the request."""

    requests = gated_calls(state["pending_tool_calls"], deps)
    approvals = await deps.approvals.open(requests)
    return {
        "approval_request": ApprovalRequest(
            approvals=list(approvals),
            tool_calls=[call for call, _ in requests],
        )
    }


def approval_gate_node(state: AgentTurnState) -> Dict[str, Any]:
    """Pause the turn until the user has answered every gated call.

    Nothing here may have a side effect: a resumed turn runs this
    node again from the top, with `interrupt` returning the answers
    instead of raising.
    """

    request = state["approval_request"]
    if request is None:
        return {"decisions": []}
    answers = interrupt(request)
    return {"approval_request": None, "decisions": _normalized(answers, request)}


def _normalized(answers: Any, request: ApprovalRequest) -> List[ToolApprovalDecision]:
    """The resume value, read as one decision per gated tool call.

    A caller may answer with `ToolApprovalDecision` values, with the
    plain mappings a JSON transport delivers, or with a single boolean
    standing for the whole batch. A gated call left unanswered counts
    as denied, so an incomplete answer can never let a call through.
    """

    if isinstance(answers, bool):
        decision = ApprovalDecision.APPROVED if answers else ApprovalDecision.DENIED
        return [
            ToolApprovalDecision(tool_call_id=call.id, decision=decision)
            for call in request.tool_calls
        ]

    by_call_id = {
        parsed.tool_call_id: parsed
        for parsed in (_as_decision(answer) for answer in _as_sequence(answers))
    }
    return [
        by_call_id.get(
            call.id,
            ToolApprovalDecision(tool_call_id=call.id, decision=ApprovalDecision.DENIED),
        )
        for call in request.tool_calls
    ]


def _as_sequence(answers: Any) -> Sequence[Any]:
    if answers is None:
        return ()
    if isinstance(answers, (list, tuple)):
        return answers
    return (answers,)


def _as_decision(answer: Any) -> ToolApprovalDecision:
    if isinstance(answer, ToolApprovalDecision):
        return answer
    if isinstance(answer, dict):
        return ToolApprovalDecision(
            tool_call_id=str(answer.get("tool_call_id", "")),
            decision=ApprovalDecision(answer.get("decision", ApprovalDecision.DENIED)),
            reason=answer.get("reason"),
        )
    raise TypeError(
        "an approval answer must be a ToolApprovalDecision, a mapping with a "
        f"tool_call_id, or a bool; got {type(answer).__name__}"
    )
