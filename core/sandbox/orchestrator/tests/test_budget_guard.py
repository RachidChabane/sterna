"""Tests for mid-run quota enforcement (budget_guard.py)."""
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from budget_guard import over_budget, terminate_command  # noqa: E402


@dataclass
class FakeAdapter:
    total_cost_usd: float


class TestOverBudget:
    def test_no_ceiling_never_exceeded(self):
        """budget_usd=None -> never over budget, however much was spent."""
        assert over_budget(FakeAdapter(total_cost_usd=999.0), None) is False

    def test_under_ceiling_not_exceeded(self):
        assert over_budget(FakeAdapter(total_cost_usd=0.5), 1.0) is False

    def test_at_ceiling_not_yet_exceeded(self):
        """Exactly at the ceiling is not over it — only crossing it stops the job."""
        assert over_budget(FakeAdapter(total_cost_usd=1.0), 1.0) is False

    def test_over_ceiling_exceeded(self):
        assert over_budget(FakeAdapter(total_cost_usd=1.01), 1.0) is True

    def test_zero_budget_allows_a_job_that_has_spent_nothing(self):
        """A user with $0 remaining can still start a job — the first
        nonzero cost observed is what stops it, not the ceiling itself."""
        assert over_budget(FakeAdapter(total_cost_usd=0.0), 0.0) is False

    def test_zero_budget_stops_at_first_nonzero_cost(self):
        assert over_budget(FakeAdapter(total_cost_usd=0.0001), 0.0) is True


class TestTerminateCommand:
    def test_targets_the_given_pid(self):
        cmd = terminate_command("4242")
        assert cmd[0] == "sh"
        assert "4242" in cmd[-1]

    def test_is_best_effort(self):
        """A missing process must not fail the command (`|| true`)."""
        cmd = terminate_command("4242")
        assert "|| true" in cmd[-1]
