"""Where the turn goes after each node.

Three decisions shape a turn, and all of them are made here so the
loop's control flow can be read in one place:

* after a generation — end on failure, close out a plain answer, stop
  at the iteration cap, pause for approval, or run the tools;
* after the approval pause — always run the tools, since a declined
  call still owes the model a result it can react to;
* after the tools — back to the model for the next round.

A turn ended by a provider failure routes straight to the end: the
`error` event already emitted is terminal, and no `done` follows it.
"""

from __future__ import annotations

from enum import StrEnum

from langgraph.graph import END

from .approval_nodes import gated_calls
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
    if gated_calls(pending, deps):
        return Node.APPROVAL_REQUEST
    return Node.TOOLS
