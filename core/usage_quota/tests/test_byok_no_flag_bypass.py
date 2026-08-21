"""Regression: BYOK fast-path must NOT bypass feature-flag gates.

A personal OpenRouter key skips the platform's USD budget gate (the
user pays OpenRouter directly), but it does not entitle the user to
flag-gated features the plan doesn't include.
"""
from decimal import Decimal

import pytest

from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.billing.service import get_billing_service
from usage_quota.constants import BILLING_ORIGIN_BYOK
from usage_quota.exceptions import FeatureNotAvailableException
from usage_quota.models import (
    FeatureType,
    ServiceType,
    SubscriptionPlan,
    UserSubscription,
)


@pytest.mark.django_db
def test_byok_does_not_bypass_feature_flag(django_user_model):
    seed_tiers_for_tests()
    user = django_user_model.objects.create_user(
        email='byok@t.com', password='x',
    )
    UserSubscription.objects.create(
        user=user,
        plan=SubscriptionPlan.objects.get(name='free'),
    )
    billing = get_billing_service()
    with pytest.raises(FeatureNotAvailableException):
        billing.check_quota(
            user=user,
            service=ServiceType.OPENROUTER,
            estimated_cost=Decimal('5.00'),
            feature=FeatureType.CHAT,
            assume_origin=BILLING_ORIGIN_BYOK,
            feature_name='spark_generation',  # sparks_create=False on free
        )


@pytest.mark.django_db
def test_byok_still_skips_usd_gate_when_flag_passes(django_user_model):
    """Sanity: when the flag passes, BYOK still skips the USD gate.

    Free plan has chat=True, so feature_name='chat' passes the flag
    gate. BYOK on OpenRouter then skips the USD gate even at a cost
    that would otherwise exceed the weekly limit.
    """
    seed_tiers_for_tests()
    user = django_user_model.objects.create_user(
        email='byok-chat@t.com', password='x',
    )
    UserSubscription.objects.create(
        user=user,
        plan=SubscriptionPlan.objects.get(name='free'),
    )
    billing = get_billing_service()
    status = billing.check_quota(
        user=user,
        service=ServiceType.OPENROUTER,
        estimated_cost=Decimal('5.00'),  # way over the $1.50 free weekly cap
        feature=FeatureType.CHAT,
        assume_origin=BILLING_ORIGIN_BYOK,
        feature_name='chat',
    )
    assert status.allowed is True
