"""Cost accounting for one streamed chat turn.

Two collaborators live here:

* ``extract_billable_tool_costs`` -- the *classifier*: decides which
  tool-reported ``cost_usd`` values the chat-aggregate row may re-bill.
* ``CostLedger`` -- the *ledger*: resolves pricing, converts token counts
  to dollars, and writes the aggregate ``UsageLog`` rows. It owns no
  streaming concerns and emits no SSE events.

Django model imports stay inside methods: this package is imported at
Django app-loading time via ``llm.agent_service``.
"""

import logging
from typing import Callable, Optional

from asgiref.sync import sync_to_async

from ..agent_tool_handlers import CODING_AGENT_TOOL_NAMES
from ..catalog_service import CatalogService
from ..pricing_config import PRICE_STORAGE_UNIT

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS):
# level/handlers are inherited by propagation, only the record name differs.
logger = logging.getLogger(__name__)

# Tools whose per-image UsageLog row is written by `image_tools._record_billing`.
# Their `cost_usd` must NOT be re-billed by the chat aggregate row — see
# `extract_billable_tool_costs` below, which excludes these tool names from
# the chat-level cost rollup to avoid double-billing.
IMAGE_GEN_TOOL_NAMES = frozenset({"generate_image", "edit_image"})


def extract_billable_tool_costs(tool_results) -> tuple:
    """Classify `cost_usd` returned by tool results for chat-row billing.

    Shared by BOTH streaming paths (`_astream_with_direct_client` and
    `astream_chat`) so the dedup semantics cannot drift between them:

    - Coding-agent tools bill their own dedicated ``CODE_SESSION`` UsageLog
      row at the tool layer — skipped entirely here.
    - Non-OpenRouter providers bill via their own ``_record_billing`` path
      (e.g. Google AI Studio image gen, video gen) — skipped here.
    - OpenRouter image-gen ALSO writes a per-image UsageLog row in
      ``image_tools._record_billing``; its cost is returned separately as
      ``image_gen_cost`` so callers can subtract it from the aggregate
      OPENROUTER/CHAT bill (same dollars must not appear in two rows).

    Returns:
        (tool_cost, image_gen_cost): total accumulated OpenRouter tool cost
        for this batch, and the subset of it that is already billed by the
        per-image IMAGE_GENERATION rows.
    """
    tool_cost = 0.0
    image_gen_cost = 0.0
    for tr in tool_results:
        result = tr.get("result", {})
        if not isinstance(result, dict) or "cost_usd" not in result:
            continue
        tool_name = tr.get("tool_call", {}).get("function", {}).get("name", "")
        if tool_name in CODING_AGENT_TOOL_NAMES:
            continue
        provider = result.get("provider")
        if provider and provider != "openrouter":
            continue
        cost = result.get("cost_usd", 0)
        if isinstance(cost, (int, float)) and cost > 0:
            tool_cost += cost
            if tool_name in IMAGE_GEN_TOOL_NAMES:
                image_gen_cost += cost
            logger.info(
                f"[LangChain] Tool cost accumulated ({tool_name}): ${cost:.6f}"
            )
    return tool_cost, image_gen_cost


class CostLedger:
    """Prices a turn and writes its aggregate usage rows.

    Holds only what billing needs (the user id, the catalog model id) plus
    the ``final_usage_recorded`` flag the view's disconnect handler reads.
    """

    def __init__(self, resolve_user_id: Callable[[], Optional[str]], model_id: str):
        # The user id is read through a callable rather than snapshotted:
        # the owning agent's `_user_id` is assignable after construction.
        self._resolve_user_id = resolve_user_id
        self._model_id = model_id
        self._billing_origin = None
        self.final_usage_recorded = False

    @property
    def _user_id(self):
        return self._resolve_user_id()

    async def resolve_billing_origin(self) -> str:
        """Resolve and cache the billing_origin for the current user.

        Returns 'byok' iff the user has a provider-scoped key for this
        chat's model, or has uploaded their own OpenRouter key
        (provisioned_at IS NULL). Otherwise 'platform'. Passing
        model_id keeps the origin consistent with the endpoint the chat
        actually used (resolve_endpoint). Cached on the instance so each
        request only hits the resolver once.
        """
        if self._billing_origin is not None:
            return self._billing_origin

        from usage_quota.constants import BILLING_ORIGIN_PLATFORM

        if not self._user_id:
            self._billing_origin = BILLING_ORIGIN_PLATFORM
            return self._billing_origin

        from authentication.models import User
        from llm.services.api_key_resolver import resolve_with_origin
        try:
            user = await sync_to_async(User.objects.get)(id=self._user_id)
            _, origin = await sync_to_async(resolve_with_origin)(
                user=user, model_id=self._model_id,
            )
            self._billing_origin = origin
        except Exception:
            logger.error("langchain.resolve_billing_origin_failed", exc_info=True)
            self._billing_origin = BILLING_ORIGIN_PLATFORM
        return self._billing_origin

    async def calculate_costs(self, prompt_tokens, completion_tokens, tool_cost=0.0):
        """Calculate costs from token counts using model pricing."""
        try:
            catalog = CatalogService()
            get_pricing = sync_to_async(catalog.get_model_pricing, thread_sensitive=True)
            pricing = await get_pricing(self._model_id)
            prompt_price = (pricing["prompt_price"] or 0) / PRICE_STORAGE_UNIT
            completion_price = (pricing["completion_price"] or 0) / PRICE_STORAGE_UNIT
            prompt_cost = prompt_tokens * prompt_price
            completion_cost = completion_tokens * completion_price
            total_cost = prompt_cost + completion_cost + tool_cost
            return prompt_cost, completion_cost, total_cost
        except Exception:
            return 0.0, 0.0, tool_cost

    async def record_chat_aggregate_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        total_tool_cost: float,
        image_gen_cost_in_bundle: float = 0.0,
    ) -> float:
        """Bill the aggregate OPENROUTER/CHAT row for one turn.

        The billable amount EXCLUDES OpenRouter image-gen cost
        (``image_gen_cost_in_bundle``): those dollars were already billed
        per-image by ``image_tools._record_billing`` (IMAGE_GENERATION
        row), so folding them into this aggregate would record the same
        dollars twice and decrement quota twice.

        Returns the amount actually billed (0.0 when nothing recorded).
        """
        billable_tool_cost = max(total_tool_cost - image_gen_cost_in_bundle, 0.0)
        _, _, billable_total_cost = await self.calculate_costs(
            prompt_tokens, completion_tokens, billable_tool_cost
        )

        if not self._user_id or billable_total_cost <= 0:
            return 0.0
        try:
            from decimal import Decimal
            from authentication.models import User
            from usage_quota.billing import get_billing_service, BillableOperation
            from usage_quota.models import ServiceType, FeatureType

            user = await sync_to_async(User.objects.get)(id=self._user_id)
            origin = await self.resolve_billing_origin()
            op = BillableOperation(
                service=ServiceType.OPENROUTER,
                feature=FeatureType.CHAT,
                model_id=self._model_id,
                cost_usd=Decimal(str(billable_total_cost)),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            await sync_to_async(get_billing_service().record_usage)(
                user, op, billing_origin=origin,
            )
            self.final_usage_recorded = True
            logger.info(
                f"[LangChain] Usage recorded (origin={origin}): "
                f"${billable_total_cost:.6f} "
                f"(image-gen excluded: ${image_gen_cost_in_bundle:.6f})"
            )
            return billable_total_cost
        except Exception:
            logger.error("langchain.quota_log_failed", exc_info=True)
            return 0.0
