"""The agent loop: a LangGraph state machine over the provider and tool ports.

One turn is a cycle between two nodes. The model node streams a
generation; the tool node answers whatever tool calls that generation
asked for and hands the results back for the next round. Two nodes
sit between them for a tool the user must sign off on, and one closes
the turn with its `done` event.

The loop reaches the outside world only through ports: the model
through `provider.ModelProvider`, the tools through
`registry.ToolRegistry`, and history, approval records, and cost
accounting through the ports in `ports`. Nothing here knows about a
web framework, a database, or a request.
"""

from .builder import build_agent_graph
from .dependencies import GraphDependencies
from .emission import EventStream, Heartbeat, ProgressPump
from .errors import to_error_event
from .policies import AgentTurnConfig, ApprovalPolicy, RetryPolicy
from .ports import (
    ApprovalDecision,
    ApprovalPort,
    ContextRelief,
    ContextWindowPort,
    CostAccountantPort,
    CostBreakdown,
    LocalApprovals,
    NoDerivedToolEvents,
    NoToolProgress,
    ProviderReportedCost,
    ToolApprovalDecision,
    ToolProgressPort,
    ToolProgressWatch,
    ToolResultEventsPort,
    UnboundedContextWindow,
)
from .routing import Node
from .runner import AgentLoop, TurnNotPausedError
from .state import AgentTurnState, ApprovalRequest, GenerationAccounting, initial_state

__all__ = [
    "AgentLoop",
    "AgentTurnConfig",
    "AgentTurnState",
    "ApprovalDecision",
    "ApprovalPolicy",
    "ApprovalPort",
    "ApprovalRequest",
    "ContextRelief",
    "ContextWindowPort",
    "CostAccountantPort",
    "CostBreakdown",
    "EventStream",
    "GenerationAccounting",
    "GraphDependencies",
    "Heartbeat",
    "LocalApprovals",
    "NoDerivedToolEvents",
    "NoToolProgress",
    "Node",
    "ProgressPump",
    "ProviderReportedCost",
    "RetryPolicy",
    "ToolApprovalDecision",
    "ToolProgressPort",
    "ToolProgressWatch",
    "ToolResultEventsPort",
    "TurnNotPausedError",
    "UnboundedContextWindow",
    "build_agent_graph",
    "initial_state",
    "to_error_event",
]
