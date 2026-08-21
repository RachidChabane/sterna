"""Live progress for the long-running coding-agent tools.

Progress reporter. The coding-agent tools run for minutes inside the
sandbox, so while the tool task is in flight the streaming loops poll the
orchestrator through this collaborator and forward whatever new steps it
reports as SSE events. It also assembles the terminal
``coding_agent_completed`` event and folds the progress payload back into
the tool result the model sees.

Every method is non-yielding: it returns lists of event dicts for the
caller to yield, so the streaming generators keep sole ownership of
control flow.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

EVENT_CODING_AGENT_STEP = "coding_agent_step"
EVENT_CODING_AGENT_QUESTION = "coding_agent_question"
EVENT_CODING_AGENT_COMPLETED = "coding_agent_completed"

DEFAULT_STEP_TYPE = "text"


def _step_event(index: int, step: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event": EVENT_CODING_AGENT_STEP,
        "data": {
            "step_index": index,
            "type": step.get("type", DEFAULT_STEP_TYPE),
            "tool": step.get("tool"),
            "content": step.get("content"),
            "timestamp": step.get("timestamp"),
        },
    }


class CodingAgentProgressReporter:
    """Polls the orchestrator and turns its progress into SSE events."""

    def __init__(self, resolve_file_tools_context: Callable[[], Any]):
        # Read through a callable: the file-tools context only exists for
        # the duration of a request and is installed by `astream_chat`.
        self._resolve_file_tools_context = resolve_file_tools_context

    async def poll(self, last_step_count: int) -> Tuple[List[dict], int, Optional[dict]]:
        """
        Poll orchestrator for coding agent progress steps.

        Returns:
            (events, new_step_count, progress_data) where events is a list of
            SSE event dicts to yield, new_step_count is the updated count,
            and progress_data is the raw progress dict (or None).
        """
        context = self._resolve_file_tools_context()
        if not context:
            return [], last_step_count, None
        try:
            from ..services.coding_agent_service import get_coding_agent_service
            service = get_coding_agent_service()
            # Use workspace_chat_id if resolved (repo may be cloned in a different chat)
            poll_chat_id = context.workspace_chat_id or context.chat_id
            progress = await service.get_progress(
                user_id=context.user_id,
                chat_id=poll_chat_id,
                job_id=None,
                auth_token=context.auth_token,
            )
            found = progress.get("found")
            steps = progress.get("steps", [])
            step_count = progress.get("step_count", 0)
            logger.info(f"[LangChain] Progress poll: found={found}, step_count={step_count}, steps_len={len(steps)}, last={last_step_count}")

            if not found:
                return [], last_step_count, None

            events = [_step_event(i, steps[i]) for i in range(last_step_count, len(steps))]

            # Check for pending question from coding agent
            pending_q = progress.get("pending_question")
            if pending_q:
                events.append({
                    "event": EVENT_CODING_AGENT_QUESTION,
                    "data": {
                        "question": pending_q.get("question"),
                        "options": pending_q.get("options"),
                    },
                })

            return events, len(steps), progress
        except Exception as e:
            logger.info(f"[LangChain] Progress poll failed: {e}")
            return [], last_step_count, None

    @staticmethod
    def build_completed_event(result: dict, progress: dict, duration_ms: int) -> dict:
        """Build a coding_agent_completed SSE event from tool result and progress data."""
        return {
            "event": EVENT_CODING_AGENT_COMPLETED,
            "data": {
                "success": result.get("success", False),
                "summary": result.get("summary") or (progress.get("summary") if progress else None),
                "files_modified": (progress.get("files_modified", []) if progress else result.get("files_modified", [])),
                "files_created": (progress.get("files_created", []) if progress else result.get("files_created", [])),
                "duration_ms": duration_ms,
                "total_tokens": (progress.get("total_tokens", 0) if progress else 0),
                "steps": (progress.get("steps", []) if progress else []),
            }
        }

    @staticmethod
    def enrich_result(result: dict, progress: dict, duration_ms: int) -> dict:
        """Enrich a coding agent tool result with coding_agent_data for frontend display."""
        result["coding_agent_data"] = {
            "steps": (progress.get("steps", []) if progress else []),
            "duration_ms": duration_ms,
            "total_tokens": (progress.get("total_tokens", 0) if progress else 0),
            "cost_usd": (progress.get("total_cost_usd", 0) if progress else 0),
            "files_created": (progress.get("files_created", []) if progress else result.get("files_created", [])),
            "files_modified": (progress.get("files_modified", []) if progress else result.get("files_modified", [])),
            "summary": result.get("summary") or (progress.get("summary") if progress else None),
            "success": result.get("success", False),
        }
        return result

    async def final_data(self, last_step_count: int, last_progress: dict) -> Tuple[List[dict], Optional[dict]]:
        """
        Get final coding agent data after tool completion.

        Tries the progress endpoint first, then falls back to the stored result
        from FileToolsContext.last_coding_agent_result (set by tool functions).

        Returns:
            (events, progress_data) - list of SSE events to yield, and progress dict
        """
        # Try progress endpoint first
        final_events, _, final_progress = await self.poll(last_step_count)
        progress_data = final_progress or last_progress

        context = self._resolve_file_tools_context()
        if progress_data or not context or not context.last_coding_agent_result:
            return final_events, progress_data

        # Fallback: use stored result from tool execution
        stored = context.last_coding_agent_result
        stored_result_data = stored.get("result", {})
        progress_data = {
            "found": True,
            "steps": stored.get("steps", []),
            "step_count": len(stored.get("steps", [])),
            "total_tokens": stored_result_data.get("total_tokens", 0),
            "total_cost_usd": stored_result_data.get("total_cost_usd", 0),
            "files_modified": stored_result_data.get("files_modified", []),
            "files_created": stored_result_data.get("files_created", []),
            "summary": stored_result_data.get("summary"),
        }
        # Emit step events for steps not yet seen by the frontend
        final_events.extend(
            _step_event(i, progress_data["steps"][i])
            for i in range(last_step_count, len(progress_data["steps"]))
        )
        logger.info(f"[LangChain] Using stored result fallback: {len(progress_data['steps'])} steps, {progress_data['total_tokens']} tokens")

        return final_events, progress_data
