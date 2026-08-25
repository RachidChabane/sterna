"""Shared fixtures for llm/tests.

Test pattern (mirrors usage_quota/tests/test_billing_coverage.py):
    Use sync `def test_*` methods on `django.test.TestCase`.
"""

from decimal import Decimal


def seed_billing_plan(plan_name="llm-tests-plan"):
    """Minimal active SubscriptionPlan for record_usage()/check_quota() calls.

    Bills from `_calculate_costs`/the accounting layer, not
    `ServicePricing`, so no ServicePricing rows are seeded here -- only a
    plan with `features={"chat": True}` (required by the pre-stream
    `check_quota(feature_name='chat')` gate) for the user's UserSubscription
    to resolve to.
    """
    from usage_quota.models import SubscriptionPlan

    plan, _ = SubscriptionPlan.objects.get_or_create(
        name=plan_name,
        defaults={
            "display_name": "LLM Tests Plan",
            "weekly_limit_usd": Decimal("50.00"),
            "session_limit_usd": Decimal("20.00"),
            # `check_quota(feature_name='chat')` gates on plan.features
            # having the matching flag (see usage_quota/feature_registry.py).
            "features": {"chat": True},
        },
    )
    return plan


def make_billing_user(email, plan):
    from authentication.models import User
    from usage_quota.models import UserSubscription

    user = User.objects.create_user(email=email, password="x")
    UserSubscription.objects.create(user=user, plan=plan, is_active=True)
    return user
