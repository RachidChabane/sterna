"""Unit tests for the coding-agent progress port.

The port is driven the way the loop drives it -- a watch per call,
polled while the call runs and closed with what the call returned --
against a stand-in for the orchestrator's progress endpoint. What each
poll and the close produce is asserted as typed events, so a change to
the shape the frontend reads fails here as well as in the transcripts.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional
from unittest import mock

from llm.agent_core.events import (
    CodingAgentCompletedEvent,
    CodingAgentQuestionEvent,
    CodingAgentStepEvent,
    ToolCall,
    ToolCallFunction,
)
from llm.agent_service.coding_agent_progress import CodingAgentProgress

USER_ID = "user-1"
CHAT_ID = "chat-1"
WORKSPACE_CHAT_ID = "chat-workspace"
AUTH_TOKEN = "token-1"

QUESTION = "Delete the row once it is archived?"
OPTIONS = [{"label": "Delete", "description": "Remove it."}]

FIRST_STEP = {"type": "system", "tool": None, "content": "System: init"}
SECOND_STEP = {"type": "tool_call", "tool": "Write", "content": "Using Write"}


class _Context:
    """The request's file-tools context, as the port reads it."""

    def __init__(self, *, workspace_chat_id: Optional[str] = None, stored=None) -> None:
        self.user_id = USER_ID
        self.chat_id = CHAT_ID
        self.auth_token = AUTH_TOKEN
        self.workspace_chat_id = workspace_chat_id
        self.last_coding_agent_result = stored


class _ProgressEndpoint:
    """Answers each poll with the next scripted progress payload."""

    def __init__(self, replies: List[Dict[str, Any]], raises=None) -> None:
        self._replies = list(replies)
        self._raises = raises
        self.polled: List[Dict[str, Any]] = []

    async def get_progress(self, *, user_id, chat_id, job_id, auth_token):
        self.polled.append({"user_id": user_id, "chat_id": chat_id, "job_id": job_id})
        if self._raises is not None:
            raise self._raises
        if len(self._replies) > 1:
            return self._replies.pop(0)
        return self._replies[0]


def _call(name: str) -> ToolCall:
    return ToolCall(
        id="call-1", type="function", function=ToolCallFunction(name=name, arguments="{}")
    )


def _not_found() -> Dict[str, Any]:
    return {"found": False}


def _running(steps, pending_question=None, **figures) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"found": True, "steps": list(steps)}
    payload.update(figures)
    if pending_question is not None:
        payload["pending_question"] = pending_question
    return payload


class CodingAgentProgressTests(unittest.IsolatedAsyncioTestCase):
    def _patch_service(self, endpoint):
        return mock.patch(
            "llm.agent_service.coding_agent_progress._progress_service",
            return_value=endpoint,
        )

    # --- Which calls are watched at all ---------------------------------

    def test_only_a_coding_agent_call_is_watched(self):
        port = CodingAgentProgress(lambda: _Context())

        self.assertIsNone(port.watch(_call("read_file")))
        for tool in ("coding_agent", "plan_implementation", "implement_plan", "edit_plan"):
            self.assertIsNotNone(port.watch(_call(tool)), tool)

    def test_each_call_is_watched_on_its_own(self):
        port = CodingAgentProgress(lambda: _Context())

        self.assertIsNot(port.watch(_call("coding_agent")), port.watch(_call("edit_plan")))

    # --- What a poll reports --------------------------------------------

    async def test_a_poll_reports_only_the_steps_it_has_not_reported(self):
        endpoint = _ProgressEndpoint(
            [_running([FIRST_STEP]), _running([FIRST_STEP, SECOND_STEP])]
        )
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            first = await watch.poll()
            second = await watch.poll()

        self.assertEqual([event.step_index for event in first], [0])
        self.assertEqual([event.step_index for event in second], [1])
        self.assertEqual(second[0].tool, "Write")
        self.assertEqual(second[0].content, "Using Write")

    async def test_a_step_without_a_declared_type_is_reported_as_text(self):
        endpoint = _ProgressEndpoint([_running([{"content": "thinking"}])])
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            reported = await watch.poll()

        self.assertEqual(reported[0].type, "text")
        self.assertIsNone(reported[0].tool)

    async def test_a_run_the_orchestrator_has_no_record_of_reports_nothing(self):
        endpoint = _ProgressEndpoint([_not_found()])
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            self.assertEqual(await watch.poll(), [])

    async def test_a_blocked_run_reports_the_question_after_its_steps(self):
        endpoint = _ProgressEndpoint(
            [
                _running(
                    [FIRST_STEP],
                    pending_question={"question": QUESTION, "options": OPTIONS},
                )
            ]
        )
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("implement_plan"))

        with self._patch_service(endpoint):
            reported = await watch.poll()

        self.assertIsInstance(reported[0], CodingAgentStepEvent)
        self.assertIsInstance(reported[1], CodingAgentQuestionEvent)
        self.assertEqual(reported[1].question, QUESTION)
        self.assertEqual(reported[1].options, OPTIONS)

    async def test_a_poll_that_fails_reports_nothing_rather_than_raising(self):
        endpoint = _ProgressEndpoint([_not_found()], raises=RuntimeError("unreachable"))
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            self.assertEqual(await watch.poll(), [])

    async def test_a_turn_with_no_context_reports_nothing(self):
        endpoint = _ProgressEndpoint([_running([FIRST_STEP])])
        port = CodingAgentProgress(lambda: None)
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            self.assertEqual(await watch.poll(), [])

        self.assertEqual(endpoint.polled, [])

    async def test_the_run_is_polled_under_the_workspace_the_repo_was_cloned_into(self):
        endpoint = _ProgressEndpoint([_running([])])
        port = CodingAgentProgress(
            lambda: _Context(workspace_chat_id=WORKSPACE_CHAT_ID)
        )
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            await watch.poll()

        self.assertEqual(endpoint.polled[0]["chat_id"], WORKSPACE_CHAT_ID)

    # --- What closing the run reports ------------------------------------

    async def test_closing_reports_the_rest_of_the_run_and_its_figures(self):
        endpoint = _ProgressEndpoint(
            [
                _running(
                    [FIRST_STEP, SECOND_STEP],
                    total_tokens=1200,
                    files_created=["a.py"],
                    files_modified=["b.py"],
                    summary="ran to completion",
                )
            ]
        )
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            reported = await watch.close({"success": True})

        steps = [event for event in reported if isinstance(event, CodingAgentStepEvent)]
        completed = reported[-1]
        self.assertEqual([event.step_index for event in steps], [0, 1])
        self.assertIsInstance(completed, CodingAgentCompletedEvent)
        self.assertTrue(completed.success)
        self.assertEqual(completed.summary, "ran to completion")
        self.assertEqual(completed.files_created, ["a.py"])
        self.assertEqual(completed.files_modified, ["b.py"])
        self.assertEqual(completed.total_tokens, 1200)
        self.assertEqual(len(completed.steps), 2)
        self.assertGreaterEqual(completed.duration_ms, 0)

    async def test_the_tool_s_own_summary_is_preferred_to_the_run_s(self):
        endpoint = _ProgressEndpoint([_running([], summary="from the progress store")])
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            reported = await watch.close({"success": True, "summary": "from the tool"})

        self.assertEqual(reported[-1].summary, "from the tool")

    async def test_a_run_no_poll_found_is_reported_from_what_the_tool_stored(self):
        stored = {
            "steps": [FIRST_STEP, SECOND_STEP],
            "result": {
                "total_tokens": 900,
                "files_created": ["c.py"],
                "files_modified": [],
                "summary": "stored summary",
            },
        }
        endpoint = _ProgressEndpoint([_not_found()])
        port = CodingAgentProgress(lambda: _Context(stored=stored))
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            reported = await watch.close({"success": True})

        steps = [event for event in reported if isinstance(event, CodingAgentStepEvent)]
        completed = reported[-1]
        self.assertEqual([event.step_index for event in steps], [0, 1])
        self.assertEqual(completed.summary, "stored summary")
        self.assertEqual(completed.files_created, ["c.py"])
        self.assertEqual(completed.total_tokens, 900)

    async def test_a_step_already_reported_is_not_reported_again_on_close(self):
        endpoint = _ProgressEndpoint([_running([FIRST_STEP, SECOND_STEP])])
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            await watch.poll()
            reported = await watch.close({"success": True})

        self.assertEqual(
            [event for event in reported if isinstance(event, CodingAgentStepEvent)], []
        )

    async def test_a_run_with_nothing_to_report_still_states_that_it_finished(self):
        endpoint = _ProgressEndpoint([_not_found()])
        port = CodingAgentProgress(lambda: _Context())
        watch = port.watch(_call("coding_agent"))

        with self._patch_service(endpoint):
            reported = await watch.close(
                {"success": False, "files_modified": ["d.py"], "files_created": []}
            )

        completed = reported[-1]
        self.assertEqual(len(reported), 1)
        self.assertFalse(completed.success)
        self.assertEqual(completed.files_modified, ["d.py"])
        self.assertEqual(completed.steps, [])
        self.assertEqual(completed.total_tokens, 0)


if __name__ == "__main__":
    unittest.main()
