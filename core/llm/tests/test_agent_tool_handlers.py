"""Characterization tests for llm/agent_tool_handlers.py.

Covers (see priority #5 in the delegating task):
  - `_resolve_workspace_chat_id`: the ClonedRepository lookup that
    routes coding-agent tools to the chat where a repo was actually
    cloned.
  - `FileToolsContext._make_request`: HTTP error paths, including the
    `httpx.ReadTimeout` empty-str() gotcha (str(exc) == "" for a bare
    timeout with no message).
  - Context registry (`set_file_tools_context` / `_get_context` /
    `clear_file_tools_context`): the ContextVar + dict-based isolation,
    and its single-context fallback.
  - `coding_agent`'s top-level `cost_usd` propagation (priority #1
    crown jewel, at the tool layer this time -- test_direct_client_stream.py
    covers the agent-loop-layer exclusion of the same cost).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase

from llm.agent_tool_handlers import (
    FileToolsContext,
    _get_context,
    _resolve_workspace_chat_id,
    clear_file_tools_context,
    coding_agent,
    set_file_tools_context,
)


def _run(coro):
    return async_to_sync(lambda: coro)()


def _make_context(**overrides):
    defaults = dict(
        user_id="user-1",
        conversation_id="conv-1",
        chat_id="chat-1",
        auth_token="tok",
    )
    defaults.update(overrides)
    return FileToolsContext(**defaults)


class ResolveWorkspaceChatIdTests(SimpleTestCase):

    def test_cached_value_short_circuits_without_db_lookup(self):
        context = _make_context()
        context.workspace_chat_id = "cached-chat"
        with patch("code_sessions.models.ClonedRepository.objects.filter") as mock_filter:
            result = _run(_resolve_workspace_chat_id(context))
        self.assertEqual(result, "cached-chat")
        mock_filter.assert_not_called()

    def test_matching_workspace_path_returns_clone_chat_id(self):
        context = _make_context(chat_id="active-chat")
        cloned = MagicMock(workspace_path="/workspace/chat-clone-99/repo")
        with patch("code_sessions.models.ClonedRepository.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = cloned
            result = _run(_resolve_workspace_chat_id(context))
        self.assertEqual(result, "clone-99")
        self.assertEqual(context.workspace_chat_id, "clone-99")

    def test_workspace_path_matching_active_chat_id_returns_it(self):
        context = _make_context(chat_id="same-chat")
        cloned = MagicMock(workspace_path="/workspace/chat-same-chat/repo")
        with patch("code_sessions.models.ClonedRepository.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = cloned
            result = _run(_resolve_workspace_chat_id(context))
        self.assertEqual(result, "same-chat")

    def test_non_matching_workspace_path_falls_back_to_chat_id(self):
        context = _make_context(chat_id="active-chat")
        cloned = MagicMock(workspace_path="/some/other/unrelated/path")
        with patch("code_sessions.models.ClonedRepository.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = cloned
            result = _run(_resolve_workspace_chat_id(context))
        self.assertEqual(result, "active-chat")
        self.assertEqual(context.workspace_chat_id, "active-chat")

    def test_no_cloned_repository_falls_back_to_chat_id(self):
        context = _make_context(chat_id="active-chat")
        with patch("code_sessions.models.ClonedRepository.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = None
            result = _run(_resolve_workspace_chat_id(context))
        self.assertEqual(result, "active-chat")

    def test_db_exception_falls_back_to_chat_id_without_raising(self):
        context = _make_context(chat_id="active-chat")
        with patch("code_sessions.models.ClonedRepository.objects.filter", side_effect=RuntimeError("db down")):
            result = _run(_resolve_workspace_chat_id(context))
        self.assertEqual(result, "active-chat")
        self.assertEqual(context.workspace_chat_id, "active-chat")


class FileToolsContextMakeRequestTests(SimpleTestCase):

    def test_successful_request_returns_parsed_json(self):
        context = _make_context()
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"success": True, "files": []}
        fake_client = MagicMock()
        fake_client.post = AsyncMock(return_value=fake_response)
        context._http_client = fake_client

        result = _run(context._make_request("/fs/list", {"path": "/"}))
        self.assertEqual(result, {"success": True, "files": []})

    def test_read_timeout_with_empty_str_yields_empty_error_string(self):
        """httpx.ReadTimeout() with no message has str(exc) == '' -- the
        generic `except Exception as e: ... str(e)` handler must not
        crash, but the resulting error message is silently empty. This
        characterizes the known gotcha, it does not endorse it."""
        context = _make_context()
        fake_client = MagicMock()
        fake_client.post = AsyncMock(side_effect=httpx.ReadTimeout(""))
        context._http_client = fake_client

        result = _run(context._make_request("/fs/read", {"path": "x"}))
        self.assertEqual(result, {"success": False, "error": ""})

    def test_generic_exception_message_is_preserved(self):
        context = _make_context()
        fake_client = MagicMock()
        fake_client.post = AsyncMock(side_effect=RuntimeError("orchestrator unreachable"))
        context._http_client = fake_client

        result = _run(context._make_request("/fs/write", {"path": "x", "content": "y"}))
        self.assertEqual(result, {"success": False, "error": "orchestrator unreachable"})

    def test_http_status_error_message_is_preserved(self):
        context = _make_context()
        response = httpx.Response(status_code=500, request=httpx.Request("POST", "http://x/fs/list"))
        fake_client = MagicMock()
        fake_client.post = AsyncMock(return_value=response)
        context._http_client = fake_client

        result = _run(context._make_request("/fs/list", {"path": "/"}))
        self.assertFalse(result["success"])
        self.assertIn("500", result["error"])

    def test_cancelled_before_start_skips_the_http_call_entirely(self):
        context = _make_context(is_cancelled_callback=lambda: True)
        fake_client = MagicMock()
        fake_client.post = AsyncMock()
        context._http_client = fake_client

        result = _run(context._make_request("/fs/list", {"path": "/"}))
        self.assertEqual(result, {"success": False, "error": "Operation cancelled by user"})
        fake_client.post.assert_not_called()


class ContextRegistryTests(TestCase):

    def setUp(self):
        self._keys_to_clear = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for key in self._keys_to_clear:
            clear_file_tools_context(key)

    def _register(self, context):
        key = set_file_tools_context(context)
        self._keys_to_clear.append(key)
        return key

    def test_set_and_get_context_roundtrip(self):
        context = _make_context(user_id="u1", conversation_id="c1", chat_id="ch1")
        self._register(context)
        self.assertIs(_get_context(), context)

    def test_clear_removes_context_from_registry(self):
        context = _make_context(user_id="u2", conversation_id="c2", chat_id="ch2")
        key = self._register(context)
        clear_file_tools_context(key)
        self._keys_to_clear.remove(key)
        # No contextvar, no other contexts registered -> None.
        self.assertIsNone(_get_context())

    def test_single_remaining_context_is_used_as_fallback(self):
        """When the contextvar is unset (e.g. a different asyncio task)
        but exactly one context is registered, _get_context falls back
        to it rather than returning None."""
        context = _make_context(user_id="u3", conversation_id="c3", chat_id="ch3")
        self._register(context)

        import contextvars
        from llm import agent_tool_handlers as module

        # Simulate a task that never called set_file_tools_context.
        def _in_fresh_context():
            module._current_context_key.set(None)
            return _get_context()

        ctx = contextvars.copy_context()
        result = ctx.run(_in_fresh_context)
        self.assertIs(result, context)


class CodingAgentToolCostUsdTests(TestCase):
    """Priority #1: cost_usd must always surface at the top level of the
    coding_agent tool's JSON return, on both success and failure, so
    `agent.cost_ledger.extract_billable_tool_costs`'s exclusion logic
    has something consistent to exclude."""

    def setUp(self):
        self.context = _make_context(api_key="sk-or-test", model_id="anthropic/claude-sonnet-4")
        self.key = set_file_tools_context(self.context)
        self.addCleanup(clear_file_tools_context, self.key)

        self._patches = [
            patch("llm.agent_tool_handlers.check_code_session_budget", new=AsyncMock(return_value=(None, None))),
            patch("llm.agent_tool_handlers._resolve_workspace_chat_id", new=AsyncMock(return_value="chat-1")),
            patch("llm.agent_tool_handlers._ensure_repo_in_sandbox", new=AsyncMock(return_value=None)),
            patch("llm.agent_tool_handlers._fetch_user_sub_agents", new=AsyncMock(return_value=([], []))),
            patch("llm.agent_tool_handlers._fetch_user_model_preferences", new=AsyncMock(return_value={
                "fast_model_id": "m", "balanced_model_id": "m", "powerful_model_id": "m",
            })),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def test_success_path_surfaces_cost_usd_and_bills_code_session(self):
        execute_result = {
            "success": True,
            "job_id": "job-1",
            "status": "completed",
            "result": {
                "total_cost_usd": 0.42,
                "summary": "Implemented the thing",
                "files_modified": ["a.py"],
                "files_created": [],
            },
            "steps": [],
            "duration_ms": 1200,
        }
        with patch("llm.services.execute_coding_agent", new=AsyncMock(return_value=execute_result)), \
             patch("llm.services.coding_agent_billing.bill_code_session", new=AsyncMock()) as mock_bill:
            raw = _run(coding_agent.ainvoke({"task": "do the thing"}))

        payload = json.loads(raw)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["cost_usd"], 0.42)
        mock_bill.assert_awaited_once()
        _, called_cost, called_model, called_session, called_request_id = mock_bill.await_args.args
        self.assertEqual(called_cost, 0.42)
        self.assertEqual(called_request_id, "job-1")

    def test_failure_path_still_surfaces_cost_usd(self):
        """A partially-billable failed run (agent burned tokens before
        erroring) must still report cost_usd so it isn't silently lost."""
        execute_result = {
            "success": False,
            "job_id": "job-2",
            "status": "failed",
            "error": "agent crashed",
            "result": {"total_cost_usd": 0.11},
        }
        with patch("llm.services.execute_coding_agent", new=AsyncMock(return_value=execute_result)), \
             patch("llm.services.coding_agent_billing.bill_code_session", new=AsyncMock()) as mock_bill:
            raw = _run(coding_agent.ainvoke({"task": "do the thing"}))

        payload = json.loads(raw)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["cost_usd"], 0.11)
        mock_bill.assert_awaited_once()

    def test_zero_cost_result_still_calls_bill_code_session_with_zero(self):
        execute_result = {
            "success": True,
            "job_id": "job-3",
            "status": "completed",
            "result": {"total_cost_usd": 0.0, "summary": "no-op"},
        }
        with patch("llm.services.execute_coding_agent", new=AsyncMock(return_value=execute_result)), \
             patch("llm.services.coding_agent_billing.bill_code_session", new=AsyncMock()) as mock_bill:
            raw = _run(coding_agent.ainvoke({"task": "do nothing"}))

        payload = json.loads(raw)
        self.assertEqual(payload["cost_usd"], 0.0)
        mock_bill.assert_awaited_once()


class CodingAgentToolGuardTests(TestCase):
    """Early-exit guards that must short-circuit before any network/DB call."""

    def test_missing_context_returns_error_without_cost_usd(self):
        # `_get_context()` has a single-remaining-context fallback (see
        # ContextRegistryTests) -- patch it directly rather than relying
        # on the module-global `_contexts` dict being empty, which is
        # not guaranteed when the full suite runs (other tests/views can
        # leave exactly one context registered).
        with patch("llm.agent_tool_handlers._get_context", return_value=None):
            raw = _run(coding_agent.ainvoke({"task": "do the thing"}))
        payload = json.loads(raw)
        self.assertFalse(payload["success"])
        self.assertIn("not initialized", payload["error"])
        self.assertNotIn("cost_usd", payload)

    def test_empty_task_is_rejected(self):
        context = _make_context()
        key = set_file_tools_context(context)
        self.addCleanup(clear_file_tools_context, key)

        raw = _run(coding_agent.ainvoke({"task": ""}))
        payload = json.loads(raw)
        self.assertFalse(payload["success"])
        self.assertIn("Task description is required", payload["error"])

    def test_tier_gate_denial_short_circuits_before_execution(self):
        context = _make_context()
        key = set_file_tools_context(context)
        self.addCleanup(clear_file_tools_context, key)

        denial = json.dumps({"success": False, "error_type": "QUOTA_EXCEEDED", "message": "no more code sessions"})
        with patch("llm.agent_tool_handlers.check_code_session_budget", new=AsyncMock(return_value=(denial, None))), \
             patch("llm.services.execute_coding_agent", new=AsyncMock()) as mock_execute:
            raw = _run(coding_agent.ainvoke({"task": "do the thing"}))

        self.assertEqual(raw, denial)
        mock_execute.assert_not_called()
