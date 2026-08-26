"""Where a job's sub-agents land in the sandbox.

`CodingAgentRunner._plant_sub_agents` writes one markdown file per
sub-agent into the container. opencode discovers agents under the
configuration directory the run's environment names and under the
workspace's own ``.opencode/``, and the harness disables the latter — so
a file written anywhere else is one opencode never reads.

Pure unit tests: the docker container is a mock capturing exec_run.
"""

from unittest.mock import MagicMock

import opencode_harness as harness
from coding_agent_runner import CodingAgentRunner

EPHEMERAL_HOME = "/tmp/opencode-home-job1"

EXPLORER = {
    "name": "explorer",
    "markdown": (
        "---\n"
        "name: explorer\n"
        "description: Explores a subsystem\n"
        "model: sonnet\n"
        "tools:\n"
        "- Read\n"
        "- Grep\n"
        "---\n"
        "\n"
        "You explore.\n"
    ),
}


def _plant(sub_agents):
    """Run the planting against a mock container; return the shell command."""
    runner = CodingAgentRunner(
        sandbox_executor=MagicMock(), user_id="user-1", chat_id="chat-1"
    )
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=0, output=b"")

    runner._plant_sub_agents(container, EPHEMERAL_HOME, sub_agents)

    if not container.exec_run.called:
        return None
    command = container.exec_run.call_args.args[0]
    assert command[:2] == ["sh", "-c"]
    assert container.exec_run.call_args.kwargs.get("user") == "sandboxuser"
    return command[2]


class TestPlanting:
    def test_the_file_lands_where_opencode_looks(self):
        command = _plant([EXPLORER])
        agents_dir = harness.subagent_dir_for(EPHEMERAL_HOME)

        assert f"mkdir -p {agents_dir}" in command
        assert f"> {agents_dir}/explorer.md" in command

    def test_the_file_is_not_left_where_opencode_never_looks(self):
        """The directory a Claude-Code harness would have used."""
        assert ".claude/agents" not in _plant([EXPLORER])

    def test_the_definition_is_translated_before_it_is_written(self):
        """Written verbatim, an imported agent's ``tools`` list would make
        opencode reject its whole configuration and fail the run."""
        command = _plant([EXPLORER])

        assert "mode: subagent" in command
        assert "- Read" not in command
        assert "model: sonnet" not in command

    def test_every_agent_gets_its_own_file(self):
        second = dict(EXPLORER, name="reviewer")
        command = _plant([EXPLORER, second])
        agents_dir = harness.subagent_dir_for(EPHEMERAL_HOME)

        assert f"> {agents_dir}/explorer.md" in command
        assert f"> {agents_dir}/reviewer.md" in command

    def test_a_job_without_sub_agents_touches_nothing(self):
        assert _plant([]) is None
        assert _plant(None) is None

    def test_a_failed_write_does_not_raise(self):
        """A job runs without its sub-agents rather than not at all."""
        runner = CodingAgentRunner(
            sandbox_executor=MagicMock(), user_id="user-1", chat_id="chat-1"
        )
        container = MagicMock()
        container.exec_run.return_value = MagicMock(exit_code=1, output=b"disk full")

        runner._plant_sub_agents(container, EPHEMERAL_HOME, [EXPLORER])
