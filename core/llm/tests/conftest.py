"""Shared fixtures for llm/tests.

Test pattern (mirrors usage_quota/tests/test_billing_coverage.py):
    Use sync `def test_*` methods on `django.test.TestCase`.
"""

from decimal import Decimal


def seed_billing_plan(plan_name="llm-tests-plan", extra_features=None, **extra_defaults):
    """Minimal active SubscriptionPlan for record_usage()/check_quota() calls.

    Bills from `_calculate_costs`/the accounting layer, not
    `ServicePricing`, so no ServicePricing rows are seeded here -- only a
    plan with `features={"chat": True}` (required by the pre-stream
    `check_quota(feature_name='chat')` gate) for the user's UserSubscription
    to resolve to.

    `extra_features` adds flag keys to `features` for a scenario that
    crosses another gate; `extra_defaults` sets the plan fields such a
    gate reads, e.g. a per-feature weekly limit. Both apply only when the
    named plan is created, so each scenario uses its own plan name.
    """
    from usage_quota.models import SubscriptionPlan

    features = {"chat": True}
    features.update(extra_features or {})
    defaults = {
        "display_name": "LLM Tests Plan",
        "weekly_limit_usd": Decimal("50.00"),
        "session_limit_usd": Decimal("20.00"),
        # `check_quota(feature_name='chat')` gates on plan.features
        # having the matching flag (see usage_quota/feature_registry.py).
        "features": features,
    }
    defaults.update(extra_defaults)

    plan, _ = SubscriptionPlan.objects.get_or_create(
        name=plan_name,
        defaults=defaults,
    )
    return plan


def make_billing_user(email, plan):
    from authentication.models import User
    from usage_quota.models import UserSubscription

    user = User.objects.create_user(email=email, password="x")
    UserSubscription.objects.create(user=user, plan=plan, is_active=True)
    return user
