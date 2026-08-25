"""What one turn carries between nodes as it runs.

`AgentTurnState` is the graph's channel schema. Every key uses
replacement semantics rather than an accumulating reducer: the model
node returns the whole message list it wants the next round to see,
which is what lets a context-window port shorten or summarize the
history instead of only appending to it.
"""

from __future__ import annotations

import dataclasses
from typing import List, Optional, TypedDict

from ..events import Approval, ErrorEvent, ToolCall, Usage
from ..provider import ProviderMessage
from .ports import ToolApprovalDecision

EMPTY_USAGE = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
"""The usage a turn reports when it never reached the model."""


@dataclasses.dataclass(frozen=True, slots=True)
class GenerationAccounting:
    """Token and cost figures for the most recent generation of a turn.

    A turn that calls tools spans several generations; a `done` event
    reports the last one's figures alongside the ids of all of them,
    which is what both legacy streaming paths put on the wire.
    """

    usage: Usage = EMPTY_USAGE
    cost: float = 0.0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0


@dataclasses.dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """The gated tool calls of one round, paired with their records."""

    approvals: List[Approval]
    tool_calls: List[ToolCall]


class AgentTurnState(TypedDict):
    """The channels one agent turn reads and writes.

    `pending_tool_calls` holds what the last generation asked for and
    the tool node has not yet answered. `decisions` holds the answers
    a resumed turn came back with, keyed by tool-call id inside each
    entry. `error` is set only by a failure that ends the turn, and
    its presence routes straight to the end without a `done` event.
    """

    messages: List[ProviderMessage]
    iteration: int
    pending_tool_calls: List[ToolCall]
    approval_request: Optional[ApprovalRequest]
    decisions: List[ToolApprovalDecision]
    generation_ids: List[str]
    accounting: GenerationAccounting
    finish_reason: Optional[str]
    error: Optional[ErrorEvent]


def initial_state(messages: List[ProviderMessage]) -> AgentTurnState:
    """The state a fresh turn starts from."""

    return AgentTurnState(
        messages=list(messages),
        iteration=0,
        pending_tool_calls=[],
        approval_request=None,
        decisions=[],
        generation_ids=[],
        accounting=GenerationAccounting(),
        finish_reason=None,
        error=None,
    )
