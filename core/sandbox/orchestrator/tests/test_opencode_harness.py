"""What the opencode harness is configured to be allowed to do.

The permission profile, the environment, and the command line are pure
functions of a job's parameters, so each is checked here without a
container.

Two of these guard properties of ``opencode run`` that a run silently
depends on:

* Configuration is injected through ``OPENCODE_CONFIG_CONTENT``, which
  opencode merges last. A file planted in the workspace, or in any
  directory above it, is merged earlier and so cannot displace it.
* The prompt is left off the command line because ``opencode run``
  reads standard input to EOF and merges it into the prompt. The task
  file is that input.
"""

import json

import opencode_harness as harness

WORKSPACE = "/workspace/chat-abc"
EPHEMERAL_HOME = "/tmp/claude-home-job1"
MODEL = "anthropic/claude-sonnet-4.5"


def _config(mode="auto", **overrides):
    kwargs = dict(
        mode=mode,
        model=MODEL,
        ephemeral_home=EPHEMERAL_HOME,
        max_steps=25,
    )
    kwargs.update(overrides)
    return harness.build_config(**kwargs)


class TestAgentSelection:
    def test_plan_mode_uses_the_planning_agent(self):
        assert harness.agent_for_mode("plan") == harness.PLAN_AGENT

    def test_every_other_mode_uses_the_building_agent(self):
        assert harness.agent_for_mode("implement") == harness.BUILD_AGENT
        assert harness.agent_for_mode("auto") == harness.BUILD_AGENT


class TestPermissionProfile:
    """Plan mode must not be able to change the workspace."""

    def test_plan_mode_denies_editing(self):
        profile = harness.build_permission_profile("plan", "/plans")
        assert profile["edit"] == harness.DENY

    def test_plan_mode_denies_bash_by_default(self):
        """opencode's bash tool writes files the edit rule cannot see.

        A planning run's write barrier is the read-only workspace the
        runner imposes; this profile keeps the agent from reaching for
        a command that would test it.
        """
        profile = harness.build_permission_profile("plan", "/plans")
        assert profile["bash"][harness.WILDCARD] == harness.DENY
        assert profile["bash"]["ls*"] == harness.ALLOW
        assert "rm*" not in profile["bash"]

    def test_plan_mode_confines_outside_writes_to_the_plans_directory(self):
        profile = harness.build_permission_profile("plan", "/plans")
        external = profile["external_directory"]
        assert external[harness.WILDCARD] == harness.DENY
        assert external["/plans/*"] == harness.ALLOW

    def test_build_mode_allows_editing(self):
        profile = harness.build_permission_profile("implement", "/plans")
        assert profile["edit"] == harness.ALLOW
        assert profile["bash"][harness.WILDCARD] == harness.ALLOW

    def test_network_reaching_commands_are_denied_in_both_modes(self):
        build = harness.build_permission_profile("implement", "/plans")
        for command in ("curl*", "wget*", "ssh*", "sudo*"):
            assert build["bash"][command] == harness.DENY
        plan = harness.build_permission_profile("plan", "/plans")
        for command in ("curl*", "wget*", "ssh*", "sudo*"):
            assert command not in plan["bash"]

    def test_tool_driven_network_access_is_denied_in_both_modes(self):
        for mode in ("plan", "implement"):
            profile = harness.build_permission_profile(mode, "/plans")
            assert profile["webfetch"] == harness.DENY
            assert profile["websearch"] == harness.DENY

    def test_the_ask_user_relay_is_allowed_in_both_modes(self):
        for mode in ("plan", "implement"):
            profile = harness.build_permission_profile(mode, "/plans")
            assert profile[harness.ASK_USER_PERMISSION] == harness.ALLOW


class TestConfig:
    def test_model_routes_through_the_openrouter_provider(self):
        config = _config()
        assert config["model"] == f"openrouter/{MODEL}"
        options = config["provider"]["openrouter"]["options"]
        assert options["baseURL"] == harness.OPENROUTER_BASE_URL

    def test_api_key_is_referenced_not_embedded(self):
        """The config travels in an environment variable of its own.

        opencode resolves ``{env:...}`` itself, so the key never has to
        be written into the document.
        """
        config = _config()
        options = config["provider"]["openrouter"]["options"]
        assert options["apiKey"] == "{env:" + harness.API_KEY_ENV_VAR + "}"
        assert "sk-or" not in json.dumps(config)

    def test_step_ceiling_rides_in_the_agent_config(self):
        """``opencode run`` has no flag for it."""
        config = _config(mode="plan", max_steps=7)
        assert config["agent"][harness.PLAN_AGENT]["steps"] == 7

    def test_only_the_agent_for_the_mode_is_configured(self):
        assert list(_config(mode="plan")["agent"]) == [harness.PLAN_AGENT]
        assert list(_config(mode="implement")["agent"]) == [harness.BUILD_AGENT]

    def test_session_sharing_is_disabled(self):
        assert _config()["share"] == "disabled"

    def test_ask_user_server_is_declared_when_a_relay_is_given(self):
        config = _config(
            ask_user_command=["python3", "/tmp/relay.py"],
            ask_user_environment={"STERNA_JOB_TOKEN": "token"},
        )
        server = config["mcp"][harness.ASK_USER_SERVER]
        assert server["type"] == "local"
        assert server["command"] == ["python3", "/tmp/relay.py"]
        assert server["environment"]["STERNA_JOB_TOKEN"] == "token"
        assert server["enabled"] is True

    def test_no_mcp_section_without_a_relay(self):
        assert "mcp" not in _config()


class TestEnvironment:
    def _env(self, **overrides):
        kwargs = dict(
            config=_config(),
            ephemeral_home=EPHEMERAL_HOME,
            api_key="sk-or-SECRET",
            base_env={"HTTPS_PROXY": "http://egress-proxy:8888"},
        )
        kwargs.update(overrides)
        return harness.build_env(**kwargs)

    def test_config_is_injected_rather_than_left_on_disk(self):
        env = self._env()
        assert json.loads(env["OPENCODE_CONFIG_CONTENT"])["model"].startswith("openrouter/")

    def test_workspace_instruction_files_are_not_read(self):
        """AGENTS.md, CLAUDE.md and CONTEXT.md in the workspace are the
        user's to write, and would otherwise steer the agent."""
        env = self._env()
        assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
        assert env["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] == "1"

    def test_every_self_update_and_download_path_is_closed(self):
        env = self._env()
        for variable in (
            "OPENCODE_PURE",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS",
            "OPENCODE_DISABLE_MODELS_FETCH",
            "OPENCODE_DISABLE_AUTOUPDATE",
            "OPENCODE_DISABLE_SHARE",
            "OPENCODE_DISABLE_LSP_DOWNLOAD",
        ):
            assert env[variable] == "1"

    def test_state_is_confined_to_the_ephemeral_home(self):
        env = self._env()
        assert env["HOME"] == EPHEMERAL_HOME
        for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            assert env[variable].startswith(EPHEMERAL_HOME + "/")

    def test_sandbox_wide_settings_are_carried_through(self):
        assert self._env()["HTTPS_PROXY"] == "http://egress-proxy:8888"

    def test_api_key_reaches_the_variable_the_config_names(self):
        assert self._env()[harness.API_KEY_ENV_VAR] == "sk-or-SECRET"


class TestCommandLine:
    def test_prompt_is_not_passed_as_an_argument(self):
        """``opencode run`` reads stdin to EOF and merges it into the
        prompt, so the task travels there instead."""
        argv = harness.build_argv("implement")
        assert argv[:2] == ["opencode", "run"]
        assert all(not arg.startswith("Implement") for arg in argv)

    def test_output_is_requested_as_json(self):
        argv = harness.build_argv("plan")
        assert argv[argv.index("--format") + 1] == "json"

    def test_agent_matches_the_mode(self):
        argv = harness.build_argv("plan")
        assert argv[argv.index("--agent") + 1] == harness.PLAN_AGENT

    def test_a_title_is_supplied_to_skip_the_title_model_call(self):
        """Left unset, opencode spends a model call naming the session
        that no step of the run would ever report."""
        argv = harness.build_argv("implement")
        assert argv[argv.index("--title") + 1] == harness.SESSION_TITLE


class TestWrapperSpec:
    def _spec(self, mode="plan"):
        return harness.build_wrapper_spec(
            mode=mode,
            workspace_path=WORKSPACE,
            ephemeral_home=EPHEMERAL_HOME,
            task_file=f"{WORKSPACE}/.task.txt",
            model=MODEL,
            tools=["Read", "Write"],
        )

    def test_wrapper_runs_opencode_in_the_workspace(self):
        spec = self._spec()
        assert spec["cwd"] == WORKSPACE
        assert spec["argv"] == harness.build_argv("plan")

    def test_plan_directory_is_inside_the_ephemeral_home(self):
        """The workspace copy is unwritable while a plan run holds it
        read-only, so the plan has to land in the job's own home."""
        spec = self._spec()
        assert spec["plans_dir"].startswith(EPHEMERAL_HOME + "/")
        assert spec["plans_dir"] == harness.plans_dir_for(EPHEMERAL_HOME)

    def test_declared_mcp_servers_let_the_adapter_name_their_tools(self):
        assert self._spec()["mcp_servers"] == [harness.ASK_USER_SERVER]
