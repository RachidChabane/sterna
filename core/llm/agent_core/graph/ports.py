"""The ports a caller supplies to run a turn, beyond the model and the tools.

The loop reaches the model through `provider.ModelProvider` and the
tools through `registry.ToolRegistry`. The remaining concerns belong
to whoever owns persistence, billing, the conversation's history, and
the meaning of a given tool's payloads; they are injected here rather
than implemented inside this package:

* relieving context-window pressure (trimming or summarizing history),
* minting the approval records a gated tool call waits on,
* splitting a provider's reported cost into its prompt/completion parts,
* deriving the extra events a tool's own result implies,
* reporting what a long-running tool call is doing while it runs.

Each port ships with a default implementation that does the inert
thing, so a caller with no such concern supplies nothing.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
from enum import StrEnum
from typing import List, Optional, Protocol, Sequence, Tuple

from ..events import Approval, JsonDict, StreamEvent, ToolCall, Usage
from ..provider import ProviderMessage
from ..registry import ToolDefinition

# --- Context-window pressure ------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ContextRelief:
    """The message history to send, plus the events explaining any change.

    `events` is empty when nothing was dropped or summarized; it
    carries a `ContextTrimmedEvent` or a `ContextCompactedEvent` when
    the history was reshaped, so the caller learns about it on the
    same stream as everything else.
    """

    messages: List[ProviderMessage]
    events: Tuple[StreamEvent, ...] = ()


class ContextWindowPort(Protocol):
    """Reshapes a conversation that no longer fits the model's context window."""

    async def relieve(self, messages: Sequence[ProviderMessage], *, model: str) -> ContextRelief:
        ...


class UnboundedContextWindow:
    """A context-window port that never reshapes the history."""

    async def relieve(self, messages: Sequence[ProviderMessage], *, model: str) -> ContextRelief:
        return ContextRelief(messages=list(messages))


# --- Tool approval ------------------------------------------------------


class ApprovalDecision(StrEnum):
    """The answer a user gives for one gated tool call."""

    APPROVED = "approved"
    DENIED = "denied"


@dataclasses.dataclass(frozen=True, slots=True)
class ToolApprovalDecision:
    """One user answer, addressed to the tool call it decides."""

    tool_call_id: str
    decision: ApprovalDecision
    reason: Optional[str] = None

    @property
    def approved(self) -> bool:
        return self.decision is ApprovalDecision.APPROVED


PENDING_APPROVAL_STATUS = "pending"
"""The `status` an `Approval` carries while it waits for an answer."""


class ApprovalPort(Protocol):
    """Turns gated tool calls into the approval records a user acts on.

    The records carry identifiers minted by whoever stores them, so
    they cannot be produced inside this package. The loop opens
    approvals exactly once per gated call, before it pauses.
    """

    async def open(
        self, requests: Sequence[Tuple[ToolCall, ToolDefinition]]
    ) -> List[Approval]:
        ...


class LocalApprovals:
    """An approval port that mints its own identifiers, for a caller with no store.

    Sufficient for a turn whose pause and resume happen in one
    process; a caller that must survive a restart supplies a port
    backed by durable records instead.
    """

    def __init__(self, prefix: str = "approval") -> None:
        self._prefix = prefix
        self._counter = itertools.count(1)

    async def open(
        self, requests: Sequence[Tuple[ToolCall, ToolDefinition]]
    ) -> List[Approval]:
        return [
            Approval(
                id=f"{self._prefix}-{next(self._counter)}",
                tool_id=definition.id,
                tool_name=definition.display.name,
                tool_description=definition.description,
                server_name=definition.display.server_name or "",
                arguments=_decoded_arguments(call),
                status=PENDING_APPROVAL_STATUS,
            )
            for call, definition in requests
        ]


def _decoded_arguments(call: ToolCall) -> JsonDict:
    try:
        decoded = json.loads(call.function.arguments or "{}")
    except ValueError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


# --- Cost accounting ----------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class CostBreakdown:
    """What one generation cost, split the way a billing report needs it."""

    total: float
    prompt: float
    completion: float


class CostAccountantPort(Protocol):
    """Splits a generation's cost into its prompt and completion parts."""

    def account(self, *, model: str, usage: Usage, reported_cost: Optional[float]) -> CostBreakdown:
        ...


class ProviderReportedCost:
    """A cost accountant that reports the provider's total and no split.

    A provider that returns a single figure gives no basis for
    apportioning it; a caller holding a price table supplies a port
    that does.
    """

    def account(self, *, model: str, usage: Usage, reported_cost: Optional[float]) -> CostBreakdown:
        total = reported_cost or 0.0
        return CostBreakdown(total=total, prompt=0.0, completion=0.0)


# --- Tool-result derived events -----------------------------------------


class ToolResultEventsPort(Protocol):
    """Derives extra stream events from what a tool call returned.

    A tool that starts a live preview or returns citations implies an
    event the loop itself cannot recognize, because the meaning lives
    in the tool's own result shape.
    """

    def derive(self, call: ToolCall, result: JsonDict) -> Sequence[StreamEvent]:
        ...


class NoDerivedToolEvents:
    """A derivation port that reads nothing out of a tool result."""

    def derive(self, call: ToolCall, result: JsonDict) -> Sequence[StreamEvent]:
        return ()


# --- Long-running tool progress -----------------------------------------


class ToolProgressWatch(Protocol):
    """What one long-running call is doing, while it is still running.

    `poll` is asked at the turn's keep-alive interval for as long as
    the call is in flight, and answers with the events that describe
    whatever happened since the last time it was asked. `close` is
    asked once, with what the call returned, and answers with the
    events that state what the run amounted to.

    Neither method may raise: a call must not fail because the channel
    reporting on it did.
    """

    async def poll(self) -> Sequence[StreamEvent]:
        ...

    async def close(self, result: JsonDict) -> Sequence[StreamEvent]:
        ...


class ToolProgressPort(Protocol):
    """Opens a progress channel for the tool calls that have one.

    Whether a call reports progress is a property of the tool, not of
    the loop -- only a handler that drives something long-running
    elsewhere has anything to report. A call the port knows nothing
    about is answered with `None`, and the loop runs it with no
    progress channel at all.
    """

    def watch(self, call: ToolCall) -> Optional[ToolProgressWatch]:
        ...


class NoToolProgress:
    """A progress port that watches nothing."""

    def watch(self, call: ToolCall) -> Optional[ToolProgressWatch]:
        return None
