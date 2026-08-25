"""Where the turn goes after each node.

Three decisions shape a turn, and all of them are made here so the
loop's control flow can be read in one place:

* after a generation — end on failure, close out a plain answer, stop
  at the iteration cap, run whatever needs no sign-off, or pause;
* after the approval pause — always run the tools, since a declined
  call still owes the model a result it can react to;
* after the tools — pause if the round still holds a gated call the
  user has not answered, otherwise back to the model.

A round mixing gated and ungated calls therefore runs the ungated ones
before it pauses, and the pause reports the whole round.

A turn ended by a provider failure routes straight to the end: the
`error` event already emitted is terminal, and no `done` follows it.
"""

from __future__ import annotations

from enum import StrEnum

from langgraph.graph import END

from .approval_nodes import partition_by_gate
from .dependencies import GraphDependencies
from .state import AgentTurnState


class Node(StrEnum):
    """The name each node is registered under in the compiled graph."""

    MODEL = "model"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_GATE = "approval_gate"
    TOOLS = "tools"
    FINALIZE = "finalize"


def route_after_model(state: AgentTurnState, deps: GraphDependencies) -> str:
    """The step that follows a generation."""

    if state["error"] is not None:
        return END
    pending = state["pending_tool_calls"]
    if not pending:
        return Node.FINALIZE
    if state["iteration"] >= deps.config.max_iterations:
        return Node.FINALIZE
    runnable, _ = partition_by_gate(pending, state["decisions"], deps)
    return Node.TOOLS if runnable else Node.APPROVAL_REQUEST


def route_after_tools(state: AgentTurnState) -> str:
    """The step that follows a round of tool calls.

    Anything still pending here is a gated call the user has not
    answered, so the turn pauses before asking the model again.
    """

    return Node.APPROVAL_REQUEST if state["pending_tool_calls"] else Node.MODEL
