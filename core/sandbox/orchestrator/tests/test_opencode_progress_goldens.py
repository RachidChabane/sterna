"""The opencode harness against the pinned progress-store payloads.

`test_coding_agent_progress_goldens` pins what the progress store holds
for a plan-mode and an implement-mode run of the Claude Code harness.
The chat layer polls that payload, so it is a contract the harness must
not move: the same two scenarios, run through opencode, have to leave
the store holding the same bytes.

Each scenario replays a recorded opencode stream
(``*_opencode_output.jsonl``) through `OpencodeOutputAdapter` on the
loop `_execute_with_streaming` runs — ingest one line, write progress
when it produced a step — and compares the result against the very same
golden files the Claude scenarios are compared against.

The recorded streams carry opencode's own line shapes: ``step_start`` /
``text`` / ``tool_use`` / ``step_finish`` from ``opencode run --format
json``, bracketed by the ``system`` and ``result`` lines the in-sandbox
wrapper prints.
"""

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import coding_agent_runner
from coding_agent_runner import CodingAgentRunner, get_progress_from_store
from opencode_output_adapter import OpencodeOutputAdapter

GOLDENS_DIR = Path(__file__).resolve().parent / "goldens"

USER_ID = "user-golden"
CHAT_ID = "chat-golden"
STORE_KEY = f"{USER_ID}:{CHAT_ID}"
PROGRESS_FILE = "/tmp/agents/coding-agent-golden/.coding-agent-progress.json"

SUCCESS_EXIT_CODE = 0
FILE_LIST_FIELDS = ("files_created", "files_modified", "files_read", "files_deleted")

MID_RUN_KEY = "mid_run"
FINAL_KEY = "final"

PLAN_MODE_SNAPSHOT_TOOL = "Read"
IMPLEMENT_MODE_SNAPSHOT_TOOL = "mcp__ask-user__ask_user"


def _sorted_file_lists(progress):
    """The payload with only its set-derived lists put in a stable order."""
    stable = copy.deepcopy(progress)
    for field in FILE_LIST_FIELDS:
        stable[field] = sorted(stable[field])
    return stable


def _replay(stream_name, snapshot_tool):
    """Drive one recorded opencode stream through the runner's writer."""
    runner = CodingAgentRunner(
        sandbox_executor=MagicMock(), user_id=USER_ID, chat_id=CHAT_ID
    )
    container = MagicMock()
    adapter = OpencodeOutputAdapter()
    step_count = 0
    mid_run = None

    try:
        runner._write_progress_file(container, PROGRESS_FILE, adapter, step_count)

        for line in (GOLDENS_DIR / stream_name).read_text().split("\n"):
            if not line.strip():
                continue
            emitted_from = len(adapter.steps)
            if not adapter.ingest(line):
                continue
            step_count += 1
            runner._write_progress_file(container, PROGRESS_FILE, adapter, step_count)
            emitted = adapter.steps[emitted_from:]
            if mid_run is None and any(step.tool == snapshot_tool for step in emitted):
                mid_run = _sorted_file_lists(get_progress_from_store(USER_ID, CHAT_ID))

        runner._write_progress_file(
            container,
            PROGRESS_FILE,
            adapter,
            step_count,
            completed=True,
            exit_code=SUCCESS_EXIT_CODE,
        )
        final = _sorted_file_lists(get_progress_from_store(USER_ID, CHAT_ID))
    finally:
        coding_agent_runner._progress_store.pop(STORE_KEY, None)

    assert mid_run is not None, f"No step used {snapshot_tool} in {stream_name}"
    return {MID_RUN_KEY: mid_run, FINAL_KEY: final}


def _assert_matches_golden(name, payload):
    """Compare against the golden the Claude scenario is pinned to."""
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path = GOLDENS_DIR / f"{name}.json"
    assert path.exists(), f"Missing golden {path}."
    assert serialized == path.read_text(), (
        f"opencode progress payload diverged from {path.name}, "
        "which the Claude Code harness still matches."
    )


def test_plan_mode_progress_store_payloads():
    """A read-only planning run: steps accumulate, no file is written."""
    snapshots = _replay("plan_mode_opencode_output.jsonl", PLAN_MODE_SNAPSHOT_TOOL)

    assert snapshots[FINAL_KEY]["files_created"] == []
    assert snapshots[FINAL_KEY]["files_modified"] == []
    assert snapshots[FINAL_KEY]["summary"].startswith("# Implementation Plan:")

    _assert_matches_golden("plan_mode_progress_store", snapshots)


def test_implement_mode_progress_store_payloads():
    """An implementing run: a question mid-flight, then file changes."""
    snapshots = _replay(
        "implement_mode_opencode_output.jsonl", IMPLEMENT_MODE_SNAPSHOT_TOOL
    )

    assert snapshots[FINAL_KEY]["files_created"] == [
        "src/auth/archive.py",
        "tests/test_archive.py",
    ]
    assert snapshots[FINAL_KEY]["total_cost_usd"] == 0.1874

    _assert_matches_golden("implement_mode_progress_store", snapshots)


def test_usage_is_withheld_until_the_run_ends():
    """Mid-run payloads report no usage, as the Claude harness does.

    opencode reports tokens and cost on every step; the Claude CLI
    reports them once, in its terminal event. The adapter accrues
    silently so a poll taken mid-run cannot show a partial figure the
    chat layer would have to reconcile later.
    """
    snapshots = _replay("implement_mode_opencode_output.jsonl", IMPLEMENT_MODE_SNAPSHOT_TOOL)

    assert snapshots[MID_RUN_KEY]["total_cost_usd"] == 0.0
    assert snapshots[MID_RUN_KEY]["total_tokens"] == 0
    assert snapshots[FINAL_KEY]["total_tokens"] == 45180
