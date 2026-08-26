"""Golden payloads for the progress store a coding-agent run fills.

`CodingAgentRunner._write_progress_file` is the only writer of the
in-memory progress store, and `get_progress_from_store` serves whatever
it last wrote to `/coding-agent/progress`. The dict it builds -- its
field names, their order, the per-step shape, and the counters -- is the
contract the chat layer polls, so it is pinned here byte for byte,
independently of anything Django-side.

Each scenario replays a recorded CLI stream (``*_cli_output.jsonl``)
through the real `ClaudeOutputParser` on the same loop
`_execute_with_streaming` runs: parse one line, append the returned step,
write progress. Two snapshots are pinned per scenario -- one taken
mid-run, while the agent is still working, and the terminal one -- so a
replacement adapter has a target for both the streaming and the final
payload.

The four file lists are built from sets, so their order is not part of
the contract and is the one value sorted before comparison. Everything
else is compared as written.

Set ``GOLDEN_UPDATE=1`` to rewrite the goldens from current behavior.
"""

import copy
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import coding_agent_runner
from claude_output_parser import ClaudeOutputParser
from coding_agent_runner import CodingAgentRunner, get_progress_from_store

GOLDENS_DIR = Path(__file__).resolve().parent / "goldens"
UPDATE_ENV_VAR = "GOLDEN_UPDATE"

USER_ID = "user-golden"
CHAT_ID = "chat-golden"
STORE_KEY = f"{USER_ID}:{CHAT_ID}"
PROGRESS_FILE = "/tmp/agents/coding-agent-golden/.coding-agent-progress.json"

SUCCESS_EXIT_CODE = 0
FILE_LIST_FIELDS = ("files_created", "files_modified", "files_read", "files_deleted")

MID_RUN_KEY = "mid_run"
FINAL_KEY = "final"

# Tool whose call marks the mid-run snapshot in each scenario: the last
# read before the plan is written, and the question the agent blocks on.
PLAN_MODE_SNAPSHOT_TOOL = "Read"
IMPLEMENT_MODE_SNAPSHOT_TOOL = "mcp__ask-user__ask_user"


def _sorted_file_lists(progress):
    """The payload with only its set-derived lists put in a stable order."""
    stable = copy.deepcopy(progress)
    for field in FILE_LIST_FIELDS:
        stable[field] = sorted(stable[field])
    return stable


def _replay(cli_output_name, snapshot_tool):
    """Drive one recorded CLI stream through the runner's progress writer.

    Mirrors `_execute_with_streaming`'s inner loop exactly: an initial
    write before any output, one write per parsed step, and a terminal
    write carrying `completed` and the exit code.
    """
    runner = CodingAgentRunner(
        sandbox_executor=MagicMock(), user_id=USER_ID, chat_id=CHAT_ID
    )
    container = MagicMock()
    parser = ClaudeOutputParser()
    step_count = 0
    mid_run = None

    try:
        runner._write_progress_file(container, PROGRESS_FILE, parser, step_count)

        for line in (GOLDENS_DIR / cli_output_name).read_text().split("\n"):
            if not line.strip():
                continue
            step = parser.parse_line(line)
            if not step:
                continue
            parser.steps.append(step)
            step_count += 1
            runner._write_progress_file(container, PROGRESS_FILE, parser, step_count)
            if step.tool == snapshot_tool and mid_run is None:
                mid_run = _sorted_file_lists(get_progress_from_store(USER_ID, CHAT_ID))

        runner._write_progress_file(
            container,
            PROGRESS_FILE,
            parser,
            step_count,
            completed=True,
            exit_code=SUCCESS_EXIT_CODE,
        )
        final = _sorted_file_lists(get_progress_from_store(USER_ID, CHAT_ID))
    finally:
        coding_agent_runner._progress_store.pop(STORE_KEY, None)

    assert mid_run is not None, f"No step used {snapshot_tool} in {cli_output_name}"
    return {MID_RUN_KEY: mid_run, FINAL_KEY: final}


def _assert_matches_golden(name, payload):
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path = GOLDENS_DIR / f"{name}.json"

    if os.environ.get(UPDATE_ENV_VAR) == "1":
        path.write_text(serialized)
        return

    assert path.exists(), f"Missing golden {path}. Run with {UPDATE_ENV_VAR}=1 to create it."
    assert serialized == path.read_text(), f"Progress payload diverged from {path.name}."


def test_plan_mode_progress_store_payloads():
    """A read-only planning run: steps accumulate, no file is written."""
    snapshots = _replay("plan_mode_cli_output.jsonl", PLAN_MODE_SNAPSHOT_TOOL)

    assert snapshots[FINAL_KEY]["completed"] is True
    assert snapshots[FINAL_KEY]["files_created"] == []
    assert snapshots[FINAL_KEY]["files_modified"] == []
    assert snapshots[FINAL_KEY]["summary"].startswith("# Implementation Plan:")
    assert snapshots[MID_RUN_KEY]["completed"] is False

    _assert_matches_golden("plan_mode_progress_store", snapshots)


def test_implement_mode_progress_store_payloads():
    """An implementing run: a question mid-flight, then file changes."""
    snapshots = _replay("implement_mode_cli_output.jsonl", IMPLEMENT_MODE_SNAPSHOT_TOOL)

    assert snapshots[FINAL_KEY]["completed"] is True
    assert snapshots[FINAL_KEY]["files_created"] == [
        "src/auth/archive.py",
        "tests/test_archive.py",
    ]
    assert snapshots[FINAL_KEY]["files_modified"] == ["src/auth/session.py"]
    assert snapshots[FINAL_KEY]["total_cost_usd"] == 0.1874

    _assert_matches_golden("implement_mode_progress_store", snapshots)


def test_progress_write_replaces_the_stored_job_token():
    """A progress write leaves nothing in the store but the payload.

    `run_coding_agent` puts the run's `_job_token` under the same key
    before the agent starts, and `/mcp/ask-user` rejects a relayed
    question whose token does not match the stored one. The first
    progress write replaces the whole entry, so the token is gone before
    the CLI produces its first line.
    """
    runner = CodingAgentRunner(
        sandbox_executor=MagicMock(), user_id=USER_ID, chat_id=CHAT_ID
    )
    coding_agent_runner._progress_store[STORE_KEY] = {"_job_token": "token-golden"}

    try:
        runner._write_progress_file(
            MagicMock(), PROGRESS_FILE, ClaudeOutputParser(), 0
        )
        stored = get_progress_from_store(USER_ID, CHAT_ID)
    finally:
        coding_agent_runner._progress_store.pop(STORE_KEY, None)

    assert "_job_token" not in stored


def test_progress_store_holds_no_pending_question():
    """The question a run blocks on is not part of the stored payload.

    `/coding-agent/progress` merges it in from the orchestrator's own
    `_pending_questions` map, so a reader of the store alone never sees
    one -- including for a run whose CLI stream calls `ask_user`.
    """
    snapshots = _replay("implement_mode_cli_output.jsonl", IMPLEMENT_MODE_SNAPSHOT_TOOL)

    for snapshot in snapshots.values():
        assert "pending_question" not in snapshot
