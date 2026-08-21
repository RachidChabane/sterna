"""Regression tests for CodingAgentRunner._create_config_file.

The plan-mode bug: ``_create_config_file`` once omitted ``mode`` and
``plan_content`` from the serialized config.json, so the in-sandbox
runner script read ``config.get("mode", "auto")`` and ALWAYS ran in
auto mode — plan mode silently produced full-write agents. These tests
pin the config wire format.

Pure unit tests: the docker container is a mock capturing exec_run.
"""

import asyncio
import json
from unittest.mock import MagicMock

from coding_agent_runner import CodingAgentConfig, CodingAgentRunner


def _make_runner():
    return CodingAgentRunner(
        sandbox_executor=MagicMock(),
        user_id="user-1",
        chat_id="chat-1",
    )


def _make_config(**overrides):
    kwargs = dict(
        task="Fix the bug in auth.py",
        model="anthropic/claude-sonnet-4",
        api_key="sk-or-SECRET",
        allowed_tools=["Read", "Edit", "Bash"],
        max_iterations=25,
        workspace_path="/workspace/chat-abc123",
        job_dir="/agents/coding-agent-job1",
        mcp_servers=None,
        mode="auto",
        plan_id=None,
        plan_content=None,
        sub_agents=None,
        user_model_preferences=None,
    )
    kwargs.update(overrides)
    return CodingAgentConfig(**kwargs)


def _write_config(config):
    """Run _create_config_file against a mock container; return
    (result, parsed_config_json)."""
    runner = _make_runner()
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=0, output=b"")

    result = asyncio.run(
        runner._create_config_file(container, config.job_dir, config)
    )

    if not container.exec_run.called:
        return result, None
    cmd = container.exec_run.call_args.args[0]
    # ["sh", "-c", "cat > <job_dir>/config.json << 'CONFIGEOF'\n<json>\nCONFIGEOF"]
    assert cmd[0:2] == ["sh", "-c"]
    heredoc = cmd[2]
    body = heredoc.split("CONFIGEOF'\n", 1)[1].rsplit("\nCONFIGEOF", 1)[0]
    return result, json.loads(body)


class TestConfigSerialization:
    def test_mode_key_present_default_auto(self):
        result, data = _write_config(_make_config())
        assert result == {"success": True}
        assert "mode" in data, "regression: mode missing from config.json"
        assert data["mode"] == "auto"

    def test_plan_mode_serialized(self):
        _, data = _write_config(_make_config(mode="plan"))
        assert data["mode"] == "plan"

    def test_implement_mode_carries_plan_content(self):
        plan = "# Plan\n\n1. Read auth.py\n2. Fix the bug\n"
        _, data = _write_config(
            _make_config(mode="implement", plan_content=plan)
        )
        assert data["mode"] == "implement"
        assert (
            "plan_content" in data
        ), "regression: plan_content missing from config.json"
        assert data["plan_content"] == plan

    def test_plan_content_null_when_absent(self):
        _, data = _write_config(_make_config())
        assert data["plan_content"] is None

    def test_core_execution_fields_serialized(self):
        _, data = _write_config(_make_config())
        assert data["task"] == "Fix the bug in auth.py"
        assert data["model"] == "anthropic/claude-sonnet-4"
        assert data["allowed_tools"] == ["Read", "Edit", "Bash"]
        assert data["max_iterations"] == 25
        assert data["workspace_path"] == "/workspace/chat-abc123"
        assert data["job_dir"] == "/agents/coding-agent-job1"

    def test_api_key_never_written_to_config_file(self):
        """The key travels via env var; the config file lands on a
        tmpfs readable by the sandboxed agent."""
        _, data = _write_config(_make_config())
        blob = json.dumps(data)
        assert "sk-or-SECRET" not in blob
        assert "api_key" not in data

    def test_mcp_servers_and_sub_agents_pass_through(self):
        mcp = {"github": {"url": "http://mcp:9000"}}
        subs = [{"name": "explorer", "markdown": "# explorer"}]
        _, data = _write_config(
            _make_config(mcp_servers=mcp, sub_agents=subs)
        )
        assert data["mcp_servers"] == mcp
        assert data["sub_agents"] == subs

    def test_config_written_to_job_dir(self):
        config = _make_config()
        runner = _make_runner()
        container = MagicMock()
        container.exec_run.return_value = MagicMock(exit_code=0, output=b"")
        asyncio.run(
            runner._create_config_file(container, config.job_dir, config)
        )
        cmd = container.exec_run.call_args.args[0]
        assert f"cat > {config.job_dir}/config.json" in cmd[2]
        # Runs as the unprivileged sandbox user.
        assert container.exec_run.call_args.kwargs.get("user") == "sandboxuser"

    def test_exec_failure_reported(self):
        config = _make_config()
        runner = _make_runner()
        container = MagicMock()
        container.exec_run.return_value = MagicMock(
            exit_code=1, output=b"disk full"
        )
        result = asyncio.run(
            runner._create_config_file(container, config.job_dir, config)
        )
        assert result["success"] is False
        assert "disk full" in result["error"]

    def test_exec_exception_reported_not_raised(self):
        config = _make_config()
        runner = _make_runner()
        container = MagicMock()
        container.exec_run.side_effect = RuntimeError("container gone")
        result = asyncio.run(
            runner._create_config_file(container, config.job_dir, config)
        )
        assert result["success"] is False
        assert "container gone" in result["error"]
