"""Everything a node needs that is not part of the turn's state.

Nodes are plain async functions that take the state; the model
backend, the tool catalog, the turn's configuration, and the caller's
ports reach them through one immutable container bound at build time.
Keeping them here rather than in the state keeps non-serializable
collaborators out of the checkpointer's way, and keeps every node
testable by constructing this object directly.
"""

from __future__ import annotations

import dataclasses

from ..provider import ModelProvider
from ..registry import ToolExecutionContext, ToolRegistry
from .policies import AgentTurnConfig
from .ports import (
    ApprovalPort,
    ContextWindowPort,
    CostAccountantPort,
    LocalApprovals,
    NoDerivedToolEvents,
    ProviderReportedCost,
    ToolResultEventsPort,
    UnboundedContextWindow,
)


@dataclasses.dataclass(frozen=True, slots=True)
class GraphDependencies:
    """The collaborators one compiled graph runs against."""

    provider: ModelProvider
    registry: ToolRegistry
    config: AgentTurnConfig
    tool_context: ToolExecutionContext
    approvals: ApprovalPort = dataclasses.field(default_factory=LocalApprovals)
    context_window: ContextWindowPort = dataclasses.field(default_factory=UnboundedContextWindow)
    cost_accountant: CostAccountantPort = dataclasses.field(default_factory=ProviderReportedCost)
    tool_result_events: ToolResultEventsPort = dataclasses.field(
        default_factory=NoDerivedToolEvents
    )
