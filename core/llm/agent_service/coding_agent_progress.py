"""Live progress for the long-running coding-agent tools.

`coding_agent`, `plan_implementation`, `implement_plan` and
`edit_plan` all hand the work to an agent running inside the user's
sandbox, and that agent runs for minutes. The tool call itself returns
only once the run is over, so without a second channel the client sees
nothing between the call being announced and its result.

That channel is the sandbox orchestrator's own progress endpoint. This
module is the `ToolProgressPort` the V2 turn supplies for it: while
one of those calls is in flight, the loop asks the open watch what has
happened, and the watch answers with the step, question and completion
events the frontend renders.

The three events are the whole contract. A step carries one entry of
the run's transcript; a question carries what the sandbox is blocked
on, which the user answers through `/code-sessions/coding-agent/answer/`
while the tool call is still waiting; a completion states what the run
produced. Nothing here blocks or resumes anything itself -- the wait
lives in the orchestrator's ask-user relay, and this reports on it.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, List, Optional, Sequence, Tuple

from ..agent_core.events import (
    CodingAgentCompletedEvent,
    CodingAgentQuestionEvent,
    CodingAgentStepEvent,
    JsonDict,
    StreamEvent,
    ToolCall,
)
from ..agent_core.graph import ToolProgressWatch
from ..agent_tool_handlers import CODING_AGENT_TOOL_NAMES

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

DEFAULT_STEP_TYPE = "text"
"""What a step whose transcript entry declares no type is reported as."""

MILLISECONDS_PER_SECOND = 1000

FOUND_FIELD = "found"
STEPS_FIELD = "steps"
PENDING_QUESTION_FIELD = "pending_question"
QUESTION_FIELD = "question"
OPTIONS_FIELD = "options"
TYPE_FIELD = "type"
TOOL_FIELD = "tool"
CONTENT_FIELD = "content"
TIMESTAMP_FIELD = "timestamp"
SUCCESS_FIELD = "success"
SUMMARY_FIELD = "summary"
FILES_MODIFIED_FIELD = "files_modified"
FILES_CREATED_FIELD = "files_created"
TOTAL_TOKENS_FIELD = "total_tokens"
RESULT_FIELD = "result"

ResolveContext = Callable[[], Any]
"""Reads the request's file-tools context, which only exists while it runs."""


class CodingAgentProgress:
    """Opens a progress watch for every call that runs the coding agent.

    The turn's file-tools context carries the user, the chat and the
    token the orchestrator is polled with, and it is installed after
    the turn's dependencies are assembled -- so it is read through a
    callable, at the moment a watch actually needs it.
    """

    def __init__(self, resolve_context: ResolveContext) -> None:
        self._resolve_context = resolve_context

    def watch(self, call: ToolCall) -> Optional[ToolProgressWatch]:
        if call.function.name not in CODING_AGENT_TOOL_NAMES:
            return None
        return CodingAgentRun(self._resolve_context)


class CodingAgentRun:
    """One coding-agent run, as the client watching it sees it.

    Holds how much of the run's transcript has already been reported,
    so each poll answers with the steps that are new, and the last
    progress payload it saw, so the completion event can still be
    assembled from a final poll that came back empty.
    """

    def __init__(self, resolve_context: ResolveContext) -> None:
        self._resolve_context = resolve_context
        self._reported_steps = 0
        self._last_progress: Optional[JsonDict] = None
        self._started_at = time.monotonic()

    async def poll(self) -> Sequence[StreamEvent]:
        """Whatever the run has done since the last time it was asked."""

        events, progress = await self._fetch()
        if progress is not None:
            self._last_progress = progress
        return events

    async def close(self, result: JsonDict) -> Sequence[StreamEvent]:
        """The rest of the run, and what it amounted to."""

        events, progress = await self._fetch()
        progress = progress or self._last_progress
        if progress is None:
            stored_events, progress = self._from_stored_result()
            events = list(events) + stored_events
        return list(events) + [self._completed(result, progress)]

    # --- Reading the orchestrator ---------------------------------------

    async def _fetch(self) -> Tuple[List[StreamEvent], Optional[JsonDict]]:
        """One poll of the progress endpoint, as events and raw payload.

        A poll that fails is reported as nothing having happened: a
        run must not end because the channel watching it could not
        reach the orchestrator.
        """

        context = self._resolve_context()
        if context is None:
            return [], None
        try:
            progress = await _progress_service().get_progress(
                user_id=context.user_id,
                # The repository may have been cloned under another
                # chat, and the run then belongs to that workspace.
                chat_id=context.workspace_chat_id or context.chat_id,
                job_id=None,
                auth_token=context.auth_token,
            )
        except Exception:
            logger.warning("coding_agent_progress.poll_failed", exc_info=True)
            return [], None

        if not progress.get(FOUND_FIELD):
            return [], None
        events = self._events_since(progress.get(STEPS_FIELD) or [])
        return events + _question(progress), progress

    def _events_since(self, steps: Sequence[JsonDict]) -> List[StreamEvent]:
        """The steps this watch has not reported yet, in transcript order."""

        events: List[StreamEvent] = [
            _step(index, steps[index])
            for index in range(self._reported_steps, len(steps))
        ]
        self._reported_steps = len(steps)
        return events

    def _from_stored_result(self) -> Tuple[List[StreamEvent], Optional[JsonDict]]:
        """The run as the tool handler recorded it, when no poll found it.

        A run short enough to finish before the first poll -- or one
        whose progress entry was already cleaned up -- is still fully
        described by what the handler stored on the request context.
        """

        context = self._resolve_context()
        stored = getattr(context, "last_coding_agent_result", None)
        if not stored:
            return [], None
        result = stored.get(RESULT_FIELD) or {}
        steps = stored.get(STEPS_FIELD) or []
        progress = {
            FOUND_FIELD: True,
            STEPS_FIELD: steps,
            TOTAL_TOKENS_FIELD: result.get(TOTAL_TOKENS_FIELD, 0),
            FILES_MODIFIED_FIELD: result.get(FILES_MODIFIED_FIELD, []),
            FILES_CREATED_FIELD: result.get(FILES_CREATED_FIELD, []),
            SUMMARY_FIELD: result.get(SUMMARY_FIELD),
        }
        return self._events_since(steps), progress

    # --- What the run amounted to ---------------------------------------

    def _completed(
        self, result: JsonDict, progress: Optional[JsonDict]
    ) -> CodingAgentCompletedEvent:
        """The terminal event, preferring the run's own figures to the tool's."""

        run = progress if progress else result
        return CodingAgentCompletedEvent(
            success=bool(result.get(SUCCESS_FIELD, False)),
            summary=result.get(SUMMARY_FIELD)
            or (progress.get(SUMMARY_FIELD) if progress else None),
            files_modified=list(run.get(FILES_MODIFIED_FIELD, [])),
            files_created=list(run.get(FILES_CREATED_FIELD, [])),
            duration_ms=self._elapsed_ms(),
            total_tokens=progress.get(TOTAL_TOKENS_FIELD, 0) if progress else 0,
            steps=[dict(step) for step in (progress or {}).get(STEPS_FIELD, [])],
        )

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * MILLISECONDS_PER_SECOND)


def _step(index: int, step: JsonDict) -> CodingAgentStepEvent:
    return CodingAgentStepEvent(
        step_index=index,
        type=step.get(TYPE_FIELD, DEFAULT_STEP_TYPE),
        tool=step.get(TOOL_FIELD),
        content=step.get(CONTENT_FIELD),
        timestamp=step.get(TIMESTAMP_FIELD),
    )


def _question(progress: JsonDict) -> List[StreamEvent]:
    """The question the run is blocked on, when it is blocked on one."""

    pending = progress.get(PENDING_QUESTION_FIELD)
    if not pending:
        return []
    return [
        CodingAgentQuestionEvent(
            question=pending.get(QUESTION_FIELD),
            options=pending.get(OPTIONS_FIELD),
        )
    ]


def _progress_service():
    """The coding-agent service, imported on use.

    Its module reaches Django models through the MCP serializer, so
    importing it at module scope would tie this module's import order
    to the app registry's.
    """

    from ..services.coding_agent_service import get_coding_agent_service

    return get_coding_agent_service()
