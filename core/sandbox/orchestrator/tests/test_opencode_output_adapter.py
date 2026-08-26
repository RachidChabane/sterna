"""Rules of the opencode translation that no single scenario pins.

`test_opencode_progress_goldens` replays two whole runs against the
pinned payloads. What it cannot show is why the translation is shaped
the way it is: each rule below is one the goldens depend on but express
only incidentally, through the particular stream each scenario carries.
"""

import json

from opencode_output_adapter import OpencodeOutputAdapter

WORKSPACE = "/workspace/chat-golden/repo"


def _stream(*events):
    return [json.dumps(event) for event in events]


def _system():
    return {"type": "system", "subtype": "init", "cwd": WORKSPACE,
            "mcp_servers": ["ask-user"]}


def _tool(name, tool_input, output="", status="completed", metadata=None, error=None):
    state = {"status": status, "input": tool_input, "output": output,
             "metadata": metadata if metadata is not None else {}}
    if error is not None:
        state["error"] = error
    return {"type": "tool_use",
            "part": {"type": "tool", "tool": name, "callID": "c1", "state": state}}


def _text(body):
    return {"type": "text", "part": {"type": "text", "text": body}}


def _step_finish(tokens=None, cost=0.0):
    part = {"type": "step-finish", "cost": cost}
    if tokens is not None:
        part["tokens"] = tokens
    return {"type": "step_finish", "part": part}


def _run(*events):
    adapter = OpencodeOutputAdapter()
    counted = 0
    for line in _stream(*events):
        if adapter.ingest(line):
            counted += 1
    return adapter, counted


class TestFileTracking:
    """The four file lists describe changes the user can review."""

    def test_a_refused_call_is_not_a_file_change(self):
        """A planning run's write is refused but still reported as a
        call; counting it would show the user a file that was never
        written."""
        adapter, _ = _run(
            _system(),
            _tool("write", {"filePath": "src/EVIL.py", "content": "x"},
                  status="error", error="The user has specified a rule"),
            _step_finish(),
        )
        assert adapter.files_created == set()

    def test_a_write_outside_the_workspace_is_not_a_file_change(self):
        """A planning run writes its plan into the job's own data
        directory. That is the harness's bookkeeping, not the user's
        workspace, and the plan reaches them as the run's summary."""
        adapter, _ = _run(
            _system(),
            _tool("write", {"filePath": "/tmp/claude-home-1/plans/a.md", "content": "x"},
                  output="Wrote file successfully.", metadata={"exists": False}),
            _step_finish(),
        )
        assert adapter.files_created == set()

    def test_a_workspace_write_is_recorded_relative_to_the_workspace(self):
        adapter, _ = _run(
            _system(),
            _tool("write", {"filePath": f"{WORKSPACE}/src/a.py", "content": "x"},
                  output="Wrote file successfully.", metadata={"exists": False}),
            _step_finish(),
        )
        assert adapter.files_created == {"src/a.py"}

    def test_writing_over_a_file_already_read_counts_as_a_modification(self):
        adapter, _ = _run(
            _system(),
            _tool("read", {"filePath": "src/a.py"}, output="<content>\n1: x\n</content>"),
            _step_finish(),
            _tool("write", {"filePath": "src/a.py", "content": "y"},
                  output="Wrote file successfully."),
            _step_finish(),
        )
        assert adapter.files_modified == {"src/a.py"}
        assert adapter.files_created == set()


class TestStepOrdering:
    """One assistant step yields its tool call before its prose.

    opencode emits the prose first, but the pinned progress payload puts
    a step's tool call ahead of its text — see the golden contract in
    `test_opencode_progress_goldens`. Step order therefore tracks how the
    model grouped parts into messages, not the order opencode emitted them.
    """

    def test_a_tool_call_precedes_prose_from_the_same_step(self):
        adapter, _ = _run(
            _system(),
            {"type": "step_start", "part": {"type": "step-start"}},
            _text("I'll read the session module first."),
            _tool("read", {"filePath": "src/a.py"}, output="<content>\n1: x\n</content>"),
            _step_finish(),
        )
        assert [step.type for step in adapter.steps] == [
            "system", "tool_call", "text", "tool_result",
        ]

    def test_prose_in_a_step_of_its_own_keeps_its_place(self):
        adapter, _ = _run(
            _system(),
            {"type": "step_start", "part": {"type": "step-start"}},
            _text("Starting step 1."),
            _step_finish(),
            {"type": "step_start", "part": {"type": "step-start"}},
            _tool("read", {"filePath": "src/a.py"}, output="<content>\n1: x\n</content>"),
            _step_finish(),
        )
        assert [step.type for step in adapter.steps] == [
            "system", "text", "tool_call", "tool_result",
        ]

    def test_a_line_that_yields_two_steps_counts_once(self):
        """`step_count` counts output lines that produced steps, not the
        steps themselves — see `coding_harness`'s module docstring."""
        adapter, counted = _run(
            _system(),
            _text("prose"),
            _tool("read", {"filePath": "src/a.py"}, output="<content>\n1: x\n</content>"),
        )
        assert len(adapter.steps) == 3
        assert counted == 2


class TestToolNaming:
    def test_an_mcp_tool_is_named_for_its_server(self):
        adapter, _ = _run(
            _system(),
            _tool("ask-user_ask_user", {"question": "Which?"}, output="Delete"),
            _step_finish(),
        )
        assert adapter.steps[1].tool == "mcp__ask-user__ask_user"

    def test_an_unoffered_tool_is_named_for_what_the_model_reached_for(self):
        """opencode reports the call as `invalid` and names the tool in
        the input, so the step still says what was attempted."""
        adapter, _ = _run(
            _system(),
            _tool("invalid", {"tool": "write", "error": "unavailable tool"},
                  status="error", error="unavailable tool"),
            _step_finish(),
        )
        assert adapter.steps[1].tool == "Write"
        assert adapter.files_created == set()


class TestReadRendering:
    def test_the_numbered_listing_is_read_back_as_the_file(self):
        listing = (
            "<path>/x</path>\n<type>file</type>\n<content>\n"
            "1: def f():\n2:     return 1\n\n(End of file - total 2 lines)\n</content>"
        )
        adapter, _ = _run(
            _system(), _tool("read", {"filePath": "a.py"}, output=listing), _step_finish()
        )
        assert adapter.steps[2].output == "def f():\n    return 1\n"

    def test_a_blank_line_in_the_file_survives(self):
        listing = "<content>\n1: a\n2:\n3: b\n\n(End of file - total 3 lines)\n</content>"
        adapter, _ = _run(
            _system(), _tool("read", {"filePath": "a.py"}, output=listing), _step_finish()
        )
        assert adapter.steps[2].output == "a\n\nb\n"


class TestUsage:
    def test_cost_is_the_session_total(self):
        adapter, _ = _run(
            _system(),
            _step_finish(tokens={"input": 10, "output": 2}, cost=0.0138),
            _step_finish(tokens={"input": 30, "output": 5}, cost=0.0274),
            {"type": "result", "subtype": "success", "result": "done"},
        )
        assert adapter.total_cost_usd == 0.0412

    def test_tokens_are_the_final_steps_own(self):
        """opencode reports per-step usage; the payload's token figure
        has always been the terminal turn's, not a sum."""
        adapter, _ = _run(
            _system(),
            _step_finish(tokens={"input": 10, "output": 2}),
            _step_finish(tokens={"input": 30, "output": 5}),
            {"type": "result", "subtype": "success", "result": "done"},
        )
        assert adapter.total_tokens == 35

    def test_a_failed_run_reports_its_error_and_no_summary(self):
        adapter, _ = _run(
            _system(),
            {"type": "result", "subtype": "error", "error": "opencode exited with code 1"},
        )
        assert adapter.error == "opencode exited with code 1"
        assert adapter.summary is None
        assert adapter.steps[-1].type == "error"


class TestMalformedInput:
    def test_a_line_that_is_not_json_is_skipped(self):
        adapter, counted = _run(_system())
        assert adapter.ingest("not json at all") is False
        assert counted == 1

    def test_an_unknown_line_type_is_skipped(self):
        adapter, counted = _run(_system(), {"type": "session.diff", "part": {}})
        assert counted == 1
