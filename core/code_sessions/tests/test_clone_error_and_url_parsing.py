"""Tests for the pure helpers in ``code_sessions.services.clone``:
``_sanitize_clone_error`` (raw error -> user-facing message) and
``parse_repo_url`` (accepted URL shapes -> owner/repo).
"""

from django.test import SimpleTestCase

from code_sessions.services.clone import _sanitize_clone_error, parse_repo_url


# ---------------------------------------------------------------------------
# _sanitize_clone_error
# ---------------------------------------------------------------------------


class SanitizeCloneErrorTests(SimpleTestCase):
    """Each recognized raw error substring maps to a fixed user-facing message."""

    def test_repository_not_found(self):
        self.assertEqual(
            _sanitize_clone_error("fatal: repository 'x' not found"),
            "Repository not found. Check the name or ensure you have access to this repository.",
        )

    def test_could_not_read_username_is_auth_failure(self):
        self.assertEqual(
            _sanitize_clone_error("fatal: could not read Username for 'https://github.com'"),
            "Authentication failed. Try reconnecting your GitHub account.",
        )

    def test_authentication_keyword_is_auth_failure(self):
        self.assertEqual(
            _sanitize_clone_error("Authentication required"),
            "Authentication failed. Try reconnecting your GitHub account.",
        )

    def test_401_is_auth_failure(self):
        self.assertEqual(
            _sanitize_clone_error("HTTP 401: Bad credentials"),
            "Authentication failed. Try reconnecting your GitHub account.",
        )

    def test_permission_denied_is_access_denied(self):
        self.assertEqual(
            _sanitize_clone_error("fatal: Permission denied (publickey)"),
            "Access denied. You don't have permission to clone this repository.",
        )

    def test_403_is_access_denied(self):
        self.assertEqual(
            _sanitize_clone_error("HTTP 403: Forbidden"),
            "Access denied. You don't have permission to clone this repository.",
        )

    def test_remote_branch_not_found(self):
        self.assertEqual(
            _sanitize_clone_error("fatal: Remote branch missing-branch not found in upstream origin"),
            "Branch not found. The specified branch doesn't exist in this repository.",
        )

    def test_could_not_resolve_host_is_network_error(self):
        self.assertEqual(
            _sanitize_clone_error("fatal: Could not resolve host: github.com"),
            "Network error. Could not reach GitHub. Please try again.",
        )

    def test_name_resolution_is_network_error(self):
        self.assertEqual(
            _sanitize_clone_error("Temporary failure in name resolution"),
            "Network error. Could not reach GitHub. Please try again.",
        )

    def test_timed_out_maps_to_timeout_message(self):
        self.assertEqual(
            _sanitize_clone_error("Connection timed out after 300s"),
            "Clone timed out. The repository may be too large or the connection is slow. Please try again.",
        )

    def test_timeout_keyword_maps_to_timeout_message(self):
        self.assertEqual(
            _sanitize_clone_error("operation timeout"),
            "Clone timed out. The repository may be too large or the connection is slow. Please try again.",
        )

    def test_connection_refused_maps_to_connection_error(self):
        self.assertEqual(
            _sanitize_clone_error("Connection refused"),
            "Connection error. Please try again in a moment.",
        )

    def test_connection_reset_maps_to_connection_error(self):
        self.assertEqual(
            _sanitize_clone_error("Connection reset by peer"),
            "Connection error. Please try again in a moment.",
        )

    def test_failed_to_create_workspace_maps_to_workspace_message(self):
        self.assertEqual(
            _sanitize_clone_error("Failed to create workspace directory: no such file"),
            "Workspace setup failed. The sandbox may be starting up — please try again in a moment.",
        )

    def test_command_failed_with_exit_code_maps_to_workspace_message(self):
        self.assertEqual(
            _sanitize_clone_error("Command failed with exit code 1"),
            "Workspace setup failed. The sandbox may be starting up — please try again in a moment.",
        )

    def test_http_5xx_maps_to_service_unavailable(self):
        self.assertEqual(
            _sanitize_clone_error("HTTP 502: Bad Gateway"),
            "Service temporarily unavailable. Please try again in a moment.",
        )

    def test_internal_server_error_maps_to_service_unavailable(self):
        self.assertEqual(
            _sanitize_clone_error("500 Internal Server Error"),
            "Service temporarily unavailable. Please try again in a moment.",
        )

    def test_no_space_left_maps_to_storage_message(self):
        self.assertEqual(
            _sanitize_clone_error("fatal: write error: No space left on device"),
            "Not enough storage space. Try a smaller repository.",
        )

    def test_disk_quota_maps_to_storage_message(self):
        self.assertEqual(
            _sanitize_clone_error("disk quota exceeded"),
            "Not enough storage space. Try a smaller repository.",
        )

    def test_invalid_repository_url_maps_to_invalid_url_message(self):
        self.assertEqual(
            _sanitize_clone_error("Invalid repository URL format: not-a-url"),
            "Invalid repository URL. Use the format owner/repo or a GitHub URL.",
        )

    def test_unmatched_message_strips_known_prefix(self):
        self.assertEqual(
            _sanitize_clone_error("Clone failed: something odd happened"),
            "something odd happened",
        )

    def test_unmatched_message_strips_fatal_prefix(self):
        self.assertEqual(
            _sanitize_clone_error("fatal: something odd happened"),
            "something odd happened",
        )

    def test_cryptic_exit_code_message_becomes_generic(self):
        self.assertEqual(
            _sanitize_clone_error("Re-clone failed: process exit code 137"),
            "Something went wrong. Please try again.",
        )

    def test_cryptic_traceback_message_becomes_generic(self):
        self.assertEqual(
            _sanitize_clone_error("Traceback (most recent call last): ..."),
            "Something went wrong. Please try again.",
        )

    def test_long_unmatched_message_is_truncated(self):
        raw = "x" * 200
        result = _sanitize_clone_error(raw)
        self.assertEqual(len(result), 150)
        self.assertTrue(result.endswith("..."))

    def test_short_unmatched_message_passes_through(self):
        self.assertEqual(_sanitize_clone_error("a short odd message"), "a short odd message")


# ---------------------------------------------------------------------------
# parse_repo_url
# ---------------------------------------------------------------------------


class ParseRepoUrlTests(SimpleTestCase):
    def test_owner_repo_shorthand_passes_through(self):
        self.assertEqual(parse_repo_url("owner/repo"), "owner/repo")

    def test_https_url_without_git_suffix(self):
        self.assertEqual(parse_repo_url("https://github.com/owner/repo"), "owner/repo")

    def test_https_url_with_git_suffix(self):
        self.assertEqual(parse_repo_url("https://github.com/owner/repo.git"), "owner/repo")

    def test_https_url_with_trailing_slash(self):
        self.assertEqual(parse_repo_url("https://github.com/owner/repo/"), "owner/repo")

    def test_ssh_url_with_git_suffix(self):
        self.assertEqual(parse_repo_url("git@github.com:owner/repo.git"), "owner/repo")

    def test_ssh_url_without_git_suffix(self):
        self.assertEqual(parse_repo_url("git@github.com:owner/repo"), "owner/repo")

    def test_extra_path_segments_in_shorthand_form_is_invalid(self):
        with self.assertRaises(ValueError):
            parse_repo_url("owner/repo/extra")

    def test_unrecognized_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_repo_url("not a repo url at all")
