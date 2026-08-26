"""The running figures one V2 chat turn reports on the wire and bills on.

A turn spans as many generations as it takes model/tool round trips,
and the V2 stream reports the totals of the whole turn on every
`usage_update` and on `done`: a client that stops reading early holds
figures for everything that ran, not for the last generation alone.
The same totals are what the aggregate usage row is written from, so
one object carries both and the two cannot drift apart.

Tool cost is tallied separately from generation cost because the two
are billed differently: the displayed figure is every dollar the tools
reported, while the billable figure excludes what a tool already wrote
its own usage row for.
"""

from __future__ import annotations

import dataclasses
from typing import List, Sequence

from ..agent.cost_ledger import extract_billable_tool_costs
from ..agent_core.events import Usage


@dataclasses.dataclass(slots=True)
class TurnAccounting:
    """Everything one turn has spent so far, accumulated as it streams."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    tool_cost: float = 0.0
    image_generation_cost: float = 0.0
    generation_ids: List[str] = dataclasses.field(default_factory=list)
    settled: bool = False
    """Whether the turn's aggregate usage row has been written."""

    def record_generation_id(self, generation_id: str) -> None:
        """Remember a generation this turn spanned, without repeating one."""

        if generation_id not in self.generation_ids:
            self.generation_ids.append(generation_id)

    def record_generation_cost(
        self,
        *,
        usage: Usage,
        cost: float,
        prompt_cost: float,
        completion_cost: float,
    ) -> None:
        """Fold one generation's usage and cost into the turn's totals."""

        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.cost += cost
        self.prompt_cost += prompt_cost
        self.completion_cost += completion_cost

    def record_tool_results(self, results: Sequence[dict]) -> None:
        """Fold one round of tool results into the turn's tool cost."""

        billable, image_generation = extract_billable_tool_costs(results)
        self.tool_cost += billable
        self.image_generation_cost += image_generation

    @property
    def usage(self) -> Usage:
        """The turn's token counts, in the shape the wire reports them."""

        return Usage(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
        )

    @property
    def reported_cost(self) -> float:
        """What the stream shows: every generation and every tool dollar."""

        return self.cost + self.tool_cost

    @property
    def last_generation_id(self) -> str | None:
        return self.generation_ids[-1] if self.generation_ids else None
