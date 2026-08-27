"""Coverage for two billing failure paths that had no test before:

1. ``BillingService._queue_failed_deduction`` — the code path only run
   when recording usage after a successful external call fails. It
   called ``queue_failed_deduction`` with a single dict positional
   argument, but that function takes ``user_id``/``service``/``cost_usd``/
   ``feature`` as separate keyword arguments — every call raised
   ``TypeError`` and was swallowed by the surrounding ``except Exception``,
   so a failed deduction was never actually queued for retry.

2. The ``@billable``/``@billable_async`` decorators' pre-flight quota
   check — raising ``QuotaExceededException`` without its required
   ``message`` argument raised ``TypeError`` instead of the intended
   quota-exceeded error whenever a pre-checked call was over quota.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase

from usage_quota.billing.decorators import billable, billable_async
from usage_quota.billing.operations import BillableOperation, QuotaStatus
from usage_quota.billing.service import BillingService
from usage_quota.exceptions import QuotaExceededException
from usage_quota.models import FeatureType, ServiceType


class QueueFailedDeductionCallShapeTest(TestCase):
    """`_queue_failed_deduction` must call `tasks.queue_failed_deduction`
    with the keyword shape that function actually accepts."""

    def test_calls_queue_failed_deduction_with_matching_kwargs(self):
        service = BillingService()
        user = MagicMock(id="user-1")
        operation = BillableOperation(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            model_id="anthropic/claude-3-5-sonnet",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=Decimal("0.02"),
            request_id="req-1",
            session_id="sess-1",
        )

        with patch(
            "usage_quota.tasks.queue_failed_deduction"
        ) as mock_queue:
            service._queue_failed_deduction(user, operation)

        mock_queue.assert_called_once()
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["user_id"], "user-1")
        self.assertEqual(kwargs["service"], str(ServiceType.OPENROUTER))
        self.assertEqual(kwargs["cost_usd"], "0.02")
        self.assertEqual(kwargs["feature"], str(FeatureType.CHAT))
        self.assertEqual(kwargs["model_id"], "anthropic/claude-3-5-sonnet")
        self.assertEqual(kwargs["prompt_tokens"], 100)
        self.assertEqual(kwargs["completion_tokens"], 50)
        self.assertEqual(kwargs["request_id"], "req-1")
        self.assertEqual(kwargs["session_id"], "sess-1")

    def test_logs_critical_but_does_not_raise_when_queueing_itself_fails(self):
        service = BillingService()
        user = MagicMock(id="user-1")
        operation = BillableOperation(
            service=ServiceType.OPENROUTER,
            cost_usd=Decimal("0.02"),
        )

        with patch(
            "usage_quota.tasks.queue_failed_deduction",
            side_effect=RuntimeError("celery and redis both down"),
        ):
            # Must not raise — this is the last-resort path.
            service._queue_failed_deduction(user, operation)


def _denied_status(reason: str) -> QuotaStatus:
    return QuotaStatus(
        allowed=False,
        weekly_limit_usd=Decimal("10"),
        weekly_used_usd=Decimal("10"),
        weekly_remaining_usd=Decimal("0"),
        session_limit_usd=Decimal("3"),
        session_used_usd=Decimal("3"),
        session_remaining_usd=Decimal("0"),
        weekly_resets_in_seconds=3600,
        session_resets_in_seconds=600,
        denial_reason=reason,
    )


class BillableDecoratorPreCheckDenialTest(TestCase):
    """Over-quota pre-checks must raise QuotaExceededException (with a
    message), not TypeError."""

    def test_sync_decorator_raises_quota_exceeded_with_message(self):
        fake_billing = MagicMock()
        fake_billing.check_quota.return_value = _denied_status("weekly")

        @billable(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            pre_check=True,
            estimated_cost_usd=Decimal("0.01"),
        )
        def do_call(user):
            return "ok"

        user = MagicMock(id="user-1")
        with patch(
            "usage_quota.billing.decorators.get_billing_service",
            return_value=fake_billing,
        ):
            with self.assertRaises(QuotaExceededException) as ctx:
                do_call(user=user)

        self.assertEqual(ctx.exception.message, "Weekly usage limit exceeded")
        self.assertEqual(ctx.exception.limit_type, "weekly")

    def test_sync_decorator_session_denial_message(self):
        fake_billing = MagicMock()
        fake_billing.check_quota.return_value = _denied_status("session")

        @billable(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            pre_check=True,
            estimated_cost_usd=Decimal("0.01"),
        )
        def do_call(user):
            return "ok"

        user = MagicMock(id="user-1")
        with patch(
            "usage_quota.billing.decorators.get_billing_service",
            return_value=fake_billing,
        ):
            with self.assertRaises(QuotaExceededException) as ctx:
                do_call(user=user)

        self.assertIn("Session rate limit exceeded", ctx.exception.message)
        self.assertEqual(ctx.exception.limit_type, "session")

    def test_async_decorator_raises_quota_exceeded_with_message(self):
        fake_billing = MagicMock()
        fake_billing.check_quota.return_value = _denied_status("weekly")

        @billable_async(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            pre_check=True,
            estimated_cost_usd=Decimal("0.01"),
        )
        async def do_call(user):
            return "ok"

        user = MagicMock(id="user-1")
        with patch(
            "usage_quota.billing.decorators.get_billing_service",
            return_value=fake_billing,
        ):
            with self.assertRaises(QuotaExceededException) as ctx:
                async_to_sync(do_call)(user=user)

        self.assertEqual(ctx.exception.message, "Weekly usage limit exceeded")
