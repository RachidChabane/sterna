"""Regression tests for ``code_sessions.services.clone.ensure_repo_in_sandbox``.

Context (bug fix): the sandbox's ``/workspace`` is tmpfs, so a fresh/recycled
sandbox container can have a ``ClonedRepository`` row in Postgres with no repo
actually present in the container filesystem, and no versioned files ever
saved for it ("no-diffs" case -- e.g. a demo user whose repo was seeded but
never touched by the coding agent). ``ensure_repo_in_sandbox`` is meant to
handle that by cloning the base repo and treating zero restored files as
success, not a failure.

That flow used to be unreachable: the function read ``ClonedRepository`` /
``GitHubConnection`` via ``asgiref.sync.sync_to_async`` (default
``thread_sensitive=True``), which deadlocks with "You cannot submit onto
CurrentThreadExecutor from its own thread" when called -- as
``code_sessions.views.ensure_repo`` does -- from inside a manually created
``asyncio.new_event_loop().run_until_complete(...)`` on a DRF view thread
that Django's ASGI handler already runs inside its own thread-sensitive
executor. That crash was confirmed live (curl against the running dev stack)
before the fix and is gone after switching those three ORM reads/writes to
``asyncio.to_thread`` (see ``_get_cloned_repo`` / ``_get_github_connection`` /
``_update_cloned_repo_head`` in clone.py) -- a pytest that merely awaits the
coroutine directly, as these do, cannot reproduce that specific nested-loop
deadlock, so these tests pin the *behavioral* contract only: the two outcomes
that flow through once the crash is gone.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from code_sessions.services.clone import ensure_repo_in_sandbox


def _run(coro):
    return async_to_sync(lambda: coro)()


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class _RoutingFakeAsyncClient:
    """Stand-in for ``httpx.AsyncClient`` supporting ``async with ... as client``.

    Routes ``client.post(url, ...)`` to a canned response by matching the
    tail of the URL, so a single fake can stand in for the three distinct
    orchestrator calls ``ensure_repo_in_sandbox`` makes
    (``/workspace/ensure-repo``, ``/workspace/restore``,
    ``/workspace/reconcile-git``) across the several ``async with
    httpx.AsyncClient()`` blocks in the function under test.
    """

    def __init__(self, responses_by_suffix):
        self._responses = responses_by_suffix

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **_kwargs):
        for suffix, response in self._responses.items():
            if url.endswith(suffix):
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
        current_branch="main",
        default_branch="main",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class EnsureRepoInSandboxNoDiffsTests(SimpleTestCase):
    """The clone-first-then-restore flow with zero stored versions succeeds."""

    def test_zero_stored_versions_is_treated_as_success(self):
        responses = {
            "/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": True}),
            # The no-diffs case: nothing was ever saved for this chat, so the
            # orchestrator restores zero files -- that must NOT be an error.
            "/workspace/restore": _FakeResponse(200, {"files_synced": 0}),
            "/workspace/reconcile-git": _FakeResponse(
                200, {"committed": True, "branch": "main", "commit_sha": "abc123"}
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
            ) as mock_clone,
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
                ensure_repo_in_sandbox(
                    user_id="user-1",
                    conversation_id="conv-1",
                    auth_token="tok",
                )
            )

        self.assertEqual(
            result,
            {
                "action": "restored",
                "success": True,
                "branch": "main",
                "commit_sha": "abc123",
                "committed": True,
            },
        )
        mock_clone.assert_awaited_once()
        mock_update_head.assert_awaited_once_with("conv-1", "abc123")


class EnsureRepoInSandboxNoGitHubConnectionTests(SimpleTestCase):
    """Missing GitHubConnection is a typed, non-crashing outcome."""

    def test_missing_github_connection_returns_typed_error_without_raising(self):
        responses = {
            "/workspace/ensure-repo": _FakeResponse(200, {"needs_clone": True}),
        }

        with (
            patch(
                "code_sessions.services.clone._get_cloned_repo",
                new=AsyncMock(return_value=_fake_cloned_repo()),
            ),
            patch(
                "code_sessions.services.clone._get_github_connection",
                new=AsyncMock(return_value=None),
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
                ensure_repo_in_sandbox(
                    user_id="user-1",
                    conversation_id="conv-1",
                    auth_token="tok",
                )
            )

        self.assertEqual(
            result,
            {
                "action": "none",
                "success": False,
                "error": "No GitHub token found",
                "code": "github_not_connected",
            },
        )
        # Same typed `code` the clone_repo view returns with HTTP 400 for the
        # equivalent condition (see code_sessions/views.py clone_repo), so
        # both paths report the missing-GitHub-connection case identically.
        mock_clone.assert_not_awaited()

    def test_no_cloned_repository_row_is_a_no_op_success(self):
        with patch(
            "code_sessions.services.clone._get_cloned_repo",
            new=AsyncMock(return_value=None),
        ):
            result = _run(
                ensure_repo_in_sandbox(
                    user_id="user-1",
                    conversation_id="conv-1",
                    auth_token="tok",
                )
            )

        self.assertEqual(result["action"], "none")
        self.assertTrue(result["success"])
