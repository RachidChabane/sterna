"""The request-scoped object every tool-visible context is published against.

`llm.agent.streaming.request_context` publishes one request into the
ContextVars the tool implementations read -- the sandbox context, the
Brave and Maps quota headers, the image, video, spark and knowledge
base contexts -- and reads what it needs off a single object. The same
object is what the endpoint's disconnect handler reads to cancel a
turn and settle an aborted one.

`V2TurnSession` is that object for a turn served by the agent core. It
carries no streaming logic: it holds the request's switches, the
turn's running accounting, and the cancellation flag, so the context
installer and the disconnect handler both find what they already
expect.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .accounting import TurnAccounting

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)


class V2TurnSession:
    """One agent-core turn, as the tool contexts and the endpoint see it."""

    def __init__(
        self,
        *,
        model: str,
        model_name: Optional[str],
        is_openrouter: bool,
        flags,
        tools: List[Any],
        accounting: TurnAccounting,
        openrouter_key_for_tools: Callable[[], Any],
        media_tool_params: Optional[Dict[str, Any]] = None,
        spark_ignite_request: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.model = model
        self.model_name = model_name
        self.is_openrouter = is_openrouter
        self.tools = tools
        self.media_tool_params = media_tool_params
        self.spark_ignite_request = spark_ignite_request

        self.enable_file_tools = flags.file_tools
        self.enable_brave_search = flags.brave_search
        self.enable_google_maps = flags.google_maps
        self.enable_image_generation = flags.image_generation
        self.enable_video_generation = flags.video_generation
        self.enable_sparks = flags.sparks

        self.file_tools_context = None
        self.is_cancelled = False

        self._accounting = accounting
        self._resolve_openrouter_key = openrouter_key_for_tools

    # --- What the tool contexts read ------------------------------------

    async def _openrouter_key_for_tools(self) -> str:
        """The key a tool that always runs against OpenRouter must use."""

        return await self._resolve_openrouter_key()

    def rebind_accounting(self, accounting: TurnAccounting) -> None:
        """Point the turn at the figures the attempt now running accumulates."""

        self._accounting = accounting

    # --- What the endpoint reads ----------------------------------------

    @property
    def all_generation_ids(self) -> List[str]:
        """Every provider generation this turn has spanned so far."""

        return list(self._accounting.generation_ids)

    @property
    def final_usage_recorded(self) -> bool:
        """Whether the turn's aggregate usage row has already been written."""

        return self._accounting.settled

    def cancel(self) -> None:
        """Stop the turn at the next point the loop checks."""

        self.is_cancelled = True
        logger.info("agent_service.turn_cancelled", extra={"model": self.model})
