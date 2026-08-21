"""Tests for ``POST /api/billing/portal-session/`` (task 12)."""

from unittest.mock import MagicMock, patch

import pytest

from authentication.models import User
from usage_quota.models import SubscriptionPlan, UserSubscription


@pytest.mark.django_db
def test_happy_path_returns_portal_url(seeded, api_client, settings, auth_as):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    plus = SubscriptionPlan.objects.get(name='plus')
    user = User.objects.create_user(
        email='paid@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_PAID'
    user.save()
    UserSubscription.objects.update_or_create(
        user=user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_ACTIVE',
        },
    )
    auth_as(api_client, user)
    fake = MagicMock(url='https://billing.stripe.com/p/session/FOO')
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.billing_portal.Session.create',
        return_value=fake,
    ) as m:
        response = api_client.post('/api/billing/portal-session/')
    assert response.status_code == 200
    assert response.json()['url'].startswith('https://billing.stripe.com/')
    assert m.call_args.kwargs['customer'] == 'cus_PAID'
    assert '/settings/billing' in m.call_args.kwargs['return_url']


@pytest.mark.django_db
def test_no_subscription_returns_409(seeded, api_client, settings, auth_as):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='nope@t.com', password='x', is_verified=True,
    )
    auth_as(api_client, user)
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.billing_portal.Session.create',
    ) as m:
        response = api_client.post('/api/billing/portal-session/')
    assert response.status_code == 409
    assert response.json()['error'] == 'no_subscription'
    m.assert_not_called()


@pytest.mark.django_db
def test_free_plan_with_no_stripe_sub_returns_409(
    seeded, api_client, settings, auth_as,
):
    """Free user has a UserSubscription row (lazy default) but null
    ``stripe_subscription_id`` — refuse before calling Stripe."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    free = SubscriptionPlan.objects.get(name='free')
    user = User.objects.create_user(
        email='free2@t.com', password='x', is_verified=True,
    )
    UserSubscription.objects.update_or_create(
        user=user,
        defaults={'plan': free, 'is_active': True},
    )
    auth_as(api_client, user)
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.billing_portal.Session.create',
    ) as m:
        response = api_client.post('/api/billing/portal-session/')
    assert response.status_code == 409
    m.assert_not_called()


@pytest.mark.django_db
def test_unverified_paid_user_can_still_manage(
    seeded, api_client, settings, auth_as,
):
    """Portal is intentionally NOT ``IsVerifiedUser``-gated so a paid
    user whose email-verification lapses can still cancel/manage."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    plus = SubscriptionPlan.objects.get(name='plus')
    user = User.objects.create_user(
        email='lapsed@t.com', password='x', is_verified=False,
    )
    user.stripe_customer_id = 'cus_LAPSED'
    user.save()
    UserSubscription.objects.update_or_create(
        user=user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_LAPSED',
        },
    )
    auth_as(api_client, user)
    fake = MagicMock(url='https://billing.stripe.com/p/session/L')
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.billing_portal.Session.create',
        return_value=fake,
    ):
        response = api_client.post('/api/billing/portal-session/')
    assert response.status_code == 200
