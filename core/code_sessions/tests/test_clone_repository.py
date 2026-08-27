"""Tests for ``code_sessions.services.clone.clone_repository``.

Covers the GitHub API + orchestrator bash-execution + ClonedRepository
persistence orchestration flow. External I/O (GitHub API, orchestrator
bash execution, the Django ORM reads/writes) is mocked at the module's
own adapter-seam functions/classes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from code_sessions.services.clone import clone_repository


def _run(coro):
    return async_to_sync(lambda: coro)()


class _FakeGitHubService:
    def __init__(self, repo_info, clone_url="https://x-access-token:tok@github.com/owner/repo.git"):
        self._repo_info = repo_info
        self._clone_url = clone_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_repo(self, owner, repo):
        return self._repo_info

    def get_clone_url_with_token(self, full_name):
        return self._clone_url


def _github_service_factory(repo_info, clone_url=None):
    def factory(_token):
        if clone_url is not None:
            return _FakeGitHubService(repo_info, clone_url=clone_url)
        return _FakeGitHubService(repo_info)

    return factory


class CloneRepositorySuccessTests(SimpleTestCase):
    def test_success_persists_cloned_repository_and_returns_head_info(self):
        repo_info = {"default_branch": "main", "private": False}
        bash_responses = [
            {"success": True},  # mkdir
            {"success": True, "exit_code": 0},  # git clone
            {"success": True, "output": "deadbeef|||Initial commit"},  # head info
        ]

        conversation = SimpleNamespace(id="conv-1")

        with (
            patch(
                "code_sessions.services.clone.GitHubService",
                side_effect=_github_service_factory(repo_info),
            ),
            patch(
                "code_sessions.services.clone._execute_bash",
                new=AsyncMock(side_effect=bash_responses),
            ),
            patch(
                "code_sessions.services.clone._get_conversation",
                new=AsyncMock(return_value=conversation),
            ),
            patch(
                "code_sessions.services.clone._create_or_update_cloned_repo",
                new=AsyncMock(return_value=(SimpleNamespace(), True)),
            ) as mock_persist,
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch=None,
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        self.assertEqual(
            result,
            {
                "success": True,
                "full_name": "owner/repo",
                "branch": "main",
                "workspace_path": "/workspace/chat-chat-1/repo",
                "head_commit_sha": "deadbeef",
                "head_commit_message": "Initial commit",
            },
        )
        mock_persist.assert_awaited_once()

    def test_explicit_branch_overrides_default_branch(self):
        repo_info = {"default_branch": "main", "private": False}
        bash_responses = [
            {"success": True},
            {"success": True, "exit_code": 0},
            {"success": True, "output": "sha1|||msg"},
        ]

        with (
            patch(
                "code_sessions.services.clone.GitHubService",
                side_effect=_github_service_factory(repo_info),
            ),
            patch(
                "code_sessions.services.clone._execute_bash",
                new=AsyncMock(side_effect=bash_responses),
            ),
            patch(
                "code_sessions.services.clone._get_conversation",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch="feature-x",
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        self.assertEqual(result["branch"], "feature-x")

    def test_missing_conversation_skips_persistence_but_still_succeeds(self):
        repo_info = {"default_branch": "main", "private": False}
        bash_responses = [
            {"success": True},
            {"success": True, "exit_code": 0},
            {"success": True, "output": "sha1|||msg"},
        ]

        with (
            patch(
                "code_sessions.services.clone.GitHubService",
                side_effect=_github_service_factory(repo_info),
            ),
            patch(
                "code_sessions.services.clone._execute_bash",
                new=AsyncMock(side_effect=bash_responses),
            ),
            patch(
                "code_sessions.services.clone._get_conversation",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "code_sessions.services.clone._create_or_update_cloned_repo",
                new=AsyncMock(),
            ) as mock_persist,
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-missing",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch=None,
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        self.assertTrue(result["success"])
        mock_persist.assert_not_awaited()

    def test_cloned_repository_persistence_failure_does_not_fail_the_clone(self):
        repo_info = {"default_branch": "main", "private": False}
        bash_responses = [
            {"success": True},
            {"success": True, "exit_code": 0},
            {"success": True, "output": "sha1|||msg"},
        ]
        conversation = SimpleNamespace(id="conv-1")

        with (
            patch(
                "code_sessions.services.clone.GitHubService",
                side_effect=_github_service_factory(repo_info),
            ),
            patch(
                "code_sessions.services.clone._execute_bash",
                new=AsyncMock(side_effect=bash_responses),
            ),
            patch(
                "code_sessions.services.clone._get_conversation",
                new=AsyncMock(return_value=conversation),
            ),
            patch(
                "code_sessions.services.clone._create_or_update_cloned_repo",
                new=AsyncMock(side_effect=RuntimeError("db unavailable")),
            ),
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch=None,
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        # Persisting the ClonedRepository row is best-effort: the clone
        # itself already succeeded, so a DB failure here must not turn the
        # overall result into a failure.
        self.assertTrue(result["success"])
        self.assertEqual(result["head_commit_sha"], "sha1")

    def test_head_info_failure_leaves_commit_fields_empty(self):
        repo_info = {"default_branch": "main", "private": False}
        bash_responses = [
            {"success": True},
            {"success": True, "exit_code": 0},
            {"success": False, "error": "log failed"},
        ]

        with (
            patch(
                "code_sessions.services.clone.GitHubService",
                side_effect=_github_service_factory(repo_info),
            ),
            patch(
                "code_sessions.services.clone._execute_bash",
                new=AsyncMock(side_effect=bash_responses),
            ),
            patch(
                "code_sessions.services.clone._get_conversation",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch=None,
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["head_commit_sha"], "")
        self.assertEqual(result["head_commit_message"], "")


class CloneRepositoryFailureTests(SimpleTestCase):
    def test_private_repository_is_rejected(self):
        repo_info = {"default_branch": "main", "private": True}

        with patch(
            "code_sessions.services.clone.GitHubService",
            side_effect=_github_service_factory(repo_info),
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch=None,
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        self.assertEqual(
            result,
            {
                "success": False,
                "error": "Private repositories are not supported yet. Please use a public repository.",
            },
        )

    def test_mkdir_failure_returns_sanitized_error(self):
        repo_info = {"default_branch": "main", "private": False}

        with (
            patch(
                "code_sessions.services.clone.GitHubService",
                side_effect=_github_service_factory(repo_info),
            ),
            patch(
                "code_sessions.services.clone._execute_bash",
                new=AsyncMock(return_value={"success": False, "error": "unexpected io failure"}),
            ),
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch=None,
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        self.assertFalse(result["success"])
        # The raw error is wrapped as "Failed to create workspace directory:
        # <cause>" before sanitization, so the workspace-setup branch (which
        # matches on that wrapper text) wins over a generic cause-based match.
        self.assertEqual(
            result["error"],
            "Workspace setup failed. The sandbox may be starting up — please try again in a moment.",
        )

    def test_clone_failure_returns_sanitized_error_with_token_stripped(self):
        repo_info = {"default_branch": "main", "private": False}
        bash_responses = [
            {"success": True},  # mkdir
            {
                "success": False,
                "exit_code": 128,
                "output": "fatal: could not read Username for 'https://oauth2:secrettoken@github.com'",
            },
        ]

        with (
            patch(
                "code_sessions.services.clone.GitHubService",
                side_effect=_github_service_factory(repo_info),
            ),
            patch(
                "code_sessions.services.clone._execute_bash",
                new=AsyncMock(side_effect=bash_responses),
            ),
        ):
            with self.assertLogs("code_sessions.services.clone", level="ERROR") as logs:
                result = _run(
                    clone_repository(
                        user_id="user-1",
                        conversation_id="conv-1",
                        chat_id="chat-1",
                        repo_url="owner/repo",
                        branch=None,
                        github_token="gh-tok",
                        auth_token="auth-tok",
                    )
                )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Authentication failed. Try reconnecting your GitHub account.")
        # The raw token must never reach the logs.
        logged = "\n".join(logs.output)
        self.assertNotIn("secrettoken", logged)
        self.assertIn("oauth2:***@", logged)

    def test_invalid_repo_url_is_caught_as_value_error(self):
        result = _run(
            clone_repository(
                user_id="user-1",
                conversation_id="conv-1",
                chat_id="chat-1",
                repo_url="not a valid url",
                branch=None,
                github_token="gh-tok",
                auth_token="auth-tok",
            )
        )

        self.assertFalse(result["success"])
        self.assertIn("Invalid repository URL", result["error"])

    def test_unexpected_exception_is_caught_and_sanitized(self):
        with patch(
            "code_sessions.services.clone.GitHubService",
            side_effect=RuntimeError("boom"),
        ):
            result = _run(
                clone_repository(
                    user_id="user-1",
                    conversation_id="conv-1",
                    chat_id="chat-1",
                    repo_url="owner/repo",
                    branch=None,
                    github_token="gh-tok",
                    auth_token="auth-tok",
                )
            )

        self.assertFalse(result["success"])
        self.assertIsInstance(result["error"], str)
