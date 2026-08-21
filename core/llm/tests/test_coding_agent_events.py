"""Characterization tests for the `coding_agent_step` / `coding_agent_completed`
SSE event builders on LangChainStreamingAgent, and the progress-polling
short-circuit they depend on.

Priority #4 ("step" events) at the agent-loop layer: `_poll_coding_agent_progress`,
`_build_coding_agent_completed_event`, and `_enrich_coding_agent_result` are
plain dict-in/dict-out (the last two) or a narrowly-scoped async no-DB
call -- no streaming, no tool loop, no mocking of the LLM required.
"""

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from llm.tests.conftest import make_agent


def _run(coro):
    """Run a plain coroutine (not an async generator) synchronously."""
    return async_to_sync(lambda: coro)()


class BuildCodingAgentCompletedEventTests(SimpleTestCase):

    def test_uses_progress_fields_when_progress_present(self):
        agent = make_agent()
        result = {"success": True, "summary": "result summary", "files_modified": ["result.py"]}
        progress = {
            "summary": "progress summary",
            "files_modified": ["progress.py"],
            "files_created": ["new.py"],
            "total_tokens": 500,
            "steps": [{"type": "text", "content": "step 1"}],
        }
        event = agent._build_coding_agent_completed_event(result, progress, duration_ms=1234)

        self.assertEqual(event["event"], "coding_agent_completed")
        data = event["data"]
        self.assertTrue(data["success"])
        # result.get("summary") is truthy -> takes precedence over progress.
        self.assertEqual(data["summary"], "result summary")
        # files_modified/files_created/total_tokens/steps come from progress
        # when progress is present (regardless of what `result` carries).
        self.assertEqual(data["files_modified"], ["progress.py"])
        self.assertEqual(data["files_created"], ["new.py"])
        self.assertEqual(data["total_tokens"], 500)
        self.assertEqual(data["steps"], [{"type": "text", "content": "step 1"}])
        self.assertEqual(data["duration_ms"], 1234)

    def test_falls_back_to_result_fields_when_progress_is_none(self):
        agent = make_agent()
        result = {
            "success": False,
            "summary": None,
            "files_modified": ["a.py"],
            "files_created": ["b.py"],
        }
        event = agent._build_coding_agent_completed_event(result, progress=None, duration_ms=50)

        data = event["data"]
        self.assertFalse(data["success"])
        self.assertIsNone(data["summary"])
        self.assertEqual(data["files_modified"], ["a.py"])
        self.assertEqual(data["files_created"], ["b.py"])
        self.assertEqual(data["total_tokens"], 0)
        self.assertEqual(data["steps"], [])

    def test_missing_result_success_key_defaults_to_false(self):
        agent = make_agent()
        event = agent._build_coding_agent_completed_event({}, progress=None, duration_ms=0)
        self.assertFalse(event["data"]["success"])


class EnrichCodingAgentResultTests(SimpleTestCase):

    def test_progress_present_populates_coding_agent_data_including_cost(self):
        agent = make_agent()
        result = {"success": True, "summary": "s"}
        progress = {
            "steps": [{"type": "text"}],
            "total_tokens": 100,
            "total_cost_usd": 0.42,
            "files_created": ["x.py"],
            "files_modified": [],
            "summary": "progress summary",
        }
        enriched = agent._enrich_coding_agent_result(result, progress, duration_ms=999)

        # Mutates and returns the same dict.
        self.assertIs(enriched, result)
        cad = enriched["coding_agent_data"]
        self.assertEqual(cad["cost_usd"], 0.42)
        self.assertEqual(cad["duration_ms"], 999)
        self.assertEqual(cad["files_created"], ["x.py"])
        self.assertTrue(cad["success"])

    def test_progress_none_defaults_cost_usd_to_zero(self):
        agent = make_agent()
        result = {"success": True, "summary": "s", "files_modified": ["m.py"], "files_created": []}
        enriched = agent._enrich_coding_agent_result(result, progress=None, duration_ms=10)

        cad = enriched["coding_agent_data"]
        self.assertEqual(cad["cost_usd"], 0)
        self.assertEqual(cad["files_modified"], ["m.py"])
        self.assertEqual(cad["steps"], [])


class PollCodingAgentProgressTests(SimpleTestCase):

    def test_no_file_tools_context_short_circuits_without_network_call(self):
        """`file_tools_context` is None outside a real chat request (as in
        most of this test module's agents) -- the poll must degrade to a
        no-op tuple rather than attempting to reach the orchestrator."""
        agent = make_agent()
        self.assertIsNone(agent.file_tools_context)

        events, step_count, progress = _run(agent._poll_coding_agent_progress(3))

        self.assertEqual(events, [])
        self.assertEqual(step_count, 3)
        self.assertIsNone(progress)
