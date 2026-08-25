"""Pricing one generation from the catalog row the request's model holds.

The agent core asks its `CostAccountantPort` to split a generation's
cost the moment the provider reports usage, from inside the running
loop. A catalog lookup is a database read, so the prices are resolved
once per request -- before the loop starts, where a synchronous query
is safe -- and the accountant that runs inside the loop holds nothing
but the two numbers it multiplies by.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from ..agent_core.events import Usage
from ..agent_core.graph import CostBreakdown
from ..catalog_service import CatalogService
from ..pricing_config import PRICE_STORAGE_UNIT


@dataclasses.dataclass(frozen=True, slots=True)
class CatalogPriceCostAccountant:
    """Prices a generation from per-token prices resolved ahead of the turn.

    Catalog prices are quoted per `PRICE_STORAGE_UNIT` tokens; the
    per-token price is derived once and multiplied by the count, which
    is the arithmetic the endpoint's cost figures are produced by.
    """

    prompt_price_per_token: float
    completion_price_per_token: float

    @classmethod
    def for_model(cls, model_id: str) -> "CatalogPriceCostAccountant":
        """The accountant for `model_id`, reading its catalog prices now.

        A model the catalog cannot price is accounted at zero, which is
        what a turn whose model carries no prices already reports.
        """

        try:
            pricing = CatalogService().get_model_pricing(model_id)
        except Exception:
            pricing = {}
        return cls(
            prompt_price_per_token=_per_token(pricing.get("prompt_price")),
            completion_price_per_token=_per_token(pricing.get("completion_price")),
        )

    def account(
        self, *, model: str, usage: Usage, reported_cost: Optional[float]
    ) -> CostBreakdown:
        prompt = self.prompt_price_per_token * usage.prompt_tokens
        completion = self.completion_price_per_token * usage.completion_tokens
        return CostBreakdown(
            total=prompt + completion, prompt=prompt, completion=completion
        )


def _per_token(quoted_price: Optional[float]) -> float:
    return (quoted_price or 0) / PRICE_STORAGE_UNIT
