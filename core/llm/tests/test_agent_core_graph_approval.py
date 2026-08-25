"""Unit tests for the approval pause: what a paused turn streams, and what resuming it does.

A tool marked `ToolApproval.REQUIRED` stops the turn before it runs.
These tests pin what the caller sees at that point, that the tool has
not run yet, and that both answers — approved and denied — carry the
turn forward with a result the model can react to.
"""

from __future__ import annotations

import unittest

from llm.agent_core.events import EventType, FinishReason
from llm.agent_core.graph import (
    AgentLoop,
    ApprovalDecision,
    LocalApprovals,
    ToolApprovalDecision,
    TurnNotPausedError,
)
from llm.agent_core.registry import ToolApproval
from llm.tests.agent_core_doubles import (
    RecordingTool,
    ScriptedProvider,
    all_of,
    collect,
    dependencies,
    event_names,
    first_of,
    run_turn,
    text_generation,
    tool_call,
    tool_call_generation,
    tool_result_messages,
)

THREAD = "thread-approval"


def _gated_loop(**overrides):
    search = RecordingTool(
        "brave_web_search",
        result={"success": True, "results": ["one"]},
        approval=ToolApproval.REQUIRED,
    )
    provider = ScriptedProvider(
        [
            tool_call_generation(
                "gen-1",
                tool_call("call-search", "brave_web_search", query="sterna streaming"),
                preamble="Searching the web.",
            ),
            text_generation("gen-2", "Here is what I found."),
        ]
    )
    loop = AgentLoop(
        dependencies(provider, [search], approvals=LocalApprovals(), **overrides)
    )
    return loop, provider, search


class ApprovalPauseTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_gated_call_pauses_the_turn_before_the_tool_runs(self):
        loop, provider, search = _gated_loop()

        events = await run_turn(loop, thread_id=THREAD)

        self.assertEqual(
            event_names(events),
            [
                EventType.GENERATION_ID,
                EventType.CONTENT,
                EventType.TOOL_CALL_REQUEST,
                EventType.DONE,
            ],
        )
        self.assertEqual(search.calls, [])
        self.assertEqual(provider.call_count, 1)

    async def test_the_request_event_names_the_gated_call_and_its_approval(self):
        loop, _, _ = _gated_loop()

        request = first_of(await run_turn(loop, thread_id=THREAD), EventType.TOOL_CALL_REQUEST)

        self.assertEqual([call.id for call in request.tool_calls], ["call-search"])
        approval = request.approvals[0]
        self.assertEqual(approval.tool_id, "brave_web_search")
        self.assertEqual(approval.tool_name, "Brave Web Search")
        self.assertEqual(approval.arguments, {"query": "sterna streaming"})
        self.assertEqual(approval.status, "pending")

    async def test_the_paused_turn_ends_with_a_done_event_marked_awaiting_approval(self):
        loop, _, _ = _gated_loop()

        done = first_of(await run_turn(loop, thread_id=THREAD), EventType.DONE)

        self.assertEqual(done.finish_reason, FinishReason.TOOL_CALLS)
        self.assertTrue(done.awaiting_approval)
        self.assertEqual(done.approval_count, 1)
        self.assertEqual(done.generation_ids, ["gen-1"])

    async def test_an_ungated_call_in_the_same_round_does_not_pause_the_turn(self):
        reader = RecordingTool("read_file", result={"success": True})
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "read_file", path="/a")),
                text_generation("gen-2", "done"),
            ]
        )
        loop = AgentLoop(dependencies(provider, [reader]))

        events = await run_turn(loop, thread_id="thread-ungated")

        self.assertEqual(all_of(events, EventType.TOOL_CALL_REQUEST), [])
        self.assertEqual(reader.calls, [{"path": "/a"}])


def _mixed_round_loop():
    """A round asking for one ungated file tool and one gated catalog tool."""

    reader = RecordingTool("read_file", result={"success": True, "content": "# Notes"})
    search = RecordingTool(
        "brave_web_search", result={"success": True}, approval=ToolApproval.REQUIRED
    )
    provider = ScriptedProvider(
        [
            tool_call_generation(
                "gen-1",
                tool_call("call-read", "read_file", path="/workspace/notes.md"),
                tool_call("call-search", "brave_web_search", query="sterna streaming"),
                preamble="Reading the file and searching the web.",
            ),
            text_generation("gen-2", "Here is what I found."),
        ]
    )
    loop = AgentLoop(
        dependencies(provider, [reader, search], approvals=LocalApprovals())
    )
    return loop, provider, reader, search


class MixedGatedAndUngatedRoundTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_ungated_call_runs_before_the_turn_pauses(self):
        loop, _, reader, search = _mixed_round_loop()

        events = await run_turn(loop, thread_id="thread-mixed")

        self.assertEqual(
            event_names(events),
            [
                EventType.GENERATION_ID,
                EventType.CONTENT,
                EventType.FILE_TOOL_EXECUTING,
                EventType.FILE_TOOL_EXECUTED,
                EventType.TOOL_CALL_REQUEST,
                EventType.DONE,
            ],
        )
        self.assertEqual(reader.calls, [{"path": "/workspace/notes.md"}])
        self.assertEqual(search.calls, [])

    async def test_only_the_gated_call_is_put_up_for_approval(self):
        loop, _, _, _ = _mixed_round_loop()

        events = await run_turn(loop, thread_id="thread-mixed")

        executed = first_of(events, EventType.FILE_TOOL_EXECUTED)
        self.assertEqual([call.id for call in executed.tool_calls], ["call-read"])
        request = first_of(events, EventType.TOOL_CALL_REQUEST)
        self.assertEqual([call.id for call in request.tool_calls], ["call-search"])
        self.assertEqual([approval.tool_id for approval in request.approvals],
                         ["brave_web_search"])

    async def test_the_paused_done_event_reports_the_whole_round(self):
        loop, _, _, _ = _mixed_round_loop()

        done = first_of(await run_turn(loop, thread_id="thread-mixed"), EventType.DONE)

        self.assertEqual(done.finish_reason, FinishReason.TOOL_CALLS)
        self.assertEqual(
            [call.id for call in done.tool_calls or []], ["call-read", "call-search"]
        )
        self.assertTrue(done.awaiting_approval)
        self.assertEqual(done.approval_count, 1)

    async def test_resuming_runs_only_the_gated_call_and_keeps_both_results(self):
        loop, provider, reader, search = _mixed_round_loop()
        await run_turn(loop, thread_id="thread-mixed")

        await collect(
            loop.resume(
                [
                    ToolApprovalDecision(
                        tool_call_id="call-search", decision=ApprovalDecision.APPROVED
                    )
                ],
                thread_id="thread-mixed",
            )
        )

        self.assertEqual(reader.calls, [{"path": "/workspace/notes.md"}])
        self.assertEqual(search.calls, [{"query": "sterna streaming"}])
        self.assertEqual(
            tool_result_messages(provider.requests[1].messages),
            [{"success": True, "content": "# Notes"}, {"success": True}],
        )


class ApprovalResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_resuming_with_an_approval_runs_the_tool_and_finishes_the_turn(self):
        loop, provider, search = _gated_loop()
        await run_turn(loop, thread_id=THREAD)

        events = await collect(
            loop.resume(
                [
                    ToolApprovalDecision(
                        tool_call_id="call-search", decision=ApprovalDecision.APPROVED
                    )
                ],
                thread_id=THREAD,
            )
        )

        self.assertEqual(
            event_names(events),
            [
                EventType.FILE_TOOL_EXECUTING,
                EventType.FILE_TOOL_EXECUTED,
                EventType.GENERATION_ID,
                EventType.CONTENT,
                EventType.DONE,
            ],
        )
        self.assertEqual(search.calls, [{"query": "sterna streaming"}])
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(first_of(events, EventType.DONE).finish_reason, FinishReason.STOP)

    async def test_resuming_with_a_denial_answers_the_model_without_running_the_tool(self):
        loop, provider, search = _gated_loop()
        await run_turn(loop, thread_id=THREAD)

        events = await collect(
            loop.resume(
                [
                    ToolApprovalDecision(
                        tool_call_id="call-search", decision=ApprovalDecision.DENIED
                    )
                ],
                thread_id=THREAD,
            )
        )

        self.assertEqual(search.calls, [])
        self.assertEqual(provider.call_count, 2)
        answered = tool_result_messages(provider.requests[1].messages)
        self.assertFalse(answered[0]["success"])
        self.assertIn("declined", answered[0]["error"])
        self.assertEqual(first_of(events, EventType.DONE).finish_reason, FinishReason.STOP)

    async def test_a_gated_call_left_unanswered_counts_as_denied(self):
        loop, provider, search = _gated_loop()
        await run_turn(loop, thread_id=THREAD)

        await collect(loop.resume([], thread_id=THREAD))

        self.assertEqual(search.calls, [])
        answered = tool_result_messages(provider.requests[1].messages)
        self.assertFalse(answered[0]["success"])

    async def test_a_second_gated_round_pauses_again_on_the_same_thread(self):
        search = RecordingTool(
            "brave_web_search", result={"success": True}, approval=ToolApproval.REQUIRED
        )
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "brave_web_search", q="a")),
                tool_call_generation("gen-2", tool_call("call-2", "brave_web_search", q="b")),
                text_generation("gen-3", "done"),
            ]
        )
        loop = AgentLoop(dependencies(provider, [search], approvals=LocalApprovals()))

        await run_turn(loop, thread_id="thread-twice")
        second = await collect(
            loop.resume(
                [
                    ToolApprovalDecision(
                        tool_call_id="call-1", decision=ApprovalDecision.APPROVED
                    )
                ],
                thread_id="thread-twice",
            )
        )

        request = first_of(second, EventType.TOOL_CALL_REQUEST)
        self.assertEqual([call.id for call in request.tool_calls], ["call-2"])
        self.assertTrue(first_of(second, EventType.DONE).awaiting_approval)
        self.assertEqual(search.calls, [{"q": "a"}])

    async def test_two_turns_on_different_threads_pause_independently(self):
        loop_a, _, search_a = _gated_loop()
        await run_turn(loop_a, thread_id="thread-a")
        await run_turn(loop_a, thread_id="thread-b")

        await collect(
            loop_a.resume(
                [
                    ToolApprovalDecision(
                        tool_call_id="call-search", decision=ApprovalDecision.APPROVED
                    )
                ],
                thread_id="thread-a",
            )
        )

        self.assertEqual(search_a.calls, [{"query": "sterna streaming"}])

    async def test_resuming_a_thread_that_was_never_started_is_refused(self):
        loop, _, _ = _gated_loop()

        with self.assertRaises(TurnNotPausedError):
            await collect(
                loop.resume(
                    [
                        ToolApprovalDecision(
                            tool_call_id="call-search", decision=ApprovalDecision.APPROVED
                        )
                    ],
                    thread_id="thread-never-started",
                )
            )

    async def test_a_decision_arriving_twice_is_refused_without_rerunning_the_tool(self):
        loop, provider, search = _gated_loop()
        await run_turn(loop, thread_id=THREAD)
        decisions = [
            ToolApprovalDecision(
                tool_call_id="call-search", decision=ApprovalDecision.APPROVED
            )
        ]
        await collect(loop.resume(decisions, thread_id=THREAD))

        with self.assertRaises(TurnNotPausedError):
            await collect(loop.resume(decisions, thread_id=THREAD))

        self.assertEqual(search.calls, [{"query": "sterna streaming"}])
        self.assertEqual(provider.call_count, 2)

    async def test_a_decision_delivered_as_a_plain_mapping_is_understood(self):
        loop, _, search = _gated_loop()
        await run_turn(loop, thread_id=THREAD)

        await collect(
            loop.resume(
                [{"tool_call_id": "call-search", "decision": "approved"}],
                thread_id=THREAD,
            )
        )

        self.assertEqual(search.calls, [{"query": "sterna streaming"}])


if __name__ == "__main__":
    unittest.main()
