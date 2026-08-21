"""Characterization tests for `LangChainStreamingAgent.astream_chat`'s
LangChain/ChatOpenAI streaming path (as opposed to
`_astream_with_direct_client`, covered in test_direct_client_stream.py).

`self.llm_with_tools` is replaced with a `FakeStreamingLLM` so no
network call happens; `tool_call_chunks` accumulation (the OpenRouter
streaming tool-call format) and the resulting SSE event shapes are
exercised end-to-end through the real method.

Kept intentionally smaller than the direct-client suite (per delegating
task guidance) -- the accumulation/dispatch/billing invariants are
identical between the two paths (they share `extract_billable_tool_costs`
and the same done/usage_update field set); this file exists to confirm
the LangChain-specific chunk-accumulation mechanics don't diverge.
"""

from unittest.mock import AsyncMock, patch

from django.test import TestCase

from llm.tests.conftest import (
    FakeChunk,
    FakeStreamingLLM,
    FakeTool,
    drain,
    make_agent,
)


def _tcc(index, call_id=None, name="", args=""):
    """One raw `tool_call_chunks` entry (dict shape, as OpenRouter sends)."""
    d = {"index": index, "args": args}
    if call_id:
        d["id"] = call_id
    if name:
        d["name"] = name
    return d


def _patch_pricing_unavailable():
    return patch(
        "llm.langchain_agent.CatalogService.get_model_pricing",
        side_effect=RuntimeError("no pricing in test"),
    )


def _patch_no_sleep():
    """astream_chat sleeps 1s between detecting tool calls and executing
    them (a UI cancel window) -- irrelevant to what we're characterizing."""
    return patch("llm.langchain_agent.asyncio.sleep", new=AsyncMock())


class LangchainPathStreamTests(TestCase):

    def _run(self, agent, **kwargs):
        params = dict(
            messages=[{"role": "user", "content": "hi"}],
            user_id=None,
            conversation_id="c1",
            chat_id="chat1",
            auth_token="tok",
        )
        params.update(kwargs)
        return drain(agent.astream_chat(**params))

    def test_plain_completion_emits_done_with_full_field_set(self):
        agent = make_agent()
        agent._user_id = None
        agent.llm_with_tools = FakeStreamingLLM(
            [FakeChunk(content="hello"), FakeChunk(usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14})],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        expected_keys = {
            "model", "finish_reason", "usage", "cost", "prompt_cost",
            "completion_cost", "tool_cost", "generation_id", "generation_ids",
        }
        self.assertTrue(expected_keys.issubset(done_data.keys()))
        self.assertEqual(done_data["finish_reason"], "stop")
        self.assertEqual(done_data["usage"]["prompt_tokens"], 10)
        self.assertEqual(done_data["tool_cost"], 0.0)
        self.assertEqual(done_data["generation_ids"], [])

    def test_generation_id_from_response_metadata_reaches_done(self):
        agent = make_agent()
        agent._user_id = None
        agent.llm_with_tools = FakeStreamingLLM(
            [
                FakeChunk(content="hi", response_metadata={"openrouter_generation_id": "gen-xyz"}),
                FakeChunk(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}),
            ],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        # Forwarded immediately as its own event...
        gen_events = [e for e in events if e["event"] == "generation_id"]
        self.assertEqual(gen_events[0]["data"]["generation_id"], "gen-xyz")
        # ...and present in the final done event.
        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertEqual(done_data["generation_id"], "gen-xyz")
        self.assertEqual(done_data["generation_ids"], ["gen-xyz"])

    def test_tool_call_chunks_accumulate_by_index_across_fragments(self):
        """OpenRouter streams tool-call args in fragments; the agent must
        accumulate them by `index` (not `id`, which only appears once)."""
        seen_args = {}

        def _capture(args):
            seen_args.update(args)
            return {"success": True}

        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("search_thing", _capture)]
        agent.llm_with_tools = FakeStreamingLLM(
            [
                FakeChunk(tool_call_chunks=[_tcc(0, call_id="call_1", name="search_thing", args='{"q"')]),
                FakeChunk(tool_call_chunks=[_tcc(0, args=': "cats"}')]),
                FakeChunk(usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}),
            ],
            [FakeChunk(content="done"), FakeChunk(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})],
        )
        with _patch_pricing_unavailable(), _patch_no_sleep():
            self._run(agent)

        self.assertEqual(seen_args, {"q": "cats"})

    def test_unknown_tool_name_reports_not_found_and_loop_continues(self):
        agent = make_agent()
        agent._user_id = None
        agent.tools = []
        agent.llm_with_tools = FakeStreamingLLM(
            [
                FakeChunk(tool_call_chunks=[_tcc(0, call_id="call_1", name="ghost_tool", args="{}")]),
                FakeChunk(usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}),
            ],
            [FakeChunk(content="ok"), FakeChunk(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})],
        )
        with _patch_pricing_unavailable(), _patch_no_sleep():
            events = self._run(agent)

        executed = [e for e in events if e["event"] == "file_tool_executed"][0]
        result = executed["data"]["results"][0]
        self.assertFalse(result["success"])
        self.assertIn("not found", result["result"]["error"])
        self.assertEqual([e["event"] for e in events][-1], "done")

    def test_tool_exception_is_caught_and_loop_continues(self):
        def _boom(_args):
            raise ValueError("kaboom")

        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("explode", _boom)]
        agent.llm_with_tools = FakeStreamingLLM(
            [
                FakeChunk(tool_call_chunks=[_tcc(0, call_id="call_1", name="explode", args="{}")]),
                FakeChunk(usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}),
            ],
            [FakeChunk(content="ok"), FakeChunk(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})],
        )
        with _patch_pricing_unavailable(), _patch_no_sleep():
            events = self._run(agent)

        executed = [e for e in events if e["event"] == "file_tool_executed"][0]
        result = executed["data"]["results"][0]
        self.assertFalse(result["success"])
        self.assertEqual(result["result"]["error"], "kaboom")

    def test_coding_agent_cost_usd_excluded_from_tool_cost(self):
        """Priority #1 parity check with the direct-client path: same
        dedup rule applies via the shared `extract_billable_tool_costs`."""
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("coding_agent", {"success": True, "cost_usd": 7.0, "summary": "ok"})]
        agent.llm_with_tools = FakeStreamingLLM(
            [
                FakeChunk(tool_call_chunks=[_tcc(0, call_id="call_1", name="coding_agent", args="{}")]),
                FakeChunk(usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}),
            ],
            [FakeChunk(content="ok"), FakeChunk(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})],
        )
        with _patch_pricing_unavailable(), _patch_no_sleep():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertEqual(done_data["tool_cost"], 0.0)

    def test_priced_tool_cost_lands_in_done_tool_cost(self):
        agent = make_agent()
        agent._user_id = None
        agent.tools = [FakeTool("priced_tool", {"success": True, "cost_usd": 0.33})]
        agent.llm_with_tools = FakeStreamingLLM(
            [
                FakeChunk(tool_call_chunks=[_tcc(0, call_id="call_1", name="priced_tool", args="{}")]),
                FakeChunk(usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}),
            ],
            [FakeChunk(content="ok"), FakeChunk(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})],
        )
        with _patch_pricing_unavailable(), _patch_no_sleep():
            events = self._run(agent)

        done_data = [e for e in events if e["event"] == "done"][0]["data"]
        self.assertAlmostEqual(done_data["tool_cost"], 0.33)

    def test_content_delta_event_is_rewrapped_from_chunk_content(self):
        """Unlike the direct-client path (which forwards an already-built
        SSE dict verbatim), astream_chat builds the `content` event itself
        from `chunk.content` on a LangChain message chunk."""
        agent = make_agent()
        agent._user_id = None
        agent.llm_with_tools = FakeStreamingLLM(
            [FakeChunk(content="hello world"), FakeChunk(usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        content_events = [e for e in events if e["event"] == "content"]
        self.assertEqual(content_events, [{"event": "content", "data": {"content": "hello world"}}])

    def test_usage_update_event_shape(self):
        agent = make_agent()
        agent._user_id = None
        agent.llm_with_tools = FakeStreamingLLM(
            [FakeChunk(content="hi"), FakeChunk(usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5})],
        )
        with _patch_pricing_unavailable():
            events = self._run(agent)

        usage_updates = [e for e in events if e["event"] == "usage_update"]
        self.assertEqual(len(usage_updates), 1)
        expected_keys = {
            "usage", "cost", "prompt_cost", "completion_cost",
            "generation_id", "generation_ids",
        }
        self.assertEqual(expected_keys, set(usage_updates[0]["data"].keys()))
