"""Harness selection and the output-adapter port the progress store reads.

A coding-agent job is executed by one of several CLI harnesses. Each
harness prints its own stream format, so each supplies an *output
adapter*: the object `CodingAgentRunner._write_progress_file` reads to
build the progress payload the chat layer polls.

The adapter contract is deliberately narrow — the attributes below plus
`ingest` — so a harness can be swapped without the progress payload
changing shape.

``total_cost_usd`` and ``total_tokens`` are the payload's usage fields,
carrying the run's own figures once it has ended. ``running_cost_usd``
is the separate live total `budget_guard.over_budget` reads while the
run is still going.

``ingest`` returns whether the line produced any step. The caller adds
one to ``step_count`` per truthy return, so ``step_count`` counts
*output lines that produced steps* while ``total_steps`` counts the
steps themselves. The two diverge whenever one line yields more than
one step, and that divergence is part of the pinned payload.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Set, runtime_checkable

from opencode_output_adapter import OpencodeOutputAdapter

OPENCODE = "opencode"

#: The modes a job runs in. Planning explores and delivers a plan;
#: implementing follows one that was approved; anything else is a task
#: the agent carries out directly.
PLAN_MODE = "plan"
IMPLEMENT_MODE = "implement"

SUPPORTED_HARNESSES = (OPENCODE,)

#: Environment variable naming the harness for jobs that do not pick one.
HARNESS_ENV_VAR = "CODING_AGENT_HARNESS"

DEFAULT_HARNESS = OPENCODE


class AgentStep(Protocol):
    """One entry in the progress payload's ``steps`` list."""

    type: str
    tool: Optional[str]
    content: Optional[str]
    input: Optional[Dict[str, Any]]
    output: Optional[str]


@runtime_checkable
class AgentOutputAdapter(Protocol):
    """Accumulates one run's output into the progress payload's fields."""

    steps: List[Any]
    files_created: Set[str]
    files_modified: Set[str]
    files_read: Set[str]
    files_deleted: Set[str]
    error: Optional[str]
    summary: Optional[str]
    total_cost_usd: float
    total_tokens: int
    running_cost_usd: float

    def ingest(self, line: str) -> bool:
        """Consume one output line; report whether it produced a step."""


def resolve_harness(requested: Optional[str] = None) -> str:
    """Pick the harness for a job.

    An explicit request wins; otherwise the environment decides, and an
    unset or unrecognized value falls back to the default harness.
    """
    candidate = (requested or os.environ.get(HARNESS_ENV_VAR) or "").strip().lower()
    if candidate in SUPPORTED_HARNESSES:
        return candidate
    return DEFAULT_HARNESS


@dataclass
class RunOutcome:
    """What one finished run reports, whichever harness produced it."""

    success: bool
    summary: Optional[str]
    steps: List[Any]
    files_created: List[str]
    files_modified: List[str]
    error: Optional[str]
    total_tokens: int
    total_cost_usd: float


def create_adapter(harness: str, workspace_path: str = "") -> AgentOutputAdapter:
    """The output adapter that reads a running job's stream.

    `harness` is the extension point a second harness would switch on;
    `SUPPORTED_HARNESSES` names every harness `resolve_harness` can hand
    back, and opencode is the only entry in it.
    """
    return OpencodeOutputAdapter(workspace_path)


def parse_run_output(
    harness: str, output: str, workspace_path: str = ""
) -> RunOutcome:
    """Replay a finished run's whole output into its outcome.

    `harness` is the extension point a second harness would switch on;
    `SUPPORTED_HARNESSES` names every harness `resolve_harness` can hand
    back, and opencode is the only entry in it.
    """
    adapter = OpencodeOutputAdapter(workspace_path)
    for line in output.split("\n"):
        adapter.ingest(line)
    return RunOutcome(
        success=adapter.error is None and bool(adapter.steps),
        summary=adapter.summary,
        steps=adapter.steps,
        files_created=sorted(adapter.files_created),
        files_modified=sorted(adapter.files_modified),
        error=adapter.error,
        total_tokens=adapter.total_tokens,
        total_cost_usd=adapter.total_cost_usd,
    )
