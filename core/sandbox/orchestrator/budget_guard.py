"""Mid-run quota enforcement for a coding-agent job.

Cost accrues on the harness's output adapter as its stream is ingested
(`AgentOutputAdapter.total_cost_usd` in `coding_harness.py`). The runner's
poll loop calls `over_budget` after each ingested line and, once the
running cost has crossed the ceiling Django computed for the job, sends
the harness process the same termination signal used elsewhere for a
timed-out run — the process exits, the runner's normal zombie/exit-code
handling takes over, and the job settles for whatever it actually spent.

A harness has no notion of its own budget: this module is the only place
that compares cost against a ceiling, so enforcement is identical
regardless of which harness the job runs on.
"""

from typing import Optional, Protocol


class CostTracking(Protocol):
    """The one attribute a budget check needs from an output adapter."""

    total_cost_usd: float


def over_budget(adapter: CostTracking, budget_usd: Optional[float]) -> bool:
    """True once `adapter`'s running cost has crossed `budget_usd`.

    `budget_usd` of `None` means no ceiling is enforced for this job. A
    ceiling of exactly `0.0` is still meaningful (a user with no budget
    left) and is crossed by the first nonzero cost observed — strict
    inequality so a job that has spent nothing yet is allowed to start.
    """
    return budget_usd is not None and adapter.total_cost_usd > budget_usd


def terminate_command(pid: str) -> list:
    """The shell command that ends a job's process gracefully.

    A bare kill is best-effort: the process may already be gone by the
    time this runs, so a failure to signal it is swallowed rather than
    surfaced as an execution error.
    """
    return ["sh", "-c", f"kill -TERM {pid} 2>/dev/null || true"]
