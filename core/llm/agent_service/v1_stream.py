"""One V1 chat turn, from the quota gate to the aggregate usage row.

The agent loop streams a turn and nothing else. Everything around it
belongs to whoever owns the request, and for the direct-completion
endpoint that is this module: the quota gate that must clear before
any upstream call is made, the wire the frames are rendered onto, the
usage row the turn is billed on, and the client the turn streamed
over.

A V1 turn runs on the model it was asked for. A provider failure ends
it there and reaches the client as an `error` event, which is the
whole of V1's failure handling -- there is no second model to fall
back to and no reroute announcement to read.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, Optional, Sequence

from .quota_precheck import precheck_chat_quota
from ..agent_core.events import DoneEvent, StreamEvent
from ..agent_core.graph import AgentLoop
from ..agent_core.mcp_bridge import MCPToolSource
from .accounting import TurnAccounting
from .dependencies import TurnRequest, V1TurnStack, build_v1_turn_stack
from .messages import to_v1_provider_messages
from .settlement import rendered, settle_turn
from .v1_wire import V1Wire

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

THREAD_ID_TEMPLATE = "v1-{conversation_id}"


class V1TurnRunner:
    """Runs one V1 chat request through the agent core and onto the wire."""

    def __init__(
        self,
        *,
        turn: TurnRequest,
        messages: Sequence[Dict[str, Any]],
        system_prompt: Optional[str],
        auth_token: Optional[str] = None,
        model_metadata: Optional[Dict[str, Any]] = None,
        mcp_tools: Optional[MCPToolSource] = None,
    ) -> None:
        self._turn = turn
        self._messages = list(messages)
        self._system_prompt = system_prompt
        self._auth_token = auth_token
        self._model_metadata = model_metadata
        self._mcp_tools = mcp_tools
        self._accounting = TurnAccounting()

    async def frames(self) -> AsyncIterator[str]:
        """Every SSE frame this turn puts on the wire, in order."""

        denial = await precheck_chat_quota(
            user_id=self._turn.user_id,
            model_id=self._turn.model,
            messages=self._messages,
        )
        if denial is not None:
            yield rendered(denial)
            return

        stack = await build_v1_turn_stack(
            self._turn,
            mcp_tools=self._mcp_tools,
            auth_token=self._auth_token,
            model_metadata=self._model_metadata,
        )
        wire = V1Wire(self._accounting)
        try:
            async for frame in wire.frames(self._events(stack)):
                yield frame
        finally:
            await stack.http_client.aclose()

    async def _events(self, stack: V1TurnStack) -> AsyncIterator[StreamEvent]:
        """The loop's events, with the turn's billing folded in."""

        turn = self._turn
        loop = AgentLoop(stack.dependencies)
        stream = loop.start(
            to_v1_provider_messages(self._messages, system_prompt=self._system_prompt),
            thread_id=THREAD_ID_TEMPLATE.format(conversation_id=turn.conversation_id),
        )
        async for event in stream:
            if isinstance(event, DoneEvent):
                await settle_turn(
                    self._accounting, user_id=turn.user_id, model=turn.model
                )
            yield event
