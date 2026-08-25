"""Unit tests for how a turn ends badly, and for the ports that shape it.

A provider failure is terminal: what has already streamed stays
streamed, an `error` event follows, and no `done` event closes the
turn. Retrying is allowed only while nothing has reached the caller
yet. The remaining tests cover the caller-supplied ports the loop runs
through on its way there.
"""

from __future__ import annotations

import unittest
from typing import List, Optional, Sequence

from llm.agent_core.events import (
    ContextTrimmedEvent,
    ErrorCode,
    EventType,
    JsonDict,
    PreviewStartedEvent,
    StreamEvent,
    ToolCall,
    Usage,
)
from llm.agent_core.graph import (
    AgentLoop,
    AgentTurnConfig,
    ContextRelief,
    CostBreakdown,
    RetryPolicy,
    to_error_event,
)
from llm.agent_core.graph.errors import (
    QUOTA_EXCEEDED_MESSAGE,
    SERVICE_UNAVAILABLE_MESSAGE,
)
from llm.agent_core.provider import (
    ProviderContentDeltaChunk,
    ProviderGenerationIdChunk,
    ProviderMessage,
)
from llm.agent_core.provider_errors import (
    ProviderOverloadedError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
)
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
)


def _failing_mid_stream(error: BaseException) -> List[object]:
    return [
        ProviderGenerationIdChunk(generation_id="gen-1"),
        ProviderContentDeltaChunk(content="The notes "),
        error,
    ]


class ProviderFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_mid_stream_failure_ends_the_turn_with_an_error_and_no_done(self):
        provider = ScriptedProvider(
            [_failing_mid_stream(ProviderOverloadedError("502 Bad Gateway", status_code=502))]
        )
        loop = AgentLoop(dependencies(provider))

        events = await run_turn(loop)

        self.assertEqual(
            event_names(events),
            [EventType.GENERATION_ID, EventType.CONTENT, EventType.ERROR],
        )
        self.assertEqual(all_of(events, EventType.DONE), [])

    async def test_the_error_event_carries_a_readable_message_and_the_raw_detail(self):
        provider = ScriptedProvider(
            [_failing_mid_stream(ProviderOverloadedError("502 Bad Gateway", status_code=502))]
        )
        loop = AgentLoop(dependencies(provider))

        error = first_of(await run_turn(loop), EventType.ERROR)

        self.assertEqual(error.error, SERVICE_UNAVAILABLE_MESSAGE)
        self.assertEqual(error.detail, "502 Bad Gateway")
        self.assertEqual(error.extra, {"status_code": 502})
        self.assertIsNone(error.code)

    async def test_a_quota_failure_carries_the_code_a_frontend_reacts_to(self):
        provider = ScriptedProvider(
            [ProviderQuotaExceededError("out of credits", status_code=402)]
        )
        loop = AgentLoop(dependencies(provider))

        error = first_of(await run_turn(loop), EventType.ERROR)

        self.assertEqual(error.error, QUOTA_EXCEEDED_MESSAGE)
        self.assertEqual(error.code, ErrorCode.QUOTA_EXCEEDED)

    async def test_a_failure_in_a_later_round_keeps_the_earlier_rounds_streamed(self):
        tool = RecordingTool("read_file", result={"success": True})
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "read_file", path="/a")),
                _failing_mid_stream(ProviderOverloadedError("upstream down")),
            ]
        )
        loop = AgentLoop(dependencies(provider, [tool]))

        events = await run_turn(loop)

        self.assertEqual(
            event_names(events),
            [
                EventType.GENERATION_ID,
                EventType.FILE_TOOL_EXECUTING,
                EventType.FILE_TOOL_EXECUTED,
                EventType.GENERATION_ID,
                EventType.CONTENT,
                EventType.ERROR,
            ],
        )
        self.assertEqual(tool.calls, [{"path": "/a"}])

    def test_the_error_mapping_falls_back_for_an_unmapped_failure(self):
        event = to_error_event(ProviderRateLimitError("slow down", status_code=429))

        self.assertEqual(event.detail, "slow down")
        self.assertIsNone(event.code)


class RetryPolicyTests(unittest.IsolatedAsyncioTestCase):
    def _config(self, max_attempts: int) -> AgentTurnConfig:
        return AgentTurnConfig(
            model=FIXTURE_MODEL,
            heartbeat_interval_seconds=None,
            retry=RetryPolicy(max_attempts=max_attempts),
        )

    async def test_a_transient_failure_before_any_output_is_retried(self):
        provider = ScriptedProvider(
            [
                ProviderOverloadedError("upstream down"),
                text_generation("gen-2", "recovered"),
            ]
        )
        loop = AgentLoop(dependencies(provider, config=self._config(2)))

        events = await run_turn(loop)

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(all_of(events, EventType.ERROR), [])
        self.assertEqual(first_of(events, EventType.CONTENT).content, "recovered")

    async def test_a_failure_after_output_has_streamed_is_never_retried(self):
        provider = ScriptedProvider(
            [
                _failing_mid_stream(ProviderOverloadedError("upstream down")),
                text_generation("gen-2", "recovered"),
            ]
        )
        loop = AgentLoop(dependencies(provider, config=self._config(3)))

        events = await run_turn(loop)

        self.assertEqual(provider.call_count, 1)
        self.assertEqual(len(all_of(events, EventType.ERROR)), 1)

    async def test_a_failure_the_policy_does_not_cover_is_never_retried(self):
        provider = ScriptedProvider(
            [ProviderQuotaExceededError("out of credits"), text_generation("gen-2", "x")]
        )
        loop = AgentLoop(dependencies(provider, config=self._config(3)))

        await run_turn(loop)

        self.assertEqual(provider.call_count, 1)

    async def test_the_attempt_budget_is_finite(self):
        provider = ScriptedProvider([ProviderOverloadedError("upstream down")])
        loop = AgentLoop(dependencies(provider, config=self._config(3)))

        events = await run_turn(loop)

        self.assertEqual(provider.call_count, 3)
        self.assertEqual(len(all_of(events, EventType.ERROR)), 1)

    async def test_retrying_is_off_unless_the_caller_asks_for_it(self):
        provider = ScriptedProvider([ProviderOverloadedError("upstream down")])
        loop = AgentLoop(dependencies(provider))

        await run_turn(loop)

        self.assertEqual(provider.call_count, 1)


class _TrimmingContextWindow:
    """A context-window port that keeps only the newest message."""

    def __init__(self) -> None:
        self.seen: List[int] = []

    async def relieve(
        self, messages: Sequence[ProviderMessage], *, model: str
    ) -> ContextRelief:
        self.seen.append(len(messages))
        if len(messages) <= 1:
            return ContextRelief(messages=list(messages))
        kept = list(messages)[-1:]
        return ContextRelief(
            messages=kept,
            events=(
                ContextTrimmedEvent(
                    trimmed_count=len(messages) - len(kept), remaining_messages=len(kept)
                ),
            ),
        )


class ContextWindowPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_port_reshapes_the_history_and_its_event_reaches_the_stream(self):
        tool = RecordingTool("read_file", result={"success": True})
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "read_file", path="/a")),
                text_generation("gen-2", "done"),
            ]
        )
        window = _TrimmingContextWindow()
        loop = AgentLoop(dependencies(provider, [tool], context_window=window))

        events = await run_turn(loop)

        self.assertEqual(window.seen, [1, 3])
        trimmed = first_of(events, EventType.CONTEXT_TRIMMED)
        self.assertEqual(trimmed.trimmed_count, 2)
        self.assertEqual(len(provider.requests[1].messages), 1)

    async def test_no_port_leaves_the_history_untouched(self):
        provider = ScriptedProvider([text_generation("gen-1", "hi")])
        loop = AgentLoop(dependencies(provider))

        events = await run_turn(loop)

        self.assertEqual(all_of(events, EventType.CONTEXT_TRIMMED), [])
        self.assertEqual(len(provider.requests[0].messages), 1)


class _HalvingCostAccountant:
    """A cost accountant that splits a reported cost evenly."""

    def account(
        self, *, model: str, usage: Usage, reported_cost: Optional[float]
    ) -> CostBreakdown:
        total = reported_cost or 0.0
        return CostBreakdown(total=total, prompt=total / 2, completion=total / 2)


class CostAccountantPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_port_splits_the_cost_on_the_usage_and_done_events(self):
        provider = ScriptedProvider(
            [
                text_generation(
                    "gen-1",
                    "hi",
                    usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            ]
        )
        loop = AgentLoop(dependencies(provider, cost_accountant=_HalvingCostAccountant()))

        events = await run_turn(loop)

        update = first_of(events, EventType.USAGE_UPDATE)
        self.assertEqual((update.cost, update.prompt_cost, update.completion_cost),
                         (0.001, 0.0005, 0.0005))
        done = first_of(events, EventType.DONE)
        self.assertEqual((done.prompt_cost, done.completion_cost), (0.0005, 0.0005))

    async def test_the_default_reports_the_provider_total_and_no_split(self):
        provider = ScriptedProvider(
            [
                text_generation(
                    "gen-1",
                    "hi",
                    usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            ]
        )
        loop = AgentLoop(dependencies(provider))

        done = first_of(await run_turn(loop), EventType.DONE)

        self.assertEqual((done.cost, done.prompt_cost, done.completion_cost), (0.001, 0.0, 0.0))


class _PreviewDerivation:
    """A derivation port that turns a tool's port number into an event."""

    def derive(self, call: ToolCall, result: JsonDict) -> Sequence[StreamEvent]:
        port = result.get("port")
        if port is None:
            return ()
        return (PreviewStartedEvent(port=int(port), command=result.get("command"), pid=None),)


class ToolResultEventsPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_derived_event_follows_the_executed_event(self):
        tool = RecordingTool(
            "start_preview", result={"success": True, "port": 5173, "command": "pnpm dev"}
        )
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "start_preview")),
                text_generation("gen-2", "running"),
            ]
        )
        loop = AgentLoop(
            dependencies(provider, [tool], tool_result_events=_PreviewDerivation())
        )

        events = await run_turn(loop)

        preview = first_of(events, EventType.PREVIEW_STARTED)
        self.assertEqual(preview.port, 5173)
        self.assertGreater(
            events.index(preview), events.index(first_of(events, EventType.FILE_TOOL_EXECUTED))
        )


class HeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_slow_tool_call_keeps_the_stream_alive(self):
        tool = RecordingTool("slow", delay_seconds=0.05)
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "slow")),
                text_generation("gen-2", "done"),
            ]
        )
        loop = AgentLoop(
            dependencies(
                provider,
                [tool],
                config=AgentTurnConfig(
                    model=FIXTURE_MODEL, heartbeat_interval_seconds=0.01
                ),
            )
        )

        events = await run_turn(loop)

        heartbeats = all_of(events, EventType.HEARTBEAT)
        self.assertGreaterEqual(len(heartbeats), 2)
        self.assertEqual({beat.tool for beat in heartbeats}, {"slow"})

    async def test_no_heartbeats_are_emitted_when_the_interval_is_disabled(self):
        tool = RecordingTool("fast")
        provider = ScriptedProvider(
            [
                tool_call_generation("gen-1", tool_call("call-1", "fast")),
                text_generation("gen-2", "done"),
            ]
        )
        loop = AgentLoop(dependencies(provider, [tool]))

        events = await run_turn(loop)

        self.assertEqual(all_of(events, EventType.HEARTBEAT), [])


if __name__ == "__main__":
    unittest.main()
