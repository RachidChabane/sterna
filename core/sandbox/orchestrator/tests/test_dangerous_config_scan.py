"""The workspace scan that refuses to start a job on a planted config.

A user can write to their own workspace from the sandbox terminal. Both
harnesses read configuration from files found there — settings, hooks,
MCP server definitions, agent permissions — so a job whose workspace
holds one does not start.

opencode widens what has to be covered: it looks for ``opencode.json``
and ``opencode.jsonc`` in the working directory *and every directory
above it*, and reads a ``.opencode`` directory beside them. Injecting
the real configuration through the environment outranks such a file on
merge, but it cannot stop the file from contributing keys the injected
document leaves unset, so the scan remains the barrier.
"""

import asyncio
from unittest.mock import MagicMock

from coding_agent_runner import CodingAgentRunner

WORKSPACE = "/workspace/chat-abc"


def _runner():
    return CodingAgentRunner(
        sandbox_executor=MagicMock(), user_id="user-1", chat_id="chat-1"
    )


def _scan(existing_paths):
    """Scan a workspace in which exactly `existing_paths` are present."""
    runner = _runner()
    container = MagicMock()

    def exec_run(command, **_kwargs):
        # The probe prints each path it finds; the mock replies with
        # whichever of the tested paths the scenario says exist.
        script = command[2]
        found = [path for path in existing_paths if f'test -e "{path}"' in script]
        return MagicMock(exit_code=0, output="\n".join(found).encode())

    container.exec_run.side_effect = exec_run
    return asyncio.run(runner._scan_for_dangerous_configs(container, WORKSPACE))


class TestScanScope:
    def test_a_clean_workspace_is_safe(self):
        is_safe, found = _scan([])
        assert is_safe is True
        assert found == []

    def test_claude_configs_still_block(self):
        is_safe, found = _scan([f"{WORKSPACE}/.claude"])
        assert is_safe is False
        assert found == [f"{WORKSPACE}/.claude"]

    def test_opencode_config_blocks(self):
        is_safe, found = _scan([f"{WORKSPACE}/opencode.json"])
        assert is_safe is False
        assert found == [f"{WORKSPACE}/opencode.json"]

    def test_comment_tolerant_opencode_config_blocks(self):
        is_safe, _ = _scan([f"{WORKSPACE}/opencode.jsonc"])
        assert is_safe is False

    def test_opencode_directory_blocks(self):
        is_safe, _ = _scan([f"{WORKSPACE}/.opencode"])
        assert is_safe is False

    def test_a_config_planted_above_the_workspace_blocks(self):
        """opencode searches upward, so the parent is in range."""
        is_safe, found = _scan(["/workspace/opencode.json"])
        assert is_safe is False
        assert found == ["/workspace/opencode.json"]

    def test_the_filesystem_root_is_in_range(self):
        is_safe, _ = _scan(["/opencode.json"])
        assert is_safe is False

    def test_every_offending_path_is_reported(self):
        is_safe, found = _scan(
            [f"{WORKSPACE}/opencode.json", "/workspace/.opencode"]
        )
        assert is_safe is False
        assert set(found) == {f"{WORKSPACE}/opencode.json", "/workspace/.opencode"}


class TestScanDirectories:
    def test_the_workspace_and_each_ancestor_are_walked(self):
        assert _runner()._config_scan_directories(WORKSPACE) == [
            WORKSPACE,
            "/workspace",
            "/",
        ]

    def test_the_walk_terminates_at_the_root(self):
        assert _runner()._config_scan_directories("/") == ["/"]
