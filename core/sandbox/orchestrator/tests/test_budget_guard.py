"""Mid-run quota enforcement (budget_guard.py) against a real run.

The guard is driven by the same object the runner drives — the adapter
`coding_harness.create_adapter` hands back, fed one line at a time — so
these tests fail if the adapter ever stops publishing a running cost
while the run is still going.

`fixtures/opencode_budget_run.jsonl` is a recorded ``opencode run
--format json`` stream, captured through `opencode_run_wrapper` and so
carrying the ``system`` and ``result`` lines that bracket it. Four steps
close before the run ends, each costing $0.0105.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from budget_guard import over_budget, terminate_command  # noqa: E402
from coding_harness import OPENCODE, AgentOutputAdapter, create_adapter  # noqa: E402

RECORDED_RUN = Path(__file__).resolve().parent / "fixtures" / "opencode_budget_run.jsonl"

LINE_RESULT = "result"

#: Cost of one step in the recorded run, and the number of steps in it.
STEP_COST_USD = 0.0105
STEPS_IN_RUN = 4

#: A ceiling the recorded run crosses on its second step.
CEILING_CROSSED_MID_RUN = STEP_COST_USD * 1.5
#: A ceiling the whole recorded run stays under.
CEILING_NEVER_REACHED = STEP_COST_USD * STEPS_IN_RUN * 2


def _recorded_lines():
    return [line for line in RECORDED_RUN.read_text().split("\n") if line.strip()]


def _result_line_index(lines):
    for index, line in enumerate(lines):
        if json.loads(line).get("type") == LINE_RESULT:
            return index
    raise AssertionError("The recorded run has no result line.")


def _first_line_over(budget_usd):
    """Index of the line after which the guard first reports over budget."""
    adapter = create_adapter(OPENCODE)
    for index, line in enumerate(_recorded_lines()):
        adapter.ingest(line)
        if over_budget(adapter, budget_usd):
            return index
    return None


def _step_finish_line(cost_usd):
    """One ``step_finish`` line reporting `cost_usd` for its step."""
    return json.dumps(
        {
            "type": "step_finish",
            "part": {
                "type": "step-finish",
                "tokens": {"input": 1000, "output": 500},
                "cost": cost_usd,
            },
        }
    )


class TestAgainstARecordedRun:
    def test_the_adapter_the_runner_builds_satisfies_the_guard(self):
        """The guard reads whatever `create_adapter` hands the runner."""
        assert isinstance(create_adapter(OPENCODE), AgentOutputAdapter)

    def test_the_guard_trips_before_the_run_ends(self):
        """The whole point: the ceiling is crossed while the job is running."""
        crossed_at = _first_line_over(CEILING_CROSSED_MID_RUN)

        assert crossed_at is not None, "The guard never tripped on the recorded run."
        assert crossed_at < _result_line_index(_recorded_lines())

    def test_the_guard_trips_on_the_step_that_crosses_the_ceiling(self):
        """Not one step later: the second step's cost is what crosses it."""
        lines = _recorded_lines()
        crossed_at = _first_line_over(CEILING_CROSSED_MID_RUN)

        assert json.loads(lines[crossed_at])["type"] == "step_finish"
        step_finishes_so_far = sum(
            1 for line in lines[: crossed_at + 1]
            if json.loads(line)["type"] == "step_finish"
        )
        assert step_finishes_so_far == 2

    def test_a_run_under_the_ceiling_is_never_stopped(self):
        assert _first_line_over(CEILING_NEVER_REACHED) is None

    def test_no_ceiling_is_never_crossed(self):
        """budget_usd=None -> never over budget, however much was spent."""
        assert _first_line_over(None) is None

    def test_the_running_cost_is_the_sum_of_the_steps_closed_so_far(self):
        adapter = create_adapter(OPENCODE)
        for line in _recorded_lines():
            adapter.ingest(line)

        assert adapter.running_cost_usd == round(STEP_COST_USD * STEPS_IN_RUN, 10)


class TestTheCeilingItself:
    def test_a_job_that_has_spent_nothing_is_under_any_ceiling(self):
        assert over_budget(create_adapter(OPENCODE), 1.0) is False

    def test_at_the_ceiling_is_not_yet_over_it(self):
        """Exactly at the ceiling is not over it — only crossing it stops the job."""
        adapter = create_adapter(OPENCODE)
        adapter.ingest(_step_finish_line(1.0))

        assert over_budget(adapter, 1.0) is False

    def test_over_the_ceiling_stops_the_job(self):
        adapter = create_adapter(OPENCODE)
        adapter.ingest(_step_finish_line(1.01))

        assert over_budget(adapter, 1.0) is True

    def test_zero_budget_allows_a_job_that_has_spent_nothing(self):
        """A user with $0 remaining can still start a job — the first
        nonzero cost observed is what stops it, not the ceiling itself."""
        assert over_budget(create_adapter(OPENCODE), 0.0) is False

    def test_zero_budget_stops_at_first_nonzero_cost(self):
        adapter = create_adapter(OPENCODE)
        adapter.ingest(_step_finish_line(0.0001))

        assert over_budget(adapter, 0.0) is True


class TestTerminateCommand:
    def test_targets_the_given_pid(self):
        cmd = terminate_command("4242")
        assert cmd[0] == "sh"
        assert "4242" in cmd[-1]

    def test_is_best_effort(self):
        """A missing process must not fail the command (`|| true`)."""
        cmd = terminate_command("4242")
        assert "|| true" in cmd[-1]
