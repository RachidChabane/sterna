"""Which harness a job runs on, and what the runner stages for it.

The opencode harness is opt-in: a job runs on Claude Code unless it, or
the environment, asks for the other. These tests pin that default and
the staging `_prepare_opencode_run` does, using a mock container that
records the commands the runner issues.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

import coding_harness
from claude_permission_profile import settings_for
from coding_agent_runner import CodingAgentRunner
from coding_harness import (
    CLAUDE_CODE,
    OPENCODE,
    ClaudeCodeOutputAdapter,
    create_adapter,
    parse_run_output,
    resolve_harness,
)
from opencode_output_adapter import OpencodeOutputAdapter

WORKSPACE = "/workspace/chat-abc"
JOB_DIR = "/tmp/agents/coding-agent-job1"
EPHEMERAL_HOME = "/tmp/claude-home-job1"


@pytest.fixture(autouse=True)
def _no_harness_in_environment(monkeypatch):
    monkeypatch.delenv(coding_harness.HARNESS_ENV_VAR, raising=False)


class TestHarnessSelection:
    def test_default_is_claude_code(self):
        assert resolve_harness() == CLAUDE_CODE

    def test_a_job_can_request_opencode(self):
        assert resolve_harness(OPENCODE) == OPENCODE

    def test_the_environment_selects_for_jobs_that_do_not(self, monkeypatch):
        monkeypatch.setenv(coding_harness.HARNESS_ENV_VAR, OPENCODE)
        assert resolve_harness() == OPENCODE

    def test_a_job_overrides_the_environment(self, monkeypatch):
        monkeypatch.setenv(coding_harness.HARNESS_ENV_VAR, OPENCODE)
        assert resolve_harness(CLAUDE_CODE) == CLAUDE_CODE

    def test_an_unknown_name_falls_back_rather_than_failing(self, monkeypatch):
        monkeypatch.setenv(coding_harness.HARNESS_ENV_VAR, "gpt-engineer")
        assert resolve_harness() == CLAUDE_CODE
        assert resolve_harness("gpt-engineer") == CLAUDE_CODE

    def test_each_harness_gets_its_own_adapter(self):
        assert isinstance(create_adapter(OPENCODE), OpencodeOutputAdapter)
        assert isinstance(create_adapter(CLAUDE_CODE), ClaudeCodeOutputAdapter)


class TestOutcomeParsing:
    def test_a_claude_run_is_read_by_the_claude_parser(self):
        stream = json.dumps(
            {"type": "result", "subtype": "success", "result": "done",
             "total_cost_usd": 0.5}
        )
        outcome = parse_run_output(CLAUDE_CODE, stream)
        assert outcome.summary == "done"
        assert outcome.total_cost_usd == 0.5

    def test_an_opencode_run_is_read_by_the_opencode_adapter(self):
        stream = "\n".join(
            json.dumps(event)
            for event in (
                {"type": "system", "subtype": "init", "cwd": WORKSPACE},
                {"type": "step_start", "part": {"type": "step-start"}},
                {"type": "tool_use", "part": {
                    "type": "tool", "tool": "write", "callID": "c1",
                    "state": {"status": "completed",
                              "input": {"filePath": f"{WORKSPACE}/a.py", "content": "x"},
                              "output": "Wrote file successfully.",
                              "metadata": {"exists": False}}}},
                {"type": "step_finish", "part": {
                    "type": "step-finish",
                    "tokens": {"input": 10, "output": 5}, "cost": 0.25}},
                {"type": "result", "subtype": "success", "result": "done"},
            )
        )
        outcome = parse_run_output(OPENCODE, stream, WORKSPACE)
        assert outcome.success is True
        assert outcome.summary == "done"
        assert outcome.files_created == ["a.py"]
        assert outcome.total_cost_usd == 0.25
        assert outcome.total_tokens == 15

    def test_a_failed_opencode_run_reports_its_error(self):
        stream = json.dumps(
            {"type": "result", "subtype": "error", "error": "opencode exited with code 1"}
        )
        outcome = parse_run_output(OPENCODE, stream)
        assert outcome.success is False
        assert outcome.error == "opencode exited with code 1"


def _staged(mode="implement"):
    """Run `_prepare_opencode_run` against a mock container.

    Returns the command, the environment, and every file the runner
    wrote into the sandbox, keyed by path.
    """
    runner = CodingAgentRunner(
        sandbox_executor=MagicMock(), user_id="user-1", chat_id="chat-1"
    )
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=0, output=b"")

    cmd, env = asyncio.run(
        runner._prepare_opencode_run(
            container, JOB_DIR, EPHEMERAL_HOME, WORKSPACE, mode,
            "anthropic/claude-sonnet-4.5", "sk-or-SECRET", 25, ["Read", "Write"],
            f"{JOB_DIR}/.task.txt", f"{JOB_DIR}/.out.jsonl", "TASK BODY",
            {"HTTPS_PROXY": "http://egress-proxy:8888", "ANTHROPIC_API_KEY": "sk-or-SECRET"},
            "job-token",
        )
    )

    written = {}
    for call in container.exec_run.call_args_list:
        script = call.args[0][2]
        if "printf '%s'" not in script:
            continue
        body, _, path = script.rpartition(" > ")
        written[path.strip()] = body.split("printf '%s' '", 1)[1][:-1]
    return cmd, env, written


class TestOpencodeStaging:
    def test_relay_and_wrapper_are_written_into_the_ephemeral_home(self):
        _, _, written = _staged()
        relay = written[f"{EPHEMERAL_HOME}/mcp-ask-user-opencode.py"]
        wrapper = written[f"{EPHEMERAL_HOME}/opencode-run-wrapper.py"]
        assert "ask_user" in relay
        assert "opencode" in wrapper

    def test_the_task_is_written_for_stdin_not_the_command_line(self):
        cmd, _, written = _staged()
        assert written[f"{JOB_DIR}/.task.txt"] == "TASK BODY"
        assert "TASK BODY" not in cmd

    def test_the_wrapper_is_told_where_the_task_and_the_plans_live(self):
        _, _, written = _staged(mode="plan")
        spec = json.loads(written[f"{JOB_DIR}/opencode-job.json"])
        assert spec["task_file"] == f"{JOB_DIR}/.task.txt"
        assert spec["plans_dir"].startswith(EPHEMERAL_HOME + "/")
        assert spec["mode"] == "plan"

    def test_job_identity_travels_in_the_relay_environment(self):
        """Out of the command line, so it does not show in a process
        list the sandboxed agent can read."""
        _, env, _ = _staged()
        config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        relay = config["mcp"]["ask-user"]
        assert relay["environment"] == {
            "STERNA_USER_ID": "user-1",
            "STERNA_CHAT_ID": "chat-1",
            "STERNA_JOB_TOKEN": "job-token",
        }
        assert all("job-token" not in argument for argument in relay["command"])

    def test_output_is_line_buffered_into_the_polled_file(self):
        cmd, _, _ = _staged()
        assert cmd.startswith("stdbuf -oL ")
        assert f"tee {JOB_DIR}/.out.jsonl" in cmd

    def test_wrapper_diagnostics_do_not_enter_the_parsed_stream(self):
        """The polled file must hold nothing but the harness's JSON."""
        cmd, _, _ = _staged()
        stderr_redirect, _, _ = cmd.partition(" | tee")
        assert "2>>" in stderr_redirect

    def test_claude_only_variables_do_not_reach_opencode(self):
        _, env, _ = _staged()
        assert "ANTHROPIC_API_KEY" not in env
        assert env["HTTPS_PROXY"] == "http://egress-proxy:8888"


class TestClaudePermissionProfile:
    """The settings document the Claude harness has always written."""

    def test_plan_mode_denies_writing_to_the_workspace(self):
        deny = settings_for("plan", WORKSPACE, EPHEMERAL_HOME)["permissions"]["deny"]
        assert f"Write({WORKSPACE}/**)" in deny
        assert f"Edit({WORKSPACE}/**)" in deny

    def test_plan_mode_allows_writing_only_to_the_ephemeral_home(self):
        allow = settings_for("plan", WORKSPACE, EPHEMERAL_HOME)["permissions"]["allow"]
        assert f"Write({EPHEMERAL_HOME}/**)" in allow
        assert f"Write({WORKSPACE}/**)" not in allow

    def test_implement_mode_allows_writing_to_the_workspace(self):
        allow = settings_for("auto", WORKSPACE, EPHEMERAL_HOME)["permissions"]["allow"]
        assert f"Write({WORKSPACE}/**)" in allow

    def test_network_reaching_commands_are_denied_in_both_modes(self):
        for mode in ("plan", "auto"):
            deny = settings_for(mode, WORKSPACE, EPHEMERAL_HOME)["permissions"]["deny"]
            for command in ("Bash(sudo*)", "Bash(curl*)", "Bash(wget*)", "Bash(ssh*)"):
                assert command in deny


class TestEnvironmentExport:
    """The shell must not reread what it exports.

    `_execute_with_file_streaming` exports the environment inside a
    shell command. opencode's whole configuration travels in
    ``OPENCODE_CONFIG_CONTENT`` as JSON — double quotes, ``$`` and
    backslashes — and an API key may hold the same characters. Quoting
    each value keeps the shell from expanding or truncating them.
    """

    def _exported(self, value):
        runner = CodingAgentRunner(
            sandbox_executor=MagicMock(), user_id="u", chat_id="c"
        )
        container = MagicMock()
        container.exec_run.return_value = MagicMock(exit_code=1, output=b"")
        asyncio.run(
            runner._execute_with_file_streaming(
                container=container,
                cmd="true",
                workspace_path=WORKSPACE,
                env={"OPENCODE_CONFIG_CONTENT": value},
                output_file="/tmp/out.jsonl",
                progress_file="/tmp/progress.json",
                harness=OPENCODE,
            )
        )
        for call in container.exec_run.call_args_list:
            script = call.args[0][2]
            if "export OPENCODE_CONFIG_CONTENT=" in script:
                return script
        raise AssertionError("the environment was never exported")

    def test_a_json_document_survives_the_shell(self):
        config = json.dumps({"$schema": "https://opencode.ai/config.json",
                             "model": "openrouter/anthropic/claude-sonnet-4.5"})
        script = self._exported(config)
        exported = script.split("export OPENCODE_CONFIG_CONTENT=", 1)[1].split(" &&", 1)[0]
        assert exported == f"'{config}'"

    def test_a_value_holding_a_quote_is_escaped_not_truncated(self):
        script = self._exported("a'b")
        assert "a'b" not in script.split("export OPENCODE_CONFIG_CONTENT=", 1)[1][:10]
        assert """'a'"'"'b'""" in script
