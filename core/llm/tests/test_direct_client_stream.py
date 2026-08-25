"""Characterization tests for `LangChainStreamingAgent._astream_with_direct_client`.

This is the crown jewel per the task brief: the manual agent loop that
streams from `OpenRouterClient.complete_stream` (mocked here as a sync
generator, matching how it's actually invoked -- run in a worker
thread), executes tool calls, and emits the SSE events the frontend
consumes.

Covered (see priorities in the delegating task):
  1. Tool-cost accumulation into `accumulated_tool_cost` and its
     appearance in `usage_update` / `done` events -- including the
     coding-agent exclusion (billed separately, never re-added here).
  2. `all_generation_ids` accumulation across iterations, deduped, and
     mirrored into `usage_update.generation_ids` / `done.generation_ids`.
  3. Tool-call dispatch: unknown tool name, tool exceptions, malformed
     JSON arguments -- the loop must continue to the next tool call.
  4. SSE event shapes for file_tool_executing / file_tool_executed /
     usage_update / done.

`self._user_id = None` throughout (except where a test explicitly
documents otherwise) so no DB-backed billing/quota path executes --
these tests characterize the streaming/accumulation logic in
isolation from the UsageLog write path.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from llm.tests.conftest import (
    FakeTool,
    content_chunk,
    done_chunk,
    drain,
    generation_id_chunk,
    make_agent,
    make_billing_user,
    make_tool_call,
    seed_billing_plan,
    stream_sequence,
)


def _patch_pricing_unavailable():
    """`_calculate_costs` catches any exception from CatalogService and
    falls back to `(0.0, 0.0, tool_cost)` -- patching it to raise makes
    `done.cost` land exactly on the accumulated tool cost, which is the
    cleanest possible assertion for tool-cost-only characterization."""
    return patch(
        "llm.langchain_agent.CatalogService.get_model_pricing",
        side_effect=RuntimeError("no pricing in test"),
    )


class DirectClientStreamTests(TestCase):

    def _run(self, agent, **kwargs):
        params = dict(
            messages=[{"role": "user", "content": "hi"}],
            user_id="u1",
            conversation_id="c1",
            chat_id="chat1",
            auth_token="tok",
        )
        params.update(kwargs)
        return drain(agent._astream_with_direct_client(**params))

    # ---- no tool calls: single-iteration completion ----------------

    def test_plain_completion_emits_final_done_with_zero_cost(self):
        agent = make_agent()
        agent._user_id = None
        agent.direct_client.complete_stream = stream_sequence(
            [content_chunk("hello"), done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_events = [e for e in events if e["event"] == "done"]
        self.assertEqual(len(done_events), 1)
        data = done_events[0]["data"]
        self.assertEqual(data["finish_reason"], "stop")
        self.assertEqual(data["cost"], 0.0)
        self.assertEqual(data["tool_cost"], 0.0)
        self.assertEqual(data["generation_id"], None)
        self.assertEqual(data["generation_ids"], [])

    def test_generation_id_from_dedicated_event_reaches_done(self):
        agent = make_agent()
        agent._user_id = None
        agent.direct_client.complete_stream = stream_sequence(
            [generation_id_chunk("gen-abc"), content_chunk("hi"), done_chunk()],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertEqual(done_data["generation_id"], "gen-abc")
        self.assertEqual(done_data["generation_ids"], ["gen-abc"])

    def test_generation_id_from_done_chunk_also_captured(self):
        agent = make_agent()
        agent._user_id = None
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(generation_id="gen-from-done")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertEqual(done_data["generation_id"], "gen-from-done")
        self.assertEqual(done_data["generation_ids"], ["gen-from-done"])

    # ---- tool-call dispatch ------------------------------------------

    def test_unknown_tool_name_reports_not_found_and_loop_continues(self):
        agent = make_agent()
        agent._user_id = None
        agent.tools = []  # no tool named "ghost_tool" registered
        tc = make_tool_call("call_1", "ghost_tool")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        executed = [e for e in events if e["event"] == "file_tool_executed"][0]
        result = executed["data"]["results"][0]
        self.assertFalse(result["success"])
        self.assertEqual(result["result"]["error"], "Tool ghost_tool not found")
        # Loop kept going and reached a final done.
        self.assertEqual([e["event"] for e in events][-1], "done")

    def test_tool_exception_is_caught_and_loop_continues(self):
        agent = make_agent()
        agent._user_id = None

        def _boom(_args):
            raise ValueError("kaboom")

        agent.tools = [FakeTool("explode", _boom)]
        tc = make_tool_call("call_1", "explode")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        executed = [e for e in events if e["event"] == "file_tool_executed"][0]
        result = executed["data"]["results"][0]
        self.assertFalse(result["success"])
        self.assertEqual(result["result"]["error"], "kaboom")
        self.assertEqual([e["event"] for e in events][-1], "done")

    def test_malformed_json_arguments_are_caught_as_tool_failure(self):
        """Args string that isn't valid JSON blows up at json.loads() and
        is caught by the per-tool-call except -- NOT the tool itself."""
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("well_behaved", {"success": True})]
        tc = make_tool_call("call_1", "well_behaved", arguments="{not valid json")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        executed = [e for e in events if e["event"] == "file_tool_executed"][0]
        result = executed["data"]["results"][0]
        self.assertFalse(result["success"])
        self.assertIn("error", result["result"])

    def test_empty_arguments_string_defaults_to_empty_dict(self):
        calls = []

        def _capture(args):
            calls.append(args)
            return {"success": True}

        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("well_behaved", _capture)]
        tc = make_tool_call("call_1", "well_behaved", arguments="")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            self._run(agent)

        # Invoked exactly once, with the empty-string args coerced to {}.
        self.assertEqual(calls, [{}])

    def test_two_unrelated_tool_calls_one_fails_one_succeeds(self):
        """A failure in one tool call must not prevent the sibling call
        (same iteration) from executing and returning its own result."""
        agent = make_agent()
        agent._user_id = None

        def _boom(_args):
            raise RuntimeError("first tool broke")

        agent.tools = [FakeTool("bad_tool", _boom), FakeTool("good_tool", {"success": True, "value": 42})]
        calls = [make_tool_call("c1", "bad_tool"), make_tool_call("c2", "good_tool")]
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=calls)],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        executed = [e for e in events if e["event"] == "file_tool_executed"][0]
        results = executed["data"]["results"]
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0]["success"])
        self.assertTrue(results[1]["success"])
        self.assertEqual(results[1]["result"]["value"], 42)

    # ---- tool-cost accumulation ---------------------------------------

    def test_plain_tool_cost_usd_lands_in_done_tool_cost(self):
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("priced_tool", {"success": True, "cost_usd": 0.25})]
        tc = make_tool_call("c1", "priced_tool")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertAlmostEqual(done_data["tool_cost"], 0.25)
        self.assertAlmostEqual(done_data["cost"], 0.25)  # pricing patched to raise -> cost == tool_cost

    def test_coding_agent_cost_usd_excluded_from_tool_cost(self):
        """Priority #1 crown jewel: a tool literally named 'coding_agent'
        that returns a top-level cost_usd must NOT contribute to
        accumulated_tool_cost / done.tool_cost -- it is billed
        separately as a CODE_SESSION UsageLog row by
        agent_tool_handlers._bill_code_session."""
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("coding_agent", {"success": True, "cost_usd": 4.20, "summary": "done"})]
        tc = make_tool_call("c1", "coding_agent")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertEqual(done_data["tool_cost"], 0.0)
        self.assertEqual(done_data["cost"], 0.0)

    def test_tool_cost_appears_in_usage_update_of_the_next_iteration(self):
        """usage_update is emitted from the per-iteration inner `done`
        chunk, which is processed BEFORE that iteration's own tool calls
        run. So a tool's cost_usd only shows up in the usage_update of
        the iteration AFTER the one that executed it -- and in the final
        SSE `done` at loop end. This test pins down that lag exactly."""
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("priced_tool", {"success": True, "cost_usd": 0.5})]
        tc = make_tool_call("c1", "priced_tool")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        usage_updates = [e for e in events if e["event"] == "usage_update"]
        self.assertEqual(len(usage_updates), 2)
        # Iteration 1's usage_update fires before priced_tool has run.
        self.assertEqual(usage_updates[0]["data"]["cost"], 0.0)
        # Iteration 2's usage_update reflects the now-accumulated tool cost.
        self.assertAlmostEqual(usage_updates[1]["data"]["cost"], 0.5)
        # And the final done event agrees.
        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertAlmostEqual(done_data["tool_cost"], 0.5)

    def test_multiple_tool_calls_same_iteration_sum_into_tool_cost(self):
        agent = make_agent()
        agent._user_id = None
        agent.tools = [
            FakeTool("tool_a", {"success": True, "cost_usd": 0.10}),
            FakeTool("tool_b", {"success": True, "cost_usd": 0.20}),
        ]
        calls = [make_tool_call("c1", "tool_a"), make_tool_call("c2", "tool_b")]
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=calls)],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertAlmostEqual(done_data["tool_cost"], 0.30)

    # ---- generation-id accumulation across iterations ------------------

    def test_generation_ids_accumulate_across_iterations_without_duplicates(self):
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("noop_tool", {"success": True})]
        tc = make_tool_call("c1", "noop_tool")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc], generation_id="gen-1")],
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc], generation_id="gen-1")],  # repeat on purpose
            [done_chunk(finish_reason="stop", generation_id="gen-2")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertEqual(done_data["generation_ids"], ["gen-1", "gen-2"])
        self.assertEqual(done_data["generation_id"], "gen-2")
        # And self.all_generation_ids (read by the view's abort-settlement
        # handler) is kept in sync with the same list.
        self.assertEqual(agent.all_generation_ids, ["gen-1", "gen-2"])

    # ---- mid-stream error / cancellation --------------------------------

    def test_error_event_is_forwarded_and_stream_stops(self):
        agent = make_agent()
        agent._user_id = None
        agent.direct_client.complete_stream = stream_sequence(
            [content_chunk("partial"), {"event": "error", "data": {"error": "upstream exploded"}}],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        self.assertEqual(events[-1]["event"], "error")
        self.assertEqual(events[-1]["data"]["error"], "upstream exploded")
        # No final `done` was emitted after the error.
        self.assertNotIn("done", [e["event"] for e in events])

    def test_cancelled_before_start_emits_immediate_done(self):
        agent = make_agent()
        agent._user_id = None
        agent.is_cancelled = True
        # complete_stream should never even be consulted.
        agent.direct_client.complete_stream = stream_sequence([done_chunk()])

        events = self._run(agent)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "done")
        self.assertEqual(events[0]["data"]["finish_reason"], "cancelled")
        self.assertEqual(events[0]["data"]["cost"], 0)

    # ---- extended-search per-message limit ------------------------------

    def test_extended_search_limit_blocks_without_invoking_tool(self):
        from llm.constants import MAX_EXTENDED_SEARCHES_PER_MESSAGE

        agent = make_agent()
        agent._user_id = None
        agent._extended_search_count = MAX_EXTENDED_SEARCHES_PER_MESSAGE
        invoked = []
        agent.tools = [FakeTool("brave_web_search", lambda a: invoked.append(a) or {"success": True})]
        tc = make_tool_call("c1", "brave_web_search")
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        executed = [e for e in events if e["event"] == "file_tool_executed"][0]
        result = executed["data"]["results"][0]
        self.assertFalse(result["success"])
        self.assertIn("Extended Search limit reached", result["result"]["error"])
        self.assertEqual(invoked, [])  # tool.ainvoke never called

    # ---- SSE event shapes -------------------------------------------------

    def test_content_delta_event_forwarded_verbatim(self):
        """The direct-client path forwards `content` chunks exactly as
        client.py emitted them -- no re-wrapping."""
        agent = make_agent()
        agent._user_id = None
        agent.direct_client.complete_stream = stream_sequence(
            [content_chunk("hello world"), done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        content_events = [e for e in events if e["event"] == "content"]
        self.assertEqual(content_events, [{"event": "content", "data": {"content": "hello world"}}])

    def test_file_tool_executing_event_shape(self):
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("noop_tool", {"success": True})]
        tc = make_tool_call("c1", "noop_tool", arguments='{"x": 1}')
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=[tc])],
            [done_chunk(finish_reason="stop")],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        executing = [e for e in events if e["event"] == "file_tool_executing"][0]
        self.assertEqual(set(executing["data"].keys()), {"tool_calls"})
        emitted_tc = executing["data"]["tool_calls"][0]
        self.assertEqual(emitted_tc["id"], "c1")
        self.assertEqual(emitted_tc["function"]["name"], "noop_tool")
        self.assertIn("display_name", emitted_tc)

    def test_done_event_contains_all_billing_fields(self):
        agent = make_agent()
        agent._user_id = None
        agent.direct_client.complete_stream = stream_sequence([done_chunk()])
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        expected_keys = {
            "model", "finish_reason", "usage", "cost", "prompt_cost",
            "completion_cost", "tool_cost", "generation_id", "generation_ids",
        }
        self.assertEqual(expected_keys, set(done_data.keys()))


class DirectClientRealBillingTests(TestCase):
    """Exercises the aggregate UsageLog write with a real user + active
    subscription -- this is where the image-gen dedup subtraction
    (`accumulated_tool_cost - image_gen_cost_in_bundle`) is actually
    observable, as opposed to just asserting on the raw `tool_cost`
    reported in the SSE `done` event."""

    @classmethod
    def setUpTestData(cls):
        cls.plan = seed_billing_plan()

    def _zero_pricing(self):
        """Deterministic LLM token cost of $0 so the UsageLog amount is
        exactly the billable tool cost, with no CatalogService lookup
        variance."""
        return patch(
            "llm.langchain_agent.CatalogService.get_model_pricing",
            return_value={"prompt_price": 0, "completion_price": 0},
        )

    def test_image_gen_cost_excluded_from_aggregate_usagelog_row(self):
        from usage_quota.models import FeatureType, ServiceType, UsageLog

        user = make_billing_user("direct-client-billing-1@test.local", self.plan)
        agent = make_agent()
        agent._user_id = str(user.id)
        agent.tools = [
            FakeTool("generate_image", {"success": True, "cost_usd": 0.05}),
            FakeTool("web_fetch", {"success": True, "cost_usd": 0.10}),
        ]
        calls = [make_tool_call("c1", "generate_image"), make_tool_call("c2", "web_fetch")]
        agent.direct_client.complete_stream = stream_sequence(
            [done_chunk(finish_reason="tool_calls", tool_calls=calls)],
            [done_chunk(finish_reason="stop")],
        )

        with self._zero_pricing():
            events = drain(agent._astream_with_direct_client(
                messages=[{"role": "user", "content": "hi"}],
                user_id=str(user.id),
                conversation_id="c1",
                chat_id="chat1",
                auth_token="tok",
            ))

        # Raw event still reports the FULL tool cost (0.15) — the
        # frontend total must match what was already streamed.
        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertAlmostEqual(done_data["tool_cost"], 0.15)

        # But the aggregate UsageLog row excludes the image-gen dollars
        # (already billed per-image by image_tools._record_billing) —
        # only 0.10 should be recorded here.
        rows = UsageLog.objects.filter(user=user, service=ServiceType.OPENROUTER, feature=FeatureType.CHAT)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().cost_usd, Decimal("0.1"))

    def test_no_positive_tool_cost_writes_no_usagelog_row(self):
        """Asserts only that the aggregate tool-cost deduct doesn't fire
        when there's no tool cost to deduct. It does NOT assert that a
        plain chat turn bills nothing overall: the LLM token row is
        normally written by `OpenRouterClient._log_usage` inside
        `complete_stream`, which is mocked out here (see `stream_sequence`)
        and therefore never runs in this test."""
        from usage_quota.models import UsageLog

        user = make_billing_user("direct-client-billing-2@test.local", self.plan)
        agent = make_agent()
        agent._user_id = str(user.id)
        agent.direct_client.complete_stream = stream_sequence([done_chunk(finish_reason="stop")])

        with self._zero_pricing():
            drain(agent._astream_with_direct_client(
                messages=[{"role": "user", "content": "hi"}],
                user_id=str(user.id),
                conversation_id="c1",
                chat_id="chat1",
                auth_token="tok",
            ))

        self.assertEqual(UsageLog.objects.filter(user=user).count(), 0)
