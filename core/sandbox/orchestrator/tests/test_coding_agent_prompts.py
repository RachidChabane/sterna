"""The prompt a run is given, against the toolset it actually has.

A prompt that names a tool the run's mode denies, or one that does not
exist, spends model calls on refusals and teaches the model that its
instructions are unreliable. These tests read the tool vocabulary from
the permission profile the same job is configured with, so a prompt and
a profile cannot drift apart silently.
"""

import coding_agent_prompts as prompts
import opencode_harness as harness
from coding_harness import IMPLEMENT_MODE, PLAN_MODE
from opencode_output_adapter import TOOL_TRANSLATIONS

WORKSPACE = "/workspace/chat-abc"
EPHEMERAL_HOME = "/tmp/opencode-home-job1"
PLAN_PATH = harness.plan_path_for(EPHEMERAL_HOME)
TASK = "Add archiving to the auth module"
PLAN = "# Implementation Plan: Archiving\n\n## Summary\nArchive things.\n"

#: Tools no opencode run offers, whatever its mode.
TOOLS_THAT_DO_NOT_EXIST = ("ExitPlanMode", "NotebookEdit")


def _prompt(mode, plan_content=None):
    return prompts.build_task_prompt(
        mode=mode,
        task=TASK,
        plan_content=plan_content,
        workspace_path=WORKSPACE,
        plan_path=PLAN_PATH,
    )


def _spellings(opencode_tool):
    """How a prompt could name one tool.

    A prompt names tools in backticks, in opencode's own vocabulary; a
    prompt written for another CLI names them in that CLI's, followed by
    the word "tool". Both spellings are searched, because it is the
    second that a prompt inherited from another harness carries.
    """
    spellings = [f"`{opencode_tool}`"]
    translation = TOOL_TRANSLATIONS.get(opencode_tool)
    if translation is not None:
        spellings.append(f"{translation.canonical_name} tool")
    return spellings


def _denied_in_plan_mode():
    """The tools a planning run's permission profile refuses outright."""
    profile = harness.build_permission_profile(
        PLAN_MODE, harness.plans_dir_for(EPHEMERAL_HOME)
    )
    return sorted(
        tool for tool, rule in profile.items() if rule == harness.DENY
    )


class TestThePlanModePrompt:
    def test_it_names_no_tool_the_mode_denies(self):
        prompt = _prompt(PLAN_MODE)
        denied = _denied_in_plan_mode()

        assert denied, "the plan profile denies nothing — this test proves nothing"
        for tool in denied:
            for spelling in _spellings(tool):
                assert spelling not in prompt

    def test_it_names_no_tool_that_does_not_exist(self):
        prompt = _prompt(PLAN_MODE)
        for tool in TOOLS_THAT_DO_NOT_EXIST:
            assert tool not in prompt

    def test_it_does_not_offer_delegation(self):
        """`task` is denied in plan mode, so there is nothing to delegate to."""
        prompt = _prompt(PLAN_MODE).lower()
        assert "sub-agent" not in prompt
        assert "delegate" not in prompt

    def test_it_says_where_the_plan_goes(self):
        """The run's whole output is the file it writes there."""
        prompt = _prompt(PLAN_MODE)
        assert PLAN_PATH in prompt
        assert "`write`" in prompt

    def test_the_plan_path_is_one_the_profile_lets_the_run_write(self):
        profile = harness.build_permission_profile(
            PLAN_MODE, harness.plans_dir_for(EPHEMERAL_HOME)
        )
        allowed = [
            pattern
            for pattern, rule in profile["external_directory"].items()
            if rule == harness.ALLOW
        ]
        assert any(
            PLAN_PATH.startswith(pattern.rstrip("*")) for pattern in allowed
        )

    def test_the_confinement_rules_make_room_for_the_plan(self):
        """Every rule keeps the run inside the workspace; the plan is the
        one file it must put outside it, and no rule may forbid that."""
        prompt = _prompt(PLAN_MODE)
        assert f"other than {PLAN_PATH}" in prompt
        forbids_absolute = next(
            line for line in prompt.split("\n") if line.startswith("- Use /tmp/")
        )
        assert "other than that one file" in forbids_absolute

    def test_it_does_not_offer_package_installation(self):
        """A planning run holds the workspace read-only and is allowed no
        command that would install anything."""
        assert "pip install" not in _prompt(PLAN_MODE)


class TestTheOtherModes:
    def test_an_implementing_run_carries_its_plan(self):
        prompt = _prompt(IMPLEMENT_MODE, plan_content=PLAN)
        assert PLAN in prompt
        assert "MODE: IMPLEMENTATION" in prompt

    def test_an_implementing_run_without_a_plan_falls_back_to_the_task(self):
        prompt = _prompt(IMPLEMENT_MODE)
        assert "TASK:\n" + TASK in prompt

    def test_they_are_confined_to_the_workspace_with_no_exception(self):
        for prompt in (_prompt("auto"), _prompt(IMPLEMENT_MODE, plan_content=PLAN)):
            assert f"modify files outside {WORKSPACE}" in prompt
            assert PLAN_PATH not in prompt

    def test_they_are_told_packages_can_be_installed(self):
        for prompt in (_prompt("auto"), _prompt(IMPLEMENT_MODE, plan_content=PLAN)):
            assert "pip install" in prompt


class TestEveryMode:
    def test_the_relay_is_named_as_opencode_offers_it(self):
        """opencode exposes an MCP server's tools as ``{server}_{tool}``,
        which is the only name the model can call."""
        for mode in (PLAN_MODE, IMPLEMENT_MODE, "auto"):
            assert harness.ASK_USER_PERMISSION in _prompt(mode, plan_content=PLAN)

    def test_the_workspace_is_named(self):
        for mode in (PLAN_MODE, IMPLEMENT_MODE, "auto"):
            assert WORKSPACE in _prompt(mode, plan_content=PLAN)

    def test_the_task_survives(self):
        for mode in (PLAN_MODE, IMPLEMENT_MODE, "auto"):
            assert TASK in _prompt(mode, plan_content=PLAN)
