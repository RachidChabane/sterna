"""One V2 chat turn, from the quota gate to the aggregate usage row.

The agent loop streams a turn and nothing else. Everything around it
belongs to whoever owns the request, and that is this module: the
quota gate that must clear before any upstream call is made, the
per-request contexts every tool implementation reads, the wire the
frames are rendered onto, the usage row the turn is billed on, and the
teardown that runs whether the turn finished, failed, or the client
went away.

A rate limit is answered by asking for another model and running the
turn again, so a request whose first choice is saturated still gets an
answer. Anything else the provider reports ends the turn where it
happened.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Sequence

from ..agent.cost_ledger import CostLedger
from ..agent.sse_events import cancelled_event
from ..agent.streaming import request_context
from ..agent.streaming.quota_precheck import precheck_chat_quota
from ..agent_core import sse
from ..agent_core.events import DoneEvent, ErrorEvent, StreamEvent
from ..agent_core.graph import AgentLoop
from .accounting import TurnAccounting
from .dependencies import TurnRequest, TurnStack, build_turn_stack
from .messages import to_provider_messages
from .session import V2TurnSession
from .v2_wire import V2Wire, error_frame

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

RATE_LIMIT_STATUS_CODE = 429
STATUS_CODE_FIELD = "status_code"
EVENT_FIELD = "event"
DATA_FIELD = "data"
FROM_MODEL_FIELD = "from_model"
TO_MODEL_FIELD = "to_model"

REROUTE_EVENT_NAME = "sterna_reroute"

MAX_REROUTE_ATTEMPTS = 2
"""How many alternative models one turn may fall back to."""

THREAD_ID_TEMPLATE = "v2-{conversation_id}-{attempt}"


class ModelReroute(Protocol):
    """Answers a saturated model with another one to run the turn on."""

    async def alternative(
        self, failed: TurnRequest, excluded: Sequence[str]
    ) -> Optional[TurnRequest]:
        ...


class NoReroute:
    """A reroute port that never offers an alternative."""

    async def alternative(
        self, failed: TurnRequest, excluded: Sequence[str]
    ) -> Optional[TurnRequest]:
        return None


@dataclasses.dataclass(slots=True)
class _Attempt:
    """How one run of the turn on one model ended."""

    failure: Optional[ErrorEvent] = None
    cancelled: bool = False


class V2TurnRunner:
    """Runs one V2 chat request through the agent core and onto the wire.

    Constructed synchronously so the endpoint holds the turn's session
    -- what it cancels and settles a disconnected stream through --
    before the first frame is produced.
    """

    def __init__(
        self,
        *,
        turn: TurnRequest,
        messages: Sequence[Dict[str, Any]],
        system_prompt: Optional[str],
        auth_token: str,
        openrouter_key_for_tools,
        summarizer_endpoint,
        model_display_name: Optional[str] = None,
        model_metadata: Optional[Dict[str, Any]] = None,
        uploaded_files: Optional[List[Dict[str, str]]] = None,
        is_openrouter: bool = True,
        reroute: Optional[ModelReroute] = None,
        media_tool_params: Optional[Dict[str, Any]] = None,
        spark_ignite_request: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._turn = turn
        self._messages = list(messages)
        self._system_prompt = system_prompt
        self._auth_token = auth_token
        self._model_metadata = model_metadata
        self._uploaded_files = uploaded_files
        self._summarizer_endpoint = summarizer_endpoint
        self._reroute = reroute or NoReroute()

        self._accounting = TurnAccounting()
        self.session = V2TurnSession(
            model=turn.model,
            model_name=model_display_name,
            is_openrouter=is_openrouter,
            flags=turn.flags,
            tools=[],
            accounting=self._accounting,
            openrouter_key_for_tools=openrouter_key_for_tools,
            media_tool_params=media_tool_params,
            spark_ignite_request=spark_ignite_request,
        )

    async def frames(self) -> AsyncIterator[str]:
        """Every SSE frame this turn puts on the wire, in order."""

        denial = await precheck_chat_quota(
            user_id=self._turn.user_id,
            model_id=self._turn.model,
            messages=self._messages,
        )
        if denial is not None:
            yield _rendered(denial)
            return

        turn = self._turn
        excluded: List[str] = []
        for attempt_number in range(1 + MAX_REROUTE_ATTEMPTS):
            attempt = _Attempt()
            async for frame in self._run_attempt(turn, attempt_number, attempt):
                yield frame

            if attempt.cancelled:
                yield _rendered(cancelled_event(turn.model))
                return
            if attempt.failure is None:
                return

            excluded.append(turn.model)
            alternative = (
                await self._alternative_for(attempt.failure, turn, excluded)
                if attempt_number < MAX_REROUTE_ATTEMPTS
                else None
            )
            if alternative is None:
                yield error_frame(attempt.failure)
                return

            logger.info(
                "agent_service.rerouted",
                extra={"from_model": turn.model, "to_model": alternative.model},
            )
            yield sse.render_frame(
                REROUTE_EVENT_NAME,
                {FROM_MODEL_FIELD: turn.model, TO_MODEL_FIELD: alternative.model},
            )
            turn = alternative
            self.session.model = alternative.model

    # --- One run on one model ---------------------------------------------

    async def _alternative_for(
        self, failure: ErrorEvent, turn: TurnRequest, excluded: Sequence[str]
    ) -> Optional[TurnRequest]:
        if not _is_rate_limited(failure):
            return None
        return await self._reroute.alternative(turn, excluded)

    async def _run_attempt(
        self, turn: TurnRequest, attempt_number: int, attempt: _Attempt
    ) -> AsyncIterator[str]:
        """The frames one run of the turn produces, failure excluded."""

        stack = await build_turn_stack(
            turn, summarizer_endpoint=self._summarizer_endpoint
        )
        self.session.tools = list(stack.tool_set.bound_callables.values())
        self._accounting = TurnAccounting()
        self.session.rebind_accounting(self._accounting)

        execution_id = await request_context.install(
            self.session,
            user_id=turn.user_id,
            conversation_id=turn.conversation_id,
            chat_id=turn.chat_id or "",
            auth_token=self._auth_token,
            model_metadata=self._model_metadata,
            uploaded_files=self._uploaded_files,
        )
        wire = V2Wire(
            self._accounting,
            display_names=stack.tool_set.display_names,
            server_icons=stack.tool_set.server_icons,
            file_tools_enabled=turn.flags.file_tools,
        )
        try:
            async for frame in wire.frames(
                self._events(stack, turn, attempt_number, attempt)
            ):
                yield frame
        finally:
            request_context.clear(self.session, execution_id)
            await stack.http_client.aclose()

    async def _events(
        self,
        stack: TurnStack,
        turn: TurnRequest,
        attempt_number: int,
        attempt: _Attempt,
    ) -> AsyncIterator[StreamEvent]:
        """The loop's events, with billing and cancellation folded in.

        A terminal failure is recorded rather than forwarded, so the
        caller can choose between rerouting and putting it on the wire.
        """

        loop = AgentLoop(stack.dependencies)
        stream = loop.start(
            to_provider_messages(self._messages, system_prompt=self._system_prompt),
            thread_id=THREAD_ID_TEMPLATE.format(
                conversation_id=turn.conversation_id, attempt=attempt_number
            ),
        )
        async for event in stream:
            if self.session.is_cancelled:
                attempt.cancelled = True
                return
            if isinstance(event, ErrorEvent):
                attempt.failure = event
                return
            if isinstance(event, DoneEvent):
                await self._settle(turn)
            yield event

    async def _settle(self, turn: TurnRequest) -> None:
        """Write the aggregate usage row before the turn's `done` reaches the wire."""

        ledger = CostLedger(lambda: turn.user_id, turn.model)
        await ledger.record_chat_aggregate_usage(
            self._accounting.prompt_tokens,
            self._accounting.completion_tokens,
            self._accounting.tool_cost,
            self._accounting.image_generation_cost,
        )
        self._accounting.settled = ledger.final_usage_recorded


def _is_rate_limited(error: ErrorEvent) -> bool:
    extra = error.extra or {}
    return extra.get(STATUS_CODE_FIELD) == RATE_LIMIT_STATUS_CODE


def _rendered(event: Dict[str, Any]) -> str:
    """One event mapping from the shared SSE helpers, as the frame it writes."""

    return sse.render_frame(event[EVENT_FIELD], event[DATA_FIELD])
