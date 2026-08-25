"""Unit tests for the agent loop's main cycle: answers, tool rounds, and the cap.

Every collaborator is a double, so what these assert is the loop's own
behaviour: which events reach the caller in which order, what the
model is asked for on each round, and when the loop stops.
"""

from __future__ import annotations

import unittest

from llm.agent_core.events import EventType, FinishReason
from llm.agent_core.graph import AgentLoop, AgentTurnConfig
from llm.tests.agent_core_doubles import (
    FIXTURE_MODEL,
    RecordingTool,
    ScriptedProvider,
    all_of,
    dependencies,
    event_names,
    first_of,
    run_turn,
    text_generation,
    tool_call,
    tool_call_generation,
    tool_result_messages,
    usage,
)


class PlainCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_turn_with_no_tool_calls_streams_content_then_done(self):
        provider = ScriptedProvider(
            [text_generation("gen-1", "The notes ", "list two ", "open items.")]
        )
        loop = AgentLoop(dependencies(provider))

        events = await run_turn(loop)

        self.assertEqual(
            event_names(events),
            [
                EventType.GENERATION_ID,
                EventType.CONTENT,
                EventType.CONTENT,
                EventType.CONTENT,
                EventType.DONE,
            ],
        )
        self.assertEqual(
            "".join(event.content for event in all_of(events, EventType.CONTENT)),
            "The notes list two open items.",
        )

    async def test_the_done_event_reports_the_model_finish_reason_and_accounting(self):
        provider = ScriptedProvider(
            [text_generation("gen-1", "hi", usage=usage(120, 40))]
        )
        loop = AgentLoop(dependencies(provider))

        done = first_of(await run_turn(loop), EventType.DONE)

        self.assertEqual(done.model, FIXTURE_MODEL)
        self.assertEqual(done.finish_reason, FinishReason.STOP)
        self.assertEqual(done.usage.total_tokens, 160)
        self.assertEqual(done.cost, 0.001)
        self.assertEqual(done.generation_ids, ["gen-1"])
        self.assertIsNone(done.tool_calls)

    async def test_a_usage_chunk_streams_a_usage_update_before_done(self):
        provider = ScriptedProvider([text_generation("gen-1", "hi", usage=usage(10, 5))])
        loop = AgentLoop(dependencies(provider))

        events = await run_turn(loop)

        update = first_of(events, EventType.USAGE_UPDATE)
        self.assertEqual(update.usage.total_tokens, 15)
        self.assertEqual(update.generation_ids, ["gen-1"])
        self.assertLess(events.index(update), events.index(first_of(events, EventType.DONE)))

    async def test_a_turn_never_calls_the_model_more_than_once_without_tool_calls(self):
        provider = ScriptedProvider([text_generation("gen-1", "hi")])
        loop = AgentLoop(dependencies(provider))

        await run_turn(loop)

        self.assertEqual(provider.call_count, 1)


class SingleToolRoundTripTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = RecordingTool("read_file", result={"success": True, "content": "# Notes"})
        self.provider = ScriptedProvider(
            [
                tool_call_generation(
                    "gen-1",
                    tool_call("call-1", "read_file", path="/workspace/notes.md"),
                    preamble="Reading the file.",
                ),
                text_generation("gen-2", "The notes open with a heading."),
            ]
        )
        self.loop = AgentLoop(dependencies(self.provider, [self.tool]))

    async def test_the_loop_runs_the_tool_and_asks_the_model_again(self):
        events = await run_turn(self.loop)

        self.assertEqual(
            event_names(events),
            [
                EventType.GENERATION_ID,
                EventType.CONTENT,
                EventType.FILE_TOOL_EXECUTING,
                EventType.FILE_TOOL_EXECUTED,
                EventType.GENERATION_ID,
                EventType.CONTENT,
                EventType.DONE,
            ],
        )
        self.assertEqual(self.provider.call_count, 2)

    async def test_the_handler_receives_the_decoded_arguments(self):
        await run_turn(self.loop)

        self.assertEqual(self.tool.calls, [{"path": "/workspace/notes.md"}])

    async def test_the_tool_result_is_fed_back_to_the_model_as_a_tool_message(self):
        await run_turn(self.loop)

        second_request = self.provider.requests[1]
        self.assertEqual(
            tool_result_messages(second_request.messages),
            [{"success": True, "content": "# Notes"}],
        )
        assistant = second_request.messages[-2]
        self.assertEqual(assistant.role, "assistant")
        self.assertEqual([call.id for call in assistant.tool_calls or []], ["call-1"])

    async def test_the_executed_event_carries_the_call_and_its_result(self):
        executed = first_of(await run_turn(self.loop), EventType.FILE_TOOL_EXECUTED)

        self.assertEqual([call.id for call in executed.tool_calls], ["call-1"])
        self.assertEqual(
            executed.results,
            [
                {
                    "tool_call": {
                        "id": "call-1",
                        "function": {"name": "read_file", "arguments": '{"path": "/workspace/notes.md"}'},
                        "type": "function",
                        "display_name": None,
                        "server_icon_url": None,
                        "server_icon_invert": None,
                    },
                    "result": {"success": True, "content": "# Notes"},
                    "success": True,
                }
            ],
        )

    async def test_the_generation_ids_of_every_round_reach_the_done_event(self):
        done = first_of(await run_turn(self.loop), EventType.DONE)

        self.assertEqual(done.generation_ids, ["gen-1", "gen-2"])
        self.assertEqual(done.generation_id, "gen-2")

    async def test_the_registry_tools_are_offered_on_every_request(self):
        await run_turn(self.loop)

        for request in self.provider.requests:
            self.assertEqual(
                [definition.function.name for definition in request.tools or []],
                ["read_file"],
            )


class MultiToolMultiRoundTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_calls_in_one_round_both_run_and_both_answer(self):
        reader = RecordingTool("read_file", result={"success": True, "content": "a"})
        lister = RecordingTool("list_files", result={"success": True, "entries": ["a", "b"]})
        provider = ScriptedProvider(
            [
                tool_call_generation(
                    "gen-1",
                    tool_call("call-1", "read_file", path="/a"),
                    tool_call("call-2", "list_files", path="/"),
                ),
                text_generation("gen-2", "done"),
            ]
        )
        loop = AgentLoop(dependencies(provider, [reader, lister]))

        events = await run_turn(loop)

        executed = first_of(events, EventType.FILE_TOOL_EXECUTED)
        self.assertEqual([call.id for call in executed.tool_calls], ["call-1", "call-2"])
        self.assertEqual(reader.calls, [{"path": "/a"}])
        self.assertEqual(lister.calls, [{"path": "/"}])
        self.assertEqual(
            tool_result_messages(provider.requests[1].messages),
            [{"success": True, "content": "a"}, {"success": True, "entries": ["a", "b"]}],
        )

    async def test_three_rounds_of_tool_calls_each_feed_the_next_generation(self):
        tool = RecordingTool("step", result={"success": True})
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "step", n=1)),
                tool_call_generation("gen-2", tool_call("call-2", "step", n=2)),
                tool_call_generation("gen-3", tool_call("call-3", "step", n=3)),
                text_generation("gen-4", "finished"),
            ]
        )
        loop = AgentLoop(dependencies(provider, [tool]))

        events = await run_turn(loop)

        self.assertEqual(tool.calls, [{"n": 1}, {"n": 2}, {"n": 3}])
        self.assertEqual(provider.call_count, 4)
        self.assertEqual(len(all_of(events, EventType.FILE_TOOL_EXECUTED)), 3)
        self.assertEqual(
            first_of(events, EventType.DONE).generation_ids,
            ["gen-1", "gen-2", "gen-3", "gen-4"],
        )

    async def test_a_call_naming_an_unknown_tool_is_answered_rather_than_raised(self):
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "no_such_tool")),
                text_generation("gen-2", "recovered"),
            ]
        )
        loop = AgentLoop(dependencies(provider))

        events = await run_turn(loop)

        self.assertEqual(first_of(events, EventType.DONE).finish_reason, FinishReason.STOP)
        answered = tool_result_messages(provider.requests[1].messages)
        self.assertEqual(len(answered), 1)
        self.assertFalse(answered[0]["success"])
        self.assertIn("no_such_tool", answered[0]["error"])

    async def test_a_handler_that_raises_is_answered_rather_than_ending_the_turn(self):
        tool = RecordingTool("flaky", raises=RuntimeError("sandbox is unreachable"))
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "flaky")),
                text_generation("gen-2", "recovered"),
            ]
        )
        loop = AgentLoop(dependencies(provider, [tool]))

        events = await run_turn(loop)

        self.assertEqual(all_of(events, EventType.ERROR), [])
        answered = tool_result_messages(provider.requests[1].messages)
        self.assertFalse(answered[0]["success"])
        self.assertIn("sandbox is unreachable", answered[0]["error"])


class IterationCapTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_loop_stops_after_the_configured_number_of_model_calls(self):
        tool = RecordingTool("step")
        provider = ScriptedProvider(
            [tool_call_generation("gen-loop", tool_call("call-loop", "step"))]
        )
        loop = AgentLoop(
            dependencies(
                provider,
                [tool],
                config=AgentTurnConfig(
                    model=FIXTURE_MODEL, max_iterations=3, heartbeat_interval_seconds=None
                ),
            )
        )

        events = await run_turn(loop)

        self.assertEqual(provider.call_count, 3)
        self.assertEqual(len(tool.calls), 2)
        done = first_of(events, EventType.DONE)
        self.assertEqual(done.finish_reason, FinishReason.TOOL_CALLS)
        self.assertEqual([call.id for call in done.tool_calls or []], ["call-loop"])

    async def test_the_cap_leaves_the_unanswered_calls_on_the_done_event(self):
        tool = RecordingTool("step")
        provider = ScriptedProvider(
            [tool_call_generation("gen-loop", tool_call("call-loop", "step"))]
        )
        loop = AgentLoop(
            dependencies(
                provider,
                [tool],
                config=AgentTurnConfig(
                    model=FIXTURE_MODEL, max_iterations=1, heartbeat_interval_seconds=None
                ),
            )
        )

        events = await run_turn(loop)

        self.assertEqual(provider.call_count, 1)
        self.assertEqual(tool.calls, [])
        self.assertIsNone(first_of(events, EventType.DONE).awaiting_approval)

    async def test_a_cap_below_one_is_rejected_at_configuration_time(self):
        with self.assertRaises(ValueError):
            AgentTurnConfig(model=FIXTURE_MODEL, max_iterations=0)


if __name__ == "__main__":
    unittest.main()
