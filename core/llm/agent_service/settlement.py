"""The usage row a turn is billed on, and how a shared event reaches the wire.

Both streaming endpoints end a turn the same way: the tokens and the
tool dollars the whole turn spent are written as one aggregate usage
row, before the `done` event that reports them reaches the client. The
step is one call rather than one per endpoint, so a change to what a
turn bills cannot land on one stack and miss the other.
"""

from __future__ import annotations

from typing import Any, Dict

from ..agent.cost_ledger import CostLedger
from ..agent_core import sse
from .accounting import TurnAccounting

EVENT_FIELD = "event"
DATA_FIELD = "data"


async def settle_turn(accounting: TurnAccounting, *, user_id: str, model: str) -> None:
    """Write the aggregate usage row for what this turn has spent."""

    ledger = CostLedger(lambda: user_id, model)
    await ledger.record_chat_aggregate_usage(
        accounting.prompt_tokens,
        accounting.completion_tokens,
        accounting.tool_cost,
        accounting.image_generation_cost,
    )
    accounting.settled = ledger.final_usage_recorded


def rendered(event: Dict[str, Any]) -> str:
    """One event mapping from the shared SSE helpers, as the frame it writes."""

    return sse.render_frame(event[EVENT_FIELD], event[DATA_FIELD])
