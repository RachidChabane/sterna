"""Tests for ``POST /api/billing/checkout-session/`` (task 12).

Patch surface: ``usage_quota.billing.stripe_checkout.stripe.checkout.Session.create``.
``api_client``, ``seeded``, ``verified_free_user``, ``auth_as`` come from
``conftest.py``.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
import stripe

from authentication.models import User
from usage_quota.models import SubscriptionPlan, UserSubscription


@pytest.mark.django_db
def test_happy_path_returns_url(
    seeded, api_client, verified_free_user, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    auth_as(api_client, verified_free_user)
    fake = MagicMock(url='https://checkout.stripe.com/c/pay/cs_test_HAPPY')
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.create',
        return_value=fake,
    ) as m:
        response = api_client.post(
            '/api/billing/checkout-session/',
            {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
            format='json',
        )
    assert response.status_code == 200
    assert response.json()['url'].startswith('https://checkout.stripe.com/')
    kwargs = m.call_args.kwargs
    assert kwargs['mode'] == 'subscription'
    assert kwargs['customer'] == 'cus_TEST'
    assert kwargs['line_items'] == [{'price': 'price_PLUS_M', 'quantity': 1}]
    assert kwargs['automatic_tax'] == {'enabled': True}
    assert kwargs['allow_promotion_codes'] is True
    assert kwargs['subscription_data']['metadata'] == {
        'user_id': str(verified_free_user.id),
        'plan_slug': 'plus',
        'billing_cycle': 'monthly',
    }
    assert '/billing/return' in kwargs['success_url']
    assert '/pricing' in kwargs['cancel_url']
    # Idempotency key includes billing_cycle so Monthly↔Yearly toggles
    # within the same wall-second produce distinct sessions.
    assert ':monthly:' in kwargs['idempotency_key']


@pytest.mark.django_db
def test_already_on_plan_returns_409(
    seeded, api_client, verified_free_user, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.update_or_create(
        user=verified_free_user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_EXISTING',
        },
    )
    auth_as(api_client, verified_free_user)
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.create',
    ) as m:
        response = api_client.post(
            '/api/billing/checkout-session/',
            {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
            format='json',
        )
    assert response.status_code == 409
    assert response.json()['error'] == 'already_on_plan'
    m.assert_not_called()


@pytest.mark.django_db
def test_email_not_verified_returns_403(seeded, api_client, settings, auth_as):
    # Create user with STRIPE_API_KEY unset so the eager post_save task
    # no-ops; then bump to a fake key for the view call.
    settings.STRIPE_API_KEY = ''
    user = User.objects.create_user(
        email='unv@t.com', password='x', is_verified=False,
    )
    user.stripe_customer_id = 'cus_X'
    user.save()
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    auth_as(api_client, user)
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.create',
    ) as m:
        response = api_client.post(
            '/api/billing/checkout-session/',
            {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
            format='json',
        )
    assert response.status_code == 403
    m.assert_not_called()


@pytest.mark.django_db
def test_unknown_slug_rejected_at_validation(
    seeded, api_client, verified_free_user, settings, auth_as,
):
    """ChoiceField rejects unknown slugs at the 400 layer.

    The 404 ``plan_not_found`` path applies only when the slug is valid
    but the SubscriptionPlan row is missing or inactive.
    """
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    auth_as(api_client, verified_free_user)
    response = api_client.post(
        '/api/billing/checkout-session/',
        {'plan_slug': 'enterprise', 'billing_cycle': 'monthly'},
        format='json',
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_inactive_plan_returns_404(
    seeded, api_client, verified_free_user, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    SubscriptionPlan.objects.filter(name='plus').update(is_active=False)
    auth_as(api_client, verified_free_user)
    response = api_client.post(
        '/api/billing/checkout-session/',
        {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
        format='json',
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_mode_mismatch_returns_500_with_log(
    seeded, api_client, verified_free_user, settings, auth_as, caplog,
):
    """Test-key + live customer (or vice versa) → InvalidRequestError → 500."""
    # Test LOGGING config routes root to a NullHandler at CRITICAL, so the
    # unconfigured 'usage_quota.views' logger drops ERROR records before
    # caplog can see them. Lower the emitting logger's level explicitly.
    caplog.set_level(logging.ERROR, logger='usage_quota.views')
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    auth_as(api_client, verified_free_user)
    err = stripe.error.InvalidRequestError(
        message='No such customer: cus_TEST',
        param='customer',
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.create',
        side_effect=err,
    ):
        response = api_client.post(
            '/api/billing/checkout-session/',
            {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
            format='json',
        )
    assert response.status_code == 500
    assert response.json()['error'] == 'stripe_misconfigured'
    assert any(
        'checkout.stripe_invalid_request' in rec.message
        for rec in caplog.records
    )


@pytest.mark.django_db
def test_no_price_id_returns_500(
    seeded, api_client, verified_free_user, settings, auth_as,
):
    """If sync_stripe_prices was never run, price ids are NULL → 500."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    SubscriptionPlan.objects.filter(name='plus').update(
        stripe_price_id_monthly=None, stripe_price_id_yearly=None,
    )
    auth_as(api_client, verified_free_user)
    response = api_client.post(
        '/api/billing/checkout-session/',
        {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
        format='json',
    )
    assert response.status_code == 500
    assert response.json()['error'] == 'plan_not_billable'


@pytest.mark.django_db
def test_missing_stripe_customer_id_creates_one(
    seeded, api_client, settings, auth_as,
):
    """Race: signup Celery task hasn't filled stripe_customer_id yet.

    The view must synchronously call ``get_or_create_stripe_customer``
    and persist the id before creating the Checkout Session.
    """
    # Create the user with STRIPE_API_KEY unset so the eager post_save
    # task no-ops and stripe_customer_id stays None.
    settings.STRIPE_API_KEY = ''
    user = User.objects.create_user(
        email='race@t.com', password='x', is_verified=True,
    )
    assert user.stripe_customer_id is None

    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    auth_as(api_client, user)
    fake_customer = MagicMock(id='cus_RACE')
    fake_session = MagicMock(url='https://checkout.stripe.com/c/pay/x')
    with patch('stripe.Customer.create', return_value=fake_customer), \
         patch(
             'usage_quota.billing.stripe_checkout.stripe.checkout.Session.create',
             return_value=fake_session,
         ) as m:
        response = api_client.post(
            '/api/billing/checkout-session/',
            {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
            format='json',
        )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.stripe_customer_id == 'cus_RACE'
    assert m.call_args.kwargs['customer'] == 'cus_RACE'


@pytest.mark.django_db
def test_unauthenticated_returns_401(seeded, api_client):
    response = api_client.post(
        '/api/billing/checkout-session/',
        {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
        format='json',
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_paid_to_paid_change_returns_409_use_portal(
    seeded, api_client, verified_free_user, settings, auth_as,
):
    """A user with an active Stripe subscription must NOT get a second
    Checkout Session for a different paid plan — that would create a
    second Stripe subscription and double-charge. The view refuses with
    409 USE_PORTAL; the frontend then opens the Customer Portal.
    """
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.update_or_create(
        user=verified_free_user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_EXISTING',
        },
    )
    auth_as(api_client, verified_free_user)
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.create',
    ) as m:
        response = api_client.post(
            '/api/billing/checkout-session/',
            {'plan_slug': 'pro', 'billing_cycle': 'monthly'},
            format='json',
        )
    assert response.status_code == 409
    body = response.json()
    assert body['error'] == 'use_portal'
    assert body['code'] == 'USE_PORTAL'
    assert body['portal_hint'] == '/api/billing/portal-session/'
    m.assert_not_called()


@pytest.mark.django_db
def test_free_user_with_stale_free_row_can_still_checkout(
    seeded, api_client, verified_free_user, settings, auth_as,
):
    """A free-plan row (no stripe_subscription_id) must NOT trip the
    USE_PORTAL guard — free→paid goes through Checkout."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    free = SubscriptionPlan.objects.get(name='free')
    UserSubscription.objects.update_or_create(
        user=verified_free_user,
        defaults={
            'plan': free, 'is_active': True,
            'stripe_subscription_id': None,
        },
    )
    auth_as(api_client, verified_free_user)
    fake = MagicMock(url='https://checkout.stripe.com/c/pay/cs_test_FREE')
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.create',
        return_value=fake,
    ):
        response = api_client.post(
            '/api/billing/checkout-session/',
            {'plan_slug': 'plus', 'billing_cycle': 'monthly'},
            format='json',
        )
    assert response.status_code == 200
