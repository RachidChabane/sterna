"""Additional branch coverage for
``code_sessions.services.clone.ensure_repo_in_sandbox`` (chat-id parsing,
already-present short circuit, branch fallback, restore/reconcile failure
tolerance, and the unexpected-exception path) plus the ``_execute_bash``
HTTP adapter it and ``clone_repository`` share.

The happy-path "no cloned repo" / "missing GitHub connection" cases live
in ``test_ensure_repo_in_sandbox.py``; this file covers what that one
doesn't. External I/O (the orchestrator's HTTP endpoints) is mocked at
the module's own adapter-seam functions/classes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from code_sessions.services.clone import _execute_bash, ensure_repo_in_sandbox


def _run(coro):
    return async_to_sync(lambda: coro)()


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class _RoutingFakeAsyncClient:
    """Routes ``client.post(url, ...)`` to a canned response/exception by
    matching the tail of the URL."""

    def __init__(self, responses_by_suffix):
        self._responses = responses_by_suffix

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **_kwargs):
        for suffix, response in self._responses.items():
            if url.endswith(suffix):
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"Unexpected POST to {url}")


def _client_factory(responses_by_suffix):
    def factory(*_args, **_kwargs):
        return _RoutingFakeAsyncClient(responses_by_suffix)

    return factory


def _fake_cloned_repo(**overrides):
    defaults = dict(
        workspace_path="/workspace/chat-chat-1/repo",
        full_name="owner/repo",
        current_branch="feature-x",
        default_branch="main",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class EnsureRepoInSandboxRoutingTests(SimpleTestCase):
    def test_unparseable_workspace_path_is_a_no_op_success(self):
        with patch(
            "code_sessions.services.clone._get_cloned_repo",
            new=AsyncMock(return_value=_fake_cloned_repo(workspace_path="/workspace/no-marker/repo")),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertEqual(result["action"], "none")
        self.assertTrue(result["success"])

    def test_repo_already_present_short_circuits(self):
        responses = {"/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": False})}

        with (
            patch(
                "code_sessions.services.clone._get_cloned_repo",
                new=AsyncMock(return_value=_fake_cloned_repo()),
            ),
            patch(
                "code_sessions.services.clone.clone_repository",
                new=AsyncMock(),
            ) as mock_clone,
            patch(
                "code_sessions.services.clone.httpx.AsyncClient",
                side_effect=_client_factory(responses),
            ),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertEqual(result, {"action": "none", "success": True, "message": "Repo already present"})
        mock_clone.assert_not_awaited()


class EnsureRepoInSandboxUnexpectedFailureTests(SimpleTestCase):
    def test_unexpected_exception_is_caught_and_reported(self):
        with patch(
            "code_sessions.services.clone._get_cloned_repo",
            new=AsyncMock(side_effect=RuntimeError("db connection lost")),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertEqual(result["action"], "none")
        self.assertFalse(result["success"])
        self.assertIn("db connection lost", result["error"])


class EnsureRepoInSandboxBranchFallbackTests(SimpleTestCase):
    def test_falls_back_to_default_branch_when_current_branch_clone_fails(self):
        responses = {
            "/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": True}),
            "/workspace/restore": _FakeResponse(200, {"files_synced": 0}),
            "/workspace/reconcile-git": _FakeResponse(
                200, {"committed": True, "branch": "main", "commit_sha": "fallbacksha"}
            ),
        }
        clone_results = [
            {"success": False, "error": "Branch not found"},  # feature-x fails
            {"success": True},  # main succeeds
        ]

        with (
            patch(
                "code_sessions.services.clone._get_cloned_repo",
                new=AsyncMock(return_value=_fake_cloned_repo()),
            ),
            patch(
                "code_sessions.services.clone._get_github_connection",
                new=AsyncMock(return_value=SimpleNamespace(access_token="gh-token")),
            ),
            patch(
                "code_sessions.services.clone.clone_repository",
                new=AsyncMock(side_effect=clone_results),
            ) as mock_clone,
            patch(
                "code_sessions.services.clone._update_cloned_repo_head",
                new=AsyncMock(),
            ),
            patch(
                "code_sessions.services.clone.httpx.AsyncClient",
                side_effect=_client_factory(responses),
            ),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertEqual(result["action"], "restored")
        self.assertTrue(result["success"])
        self.assertEqual(mock_clone.await_count, 2)
        # Second attempt must target the default branch.
        _, second_kwargs = mock_clone.await_args_list[1]
        self.assertEqual(second_kwargs["branch"], "main")

    def test_both_branches_failing_returns_typed_error(self):
        responses = {"/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": True})}
        clone_results = [
            {"success": False, "error": "Branch not found"},
            {"success": False, "error": "still failing"},
        ]

        with (
            patch(
                "code_sessions.services.clone._get_cloned_repo",
                new=AsyncMock(return_value=_fake_cloned_repo()),
            ),
            patch(
                "code_sessions.services.clone._get_github_connection",
                new=AsyncMock(return_value=SimpleNamespace(access_token="gh-token")),
            ),
            patch(
                "code_sessions.services.clone.clone_repository",
                new=AsyncMock(side_effect=clone_results),
            ) as mock_clone,
            patch(
                "code_sessions.services.clone.httpx.AsyncClient",
                side_effect=_client_factory(responses),
            ),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertEqual(result["action"], "none")
        self.assertFalse(result["success"])
        # "Re-clone failed: " is a recognized prefix that _sanitize_clone_error
        # strips, so the final message is the underlying cause alone.
        self.assertEqual(result["error"], "still failing")
        self.assertEqual(mock_clone.await_count, 2)

    def test_no_fallback_attempted_when_current_branch_is_already_default(self):
        responses = {"/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": True})}

        with (
            patch(
                "code_sessions.services.clone._get_cloned_repo",
                new=AsyncMock(
                    return_value=_fake_cloned_repo(current_branch="main", default_branch="main")
                ),
            ),
            patch(
                "code_sessions.services.clone._get_github_connection",
                new=AsyncMock(return_value=SimpleNamespace(access_token="gh-token")),
            ),
            patch(
                "code_sessions.services.clone.clone_repository",
                new=AsyncMock(return_value={"success": False, "error": "boom"}),
            ) as mock_clone,
            patch(
                "code_sessions.services.clone.httpx.AsyncClient",
                side_effect=_client_factory(responses),
            ),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertFalse(result["success"])
        mock_clone.assert_awaited_once()


class EnsureRepoInSandboxRestoreAndReconcileFailureTests(SimpleTestCase):
    def test_restore_step_exception_does_not_abort_reconciliation(self):
        responses = {
            "/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": True}),
            "/workspace/restore": ConnectionError("orchestrator unreachable"),
            "/workspace/reconcile-git": _FakeResponse(
                200, {"committed": True, "branch": "feature-x", "commit_sha": "sha-after-restore-fail"}
            ),
        }

        with (
            patch(
                "code_sessions.services.clone._get_cloned_repo",
                new=AsyncMock(return_value=_fake_cloned_repo()),
            ),
            patch(
                "code_sessions.services.clone._get_github_connection",
                new=AsyncMock(return_value=SimpleNamespace(access_token="gh-token")),
            ),
            patch(
                "code_sessions.services.clone.clone_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch(
                "code_sessions.services.clone._update_cloned_repo_head",
                new=AsyncMock(),
            ) as mock_update_head,
            patch(
                "code_sessions.services.clone.httpx.AsyncClient",
                side_effect=_client_factory(responses),
            ),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertEqual(result["action"], "restored")
        self.assertTrue(result["success"])
        self.assertEqual(result["commit_sha"], "sha-after-restore-fail")
        mock_update_head.assert_awaited_once_with("conv-1", "sha-after-restore-fail")

    def test_reconcile_step_exception_still_reports_restored_success(self):
        responses = {
            "/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": True}),
            "/workspace/restore": _FakeResponse(200, {"files_synced": 3}),
            "/workspace/reconcile-git": TimeoutError("orchestrator too slow"),
        }

        with (
            patch(
                "code_sessions.services.clone._get_cloned_repo",
                new=AsyncMock(return_value=_fake_cloned_repo()),
            ),
            patch(
                "code_sessions.services.clone._get_github_connection",
                new=AsyncMock(return_value=SimpleNamespace(access_token="gh-token")),
            ),
            patch(
                "code_sessions.services.clone.clone_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch(
                "code_sessions.services.clone._update_cloned_repo_head",
                new=AsyncMock(),
            ) as mock_update_head,
            patch(
                "code_sessions.services.clone.httpx.AsyncClient",
                side_effect=_client_factory(responses),
            ),
        ):
            result = _run(
                ensure_repo_in_sandbox(user_id="user-1", conversation_id="conv-1", auth_token="tok")
            )

        self.assertEqual(
            result,
            {
                "action": "restored",
                "success": True,
                "branch": "feature-x",
                "commit_sha": "",
                "committed": False,
            },
        )
        mock_update_head.assert_not_awaited()


# ---------------------------------------------------------------------------
# _execute_bash
# ---------------------------------------------------------------------------


class _SinglePostFakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, _url, **_kwargs):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class ExecuteBashTests(SimpleTestCase):
    def test_success_response_returns_parsed_json(self):
        response = _FakeResponse(200, {"success": True, "output": "ok"})
        with patch(
            "code_sessions.services.clone.httpx.AsyncClient",
            side_effect=lambda: _SinglePostFakeAsyncClient(response),
        ):
            result = _run(
                _execute_bash(
                    orchestrator_url="http://orchestrator",
                    auth_token="tok",
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    command="echo hi",
                )
            )

        self.assertEqual(result, {"success": True, "output": "ok"})

    def test_non_200_response_returns_typed_error(self):
        response = _FakeResponse(500, {})
        response.text = "internal error"
        with patch(
            "code_sessions.services.clone.httpx.AsyncClient",
            side_effect=lambda: _SinglePostFakeAsyncClient(response),
        ):
            result = _run(
                _execute_bash(
                    orchestrator_url="http://orchestrator",
                    auth_token="tok",
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    command="echo hi",
                )
            )

        self.assertFalse(result["success"])
        self.assertIn("HTTP 500", result["error"])

    def test_transport_exception_returns_typed_error(self):
        with patch(
            "code_sessions.services.clone.httpx.AsyncClient",
            side_effect=lambda: _SinglePostFakeAsyncClient(ConnectionError("refused")),
        ):
            result = _run(
                _execute_bash(
                    orchestrator_url="http://orchestrator",
                    auth_token="tok",
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    command="echo hi",
                )
            )

        self.assertFalse(result["success"])
        self.assertIn("refused", result["error"])
