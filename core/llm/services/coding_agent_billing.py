"""Server-side quota gate and billing settlement for coding-agent tool calls.

Every coding-agent tool handler (`coding_agent`, `plan_implementation`,
`implement_plan`, `edit_plan` in `llm.agent_tool_handlers`) runs the same
two-sided contract around `execute_coding_agent`: a pre-flight budget gate
before the sandbox job starts, and a settlement that survives the caller's
own cancellation once it ends. Centralizing both here means the gate and
the settlement apply the same way regardless of which handler called them
or which harness the orchestrator ran the job with — and regardless of
whether the browser that asked for it is still listening when the job
finishes.
"""

import asyncio
import json
import logging
from decimal import Decimal
from typing import Any, Awaitable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


async def check_code_session_budget(context) -> Tuple[Optional[str], Optional[float]]:
    """Run the feature_name='code_session' pre-flight gate for `context.user_id`.

    Returns ``(denial, budget_usd)``. ``denial`` is a JSON-encoded error the
    caller should return to the model verbatim, or ``None`` when the gate
    passes. ``budget_usd`` is the smaller of the user's remaining weekly
    and session USD budget at the moment of the check — the ceiling a
    mid-run job must not cross — or ``None`` when the gate could not
    compute one (missing context, or an infra error, in which case the job
    proceeds uncapped rather than blocking the user on our own fault).
    """
    if not context or not getattr(context, "user_id", None):
        return None, None
    try:
        from asgiref.sync import sync_to_async
        from usage_quota.billing.service import get_billing_service
        from usage_quota.exceptions import (
            FeatureNotAvailableException,
            QuotaExceededException,
        )
        from usage_quota.models import ServiceType, FeatureType
        try:
            from authentication.models import User
        except ImportError:
            from django.contrib.auth import get_user_model
            User = get_user_model()
        user = await sync_to_async(User.objects.get)(id=context.user_id)
        try:
            status = await sync_to_async(get_billing_service().check_quota)(
                user=user,
                service=ServiceType.CODE_SESSION,
                estimated_cost=Decimal('0'),
                feature=FeatureType.CODE_SESSION,
                feature_name='code_session',
            )
        except (FeatureNotAvailableException, QuotaExceededException) as exc:
            return json.dumps({
                "success": False,
                "status": "error",
                "error_type": exc.code,
                "message": exc.message,
                **exc.to_response_dict(),
            }), None
        remaining = min(status.weekly_remaining_usd, status.session_remaining_usd)
        return None, float(remaining)
    except Exception:
        logger.error("code_session_tier_gate_error", exc_info=True)
        return None, None


def quota_exceeded_error(budget_usd: Optional[float]) -> str:
    """The JSON error a mid-run quota stop reports to the model.

    Mirrors the shape `check_code_session_budget` returns for a pre-flight
    denial, so the model — and the frontend rendering the tool result —
    see one consistent contract whether the quota was exhausted before the
    job started or crossed while it was running.
    """
    return json.dumps({
        "success": False,
        "status": "error",
        "error_type": "quota_exceeded",
        "message": "Coding agent stopped: usage quota exceeded mid-run.",
        "limit_type": "weekly",
        "remaining_usd": budget_usd if budget_usd is not None else 0.0,
    })


async def bill_code_session(
    context,
    cost_usd,
    model_id: str,
    session_id: str = "",
    request_id: str = "",
) -> None:
    """Record a UsageLog row for a coding-agent invocation.

    The chat row's tool-cost accumulator excludes coding-agent costs (see
    `agent.cost_ledger.extract_billable_tool_costs`'s dedup guard) — this
    is the single bill site for `service=code_session`. No-op for
    zero/negative cost, missing user, or a `request_id` already settled
    (idempotency: the same job must never be billed twice, whichever
    caller settles it first).
    """
    try:
        cost_value = float(cost_usd or 0)
    except (TypeError, ValueError):
        cost_value = 0.0
    if cost_value <= 0:
        return
    if not context or not getattr(context, "user_id", None):
        return
    try:
        from asgiref.sync import sync_to_async
        from usage_quota.billing.service import get_billing_service
        from usage_quota.billing.operations import BillableOperation
        from usage_quota.models import ServiceType, FeatureType, UsageLog
        try:
            from authentication.models import User
        except ImportError:
            from django.contrib.auth import get_user_model
            User = get_user_model()
        user = await sync_to_async(User.objects.get)(id=context.user_id)
        if request_id:
            already_settled = await sync_to_async(
                UsageLog.objects.filter(
                    user=user, service=ServiceType.CODE_SESSION, request_id=request_id,
                ).exists
            )()
            if already_settled:
                return
        op = BillableOperation(
            service=ServiceType.CODE_SESSION,
            feature=FeatureType.CODE_SESSION,
            model_id=model_id or "",
            cost_usd=Decimal(str(cost_value)),
            session_id=session_id,
            request_id=request_id,
        )
        # Resolve BYOK origin: coding-agent jobs run through the OpenRouter
        # bridge using the user's key when uploaded.
        from llm.services.api_key_resolver import resolve_with_origin
        try:
            _, origin = await sync_to_async(resolve_with_origin)(user=user)
        except Exception:
            origin = 'platform'
        await sync_to_async(get_billing_service().record_usage)(
            user, op, billing_origin=origin,
        )
        logger.info(
            f"[code_session_billing] Recorded ${cost_value:.6f} for "
            f"chat={getattr(context, 'chat_id', None)} job={request_id} (origin={origin})"
        )
    except Exception:
        logger.error("code_session_billing_failed", exc_info=True)


async def run_and_settle(
    context,
    model_id: str,
    session_id: str,
    job: Awaitable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run a coding-agent job and bill it, immune to the caller's cancellation.

    A closed browser tab cancels the tool handler's own task; shielding the
    orchestrator round trip and its settlement keeps both running to
    completion on the server so usage is always recorded, however the
    request that started the job ends.
    """
    async def _run() -> Dict[str, Any]:
        result = await job
        inner = result.get("result", {}) if isinstance(result, dict) else {}
        cost_usd = inner.get("total_cost_usd", 0.0) or result.get("total_cost_usd", 0.0)
        request_id = result.get("job_id") or ""
        await bill_code_session(context, cost_usd, model_id, session_id, request_id)
        return result

    return await asyncio.shield(_run())
