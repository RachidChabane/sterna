"""Runs a compiled agent graph and yields the turn as a stream of events.

A caller drives a turn through two entry points. `start` runs a fresh
turn from a message history; `resume` continues one that paused for
tool approval, carrying the user's decisions back in. Both identify
the turn by a `thread_id`, which is also the key its checkpoint is
stored under, so the pause can outlive the process that opened it when
the checkpointer is durable.

Nodes emit their events on LangGraph's custom stream; the runner
forwards those unchanged. It synthesizes only what a node cannot: the
pause itself is not a node's output but the graph declining to
continue, so the runner turns it into the `tool_call_request` and
`done` pair that tells a caller the turn is waiting on them.
"""

from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import INTERRUPT
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Interrupt, RunnableConfig, StreamMode

from ..events import (
    DoneEvent,
    FinishReason,
    JsonDict,
    StreamEvent,
    ToolCallRequestEvent,
)
from ..provider import ProviderMessage
from .builder import build_agent_graph
from .dependencies import GraphDependencies
from .ports import ToolApprovalDecision
from .state import AgentTurnState, ApprovalRequest, GenerationAccounting, initial_state

_CUSTOM: StreamMode = "custom"
_UPDATES: StreamMode = "updates"

_STREAM_MODES: List[StreamMode] = [_CUSTOM, _UPDATES]
"""The two channels a turn is read from: what nodes emit, and where the graph went.

Requesting more than one mode requires a `list`: any other sequence is
taken for a single mode, and the turn then streams nothing at all.
Each run is handed a copy, so this shared list cannot be reached by
anything the run does with it.
"""


class TurnNotPausedError(RuntimeError):
    """A turn was resumed on a thread that is not waiting for approval.

    Raised for a thread nothing was ever started on, and for one whose
    turn already finished — a decision arriving twice, or against a
    stale link. Naming the condition keeps a caller from having to
    tell an unknown thread apart from an internal failure.
    """

    def __init__(self, thread_id: str) -> None:
        super().__init__(f"no turn is paused on thread {thread_id!r}")
        self.thread_id = thread_id


class AgentLoop:
    """One configured agent loop, runnable over many turns."""

    def __init__(
        self,
        deps: GraphDependencies,
        *,
        checkpointer: Optional[BaseCheckpointSaver] = None,
    ) -> None:
        self._deps = deps
        self._graph: CompiledStateGraph = build_agent_graph(deps, checkpointer=checkpointer)

    @property
    def graph(self) -> CompiledStateGraph:
        """The compiled graph, for a caller that needs to inspect its state."""

        return self._graph

    def start(
        self, messages: Sequence[ProviderMessage], *, thread_id: str
    ) -> AsyncIterator[StreamEvent]:
        """Run a fresh turn over `messages`."""

        return self._run(initial_state(list(messages)), thread_id)

    def resume(
        self, decisions: Sequence[Union[ToolApprovalDecision, JsonDict]], *, thread_id: str
    ) -> AsyncIterator[StreamEvent]:
        """Continue the turn paused on `thread_id` with the user's decisions.

        A decision arriving over a JSON transport may be given as the
        plain mapping it deserialized into, rather than as a
        `ToolApprovalDecision`. Raises `TurnNotPausedError` on the
        first iteration if the thread holds no paused turn.
        """

        return self._run(Command(resume=list(decisions)), thread_id, require_pause=True)

    async def _run(
        self, entry: Any, thread_id: str, *, require_pause: bool = False
    ) -> AsyncIterator[StreamEvent]:
        config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
        if require_pause and not (await self._graph.aget_state(config)).interrupts:
            raise TurnNotPausedError(thread_id)
        pause: Optional[ApprovalRequest] = None
        async for mode, chunk in self._graph.astream(
            entry, config=config, stream_mode=list(_STREAM_MODES)
        ):
            if mode == _CUSTOM:
                yield cast(StreamEvent, chunk)
            elif mode == _UPDATES:
                pause = _paused_on(chunk) or pause

        if pause is not None:
            for event in await self._pause_events(pause, config):
                yield event

    async def _pause_events(
        self, pause: ApprovalRequest, config: RunnableConfig
    ) -> List[StreamEvent]:
        """The pair of events announcing that the turn is waiting on the user."""

        snapshot = await self._graph.aget_state(config)
        accounting, generation_ids = _accounting_of(snapshot.values)
        return [
            ToolCallRequestEvent(
                approvals=list(pause.approvals), tool_calls=list(pause.tool_calls)
            ),
            DoneEvent(
                model=self._deps.config.model,
                finish_reason=FinishReason.TOOL_CALLS,
                usage=accounting.usage,
                cost=accounting.cost,
                prompt_cost=accounting.prompt_cost,
                completion_cost=accounting.completion_cost,
                tool_calls=list(pause.round_tool_calls) or list(pause.tool_calls),
                awaiting_approval=True,
                approval_count=len(pause.approvals),
                generation_id=generation_ids[-1] if generation_ids else None,
                generation_ids=list(generation_ids) or None,
            ),
        ]


def _paused_on(update: Any) -> Optional[ApprovalRequest]:
    """The approval request an `updates` chunk announces a pause on, if any."""

    if not isinstance(update, dict):
        return None
    interrupts = update.get(INTERRUPT)
    if not isinstance(interrupts, Iterable):
        return None
    for entry in interrupts:
        if isinstance(entry, Interrupt) and isinstance(entry.value, ApprovalRequest):
            return entry.value
    return None


def _accounting_of(values: Any) -> Tuple[GenerationAccounting, List[str]]:
    """The turn's accounting so far, read off a state snapshot."""

    if not isinstance(values, dict):
        return GenerationAccounting(), []
    state = cast(AgentTurnState, values)
    return (
        state.get("accounting") or GenerationAccounting(),
        list(state.get("generation_ids") or []),
    )
