"""The opencode harness against the pinned progress-store payloads.

`CodingAgentRunner._write_progress_file` is the only writer of the
in-memory progress store, and `get_progress_from_store` serves whatever
it last wrote to `/coding-agent/progress`. The dict it builds — its
field names, their order, the per-step shape, and the counters — is the
contract the chat layer polls, so a plan-mode and an implement-mode
scenario are pinned here byte for byte, independently of anything
Django-side.

Each scenario replays a recorded opencode stream
(``*_opencode_output.jsonl``) through `OpencodeOutputAdapter` on the
loop `_execute_with_streaming` runs — ingest one line, write progress
when it produced a step. Two snapshots are pinned per scenario — one
taken mid-run, while the agent is still working, and the terminal one.

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
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path = GOLDENS_DIR / f"{name}.json"
    assert path.exists(), f"Missing golden {path}."
    assert serialized == path.read_text(), f"Progress payload diverged from {path.name}."


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


def test_the_store_withholds_usage_until_the_run_ends():
    """Mid-run payloads report no usage.

    opencode reports tokens and cost on every step, and the adapter
    tracks the cost of the steps closed so far so a budget check has a
    figure to read (`budget_guard.over_budget`). The payload the chat
    layer polls carries neither until the run ends, so a poll taken
    mid-run cannot show a partial figure it would have to reconcile
    later.
    """
    snapshots = _replay("implement_mode_opencode_output.jsonl", IMPLEMENT_MODE_SNAPSHOT_TOOL)

    assert snapshots[MID_RUN_KEY]["total_cost_usd"] == 0.0
    assert snapshots[MID_RUN_KEY]["total_tokens"] == 0
    assert snapshots[FINAL_KEY]["total_tokens"] == 45180


def test_progress_write_replaces_the_stored_job_token():
    """A progress write leaves nothing in the store but the payload.

    `run_coding_agent` puts the run's `_job_token` under the same key
    before the agent starts, and `/mcp/ask-user` rejects a relayed
    question whose token does not match the stored one. The first
    progress write replaces the whole entry, so the token is gone before
    opencode produces its first line.
    """
    runner = CodingAgentRunner(
        sandbox_executor=MagicMock(), user_id=USER_ID, chat_id=CHAT_ID
    )
    coding_agent_runner._progress_store[STORE_KEY] = {"_job_token": "token-golden"}

    try:
        runner._write_progress_file(
            MagicMock(), PROGRESS_FILE, OpencodeOutputAdapter(), 0
        )
        stored = get_progress_from_store(USER_ID, CHAT_ID)
    finally:
        coding_agent_runner._progress_store.pop(STORE_KEY, None)

    assert "_job_token" not in stored


def test_progress_store_holds_no_pending_question():
    """The question a run blocks on is not part of the stored payload.

    `/coding-agent/progress` merges it in from the orchestrator's own
    `_pending_questions` map, so a reader of the store alone never sees
    one — including for a run whose stream calls `ask_user`.
    """
    snapshots = _replay("implement_mode_opencode_output.jsonl", IMPLEMENT_MODE_SNAPSHOT_TOOL)

    for snapshot in snapshots.values():
        assert "pending_question" not in snapshot
