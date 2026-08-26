"""Unit tests for the coding-agent billing gate and settlement.

Exercises `llm.services.coding_agent_billing` directly against a mocked
job coroutine — the transcripts in `llm/tests/golden/` cover the same
code wired into a full chat turn; these tests pin the billing amounts
and attribution in isolation.
"""

import asyncio
from decimal import Decimal

from asgiref.sync import async_to_sync
from rest_framework.test import APITestCase

from llm.services.coding_agent_billing import (
    bill_code_session,
    check_code_session_budget,
    run_and_settle,
)
from llm.tests.conftest import make_billing_user, seed_billing_plan
from usage_quota.models import FeatureType, ServiceType, UsageLog

PLAN_NAME = "coding-agent-billing-plan"
MODEL_ID = "anthropic/claude-sonnet-4"
CHAT_ID = "chat-billing-test"
JOB_ID = "job-billing-test"


class FakeContext:
    """The two attributes `coding_agent_billing` reads off a tool context."""

    def __init__(self, user_id: str, chat_id: str = CHAT_ID):
        self.user_id = user_id
        self.chat_id = chat_id


async def _job_result(cost_usd: float, job_id: str = JOB_ID, delay: float = 0.0) -> dict:
    """A `CodingAgentService.execute()`-shaped result for a finished job.

    `delay` gives the caller a real suspension point to cancel against —
    without one, a fast fake job could finish before cancellation ever
    reaches it, and a test built on that would pass whether or not the
    shield actually did anything.
    """
    if delay:
        await asyncio.sleep(delay)
    return {
        "success": True,
        "job_id": job_id,
        "result": {"success": True, "total_cost_usd": cost_usd},
    }


class BillCodeSessionTests(APITestCase):
    def setUp(self):
        plan = seed_billing_plan(PLAN_NAME, extra_features={"code_sessions": True})
        self.user = make_billing_user("coding-agent-billing@example.com", plan)
        self.context = FakeContext(str(self.user.id))

    def test_records_correct_amount_and_attribution(self):
        async_to_sync(bill_code_session)(self.context, 4.5, MODEL_ID, CHAT_ID, JOB_ID)

        log = UsageLog.objects.get(user=self.user, service=ServiceType.CODE_SESSION)
        self.assertEqual(log.cost_usd, Decimal("4.5"))
        self.assertEqual(log.feature, FeatureType.CODE_SESSION)
        self.assertEqual(log.model_id, MODEL_ID)
        self.assertEqual(log.session_id, CHAT_ID)
        self.assertEqual(log.request_id, JOB_ID)

    def test_zero_cost_is_a_no_op(self):
        async_to_sync(bill_code_session)(self.context, 0.0, MODEL_ID, CHAT_ID, JOB_ID)

        self.assertFalse(
            UsageLog.objects.filter(user=self.user, service=ServiceType.CODE_SESSION).exists()
        )

    def test_same_job_id_is_billed_once(self):
        """Idempotency: two settlement attempts for one job never double-bill."""
        async_to_sync(bill_code_session)(self.context, 4.5, MODEL_ID, CHAT_ID, JOB_ID)
        async_to_sync(bill_code_session)(self.context, 4.5, MODEL_ID, CHAT_ID, JOB_ID)

        rows = UsageLog.objects.filter(
            user=self.user, service=ServiceType.CODE_SESSION, request_id=JOB_ID,
        )
        self.assertEqual(rows.count(), 1)


class RunAndSettleTests(APITestCase):
    def setUp(self):
        plan = seed_billing_plan(PLAN_NAME + "-run", extra_features={"code_sessions": True})
        self.user = make_billing_user("coding-agent-run-settle@example.com", plan)
        self.context = FakeContext(str(self.user.id))

    def test_bills_the_job_it_ran(self):
        result = async_to_sync(run_and_settle)(
            self.context, MODEL_ID, CHAT_ID, _job_result(2.25)
        )

        self.assertEqual(result["job_id"], JOB_ID)
        log = UsageLog.objects.get(user=self.user, service=ServiceType.CODE_SESSION)
        self.assertEqual(log.cost_usd, Decimal("2.25"))
        self.assertEqual(log.request_id, JOB_ID)

    def test_survives_cancellation_of_the_awaiting_task(self):
        """A closed tab cancels the caller mid-flight; settlement still lands."""

        async def _cancel_while_the_job_is_still_running():
            task = asyncio.ensure_future(
                run_and_settle(self.context, MODEL_ID, CHAT_ID, _job_result(3.0, delay=0.05))
            )
            await asyncio.sleep(0.01)  # the fake job is still sleeping here
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            # Give the shielded settlement a turn to finish in the background.
            await asyncio.sleep(0.1)

        async_to_sync(_cancel_while_the_job_is_still_running)()

        log = UsageLog.objects.get(user=self.user, service=ServiceType.CODE_SESSION)
        self.assertEqual(log.cost_usd, Decimal("3.0"))


class CheckCodeSessionBudgetTests(APITestCase):
    def setUp(self):
        plan = seed_billing_plan(
            PLAN_NAME + "-budget",
            extra_features={"code_sessions": True},
        )
        self.user = make_billing_user("coding-agent-budget@example.com", plan)
        self.context = FakeContext(str(self.user.id))

    def test_budget_is_the_tighter_of_weekly_and_session_remaining(self):
        denial, budget_usd = async_to_sync(check_code_session_budget)(self.context)

        self.assertIsNone(denial)
        # seed_billing_plan's defaults: weekly=50.00, session=20.00.
        self.assertEqual(budget_usd, 20.0)

    def test_missing_context_enforces_no_ceiling(self):
        denial, budget_usd = async_to_sync(check_code_session_budget)(None)

        self.assertIsNone(denial)
        self.assertIsNone(budget_usd)
