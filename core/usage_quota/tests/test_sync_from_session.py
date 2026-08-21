"""Tests for ``POST /api/billing/sync-from-session/`` + ``GET /api/billing/status/``."""

from unittest.mock import patch

import pytest
import stripe

from authentication.models import User
from usage_quota.models import SubscriptionPlan, UserSubscription


def _fake_session(
    *,
    customer,
    sub_id='sub_X',
    meta_user_id=None,
    price_id='price_PLUS_M',
    sub_status='active',
    payment_status='paid',
    period_end=1700000000,
    cancel_at_period_end=False,
):
    """Build a dict shaped like an expanded Stripe Checkout Session."""
    subscription = {
        'id': sub_id,
        'status': sub_status,
        'current_period_end': period_end,
        'cancel_at_period_end': cancel_at_period_end,
        'metadata': {'user_id': meta_user_id} if meta_user_id else {},
        'items': {
            'data': [{'price': {'id': price_id}}],
        },
    }
    return {
        'customer': customer,
        'subscription': subscription,
        'payment_status': payment_status,
    }


@pytest.mark.django_db
def test_happy_path_writes_subscription(
    seeded, api_client, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='sync@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_SYNC'
    user.save()
    auth_as(api_client, user)
    sess = _fake_session(
        customer='cus_SYNC', meta_user_id=str(user.id),
        period_end=1799999999, cancel_at_period_end=False,
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_test_SYNC',
        )
    assert response.status_code == 200
    body = response.json()
    assert body['plan'] == 'plus'
    assert body['current_period_end'] == 1799999999
    assert body['cancel_at_period_end'] is False
    sub = UserSubscription.objects.get(user=user)
    assert sub.plan.name == 'plus'
    assert sub.stripe_subscription_id == 'sub_X'
    assert sub.current_period_end == 1799999999
    assert sub.cancel_at_period_end is False


@pytest.mark.django_db
def test_foreign_session_returns_403(
    seeded, api_client, settings, auth_as,
):
    """Attacker submits another user's session_id."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    attacker = User.objects.create_user(
        email='atk@t.com', password='x', is_verified=True,
    )
    attacker.stripe_customer_id = 'cus_ATTACKER'
    attacker.save()
    auth_as(api_client, attacker)
    sess = _fake_session(
        customer='cus_VICTIM', meta_user_id='some-other-uuid',
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_X',
        )
    assert response.status_code == 403
    sub = UserSubscription.objects.filter(user=attacker).first()
    if sub is not None:
        assert sub.plan.name == 'free'
        assert sub.stripe_subscription_id in (None, '')


@pytest.mark.django_db
def test_null_customer_id_does_not_bypass_ownership(
    seeded, api_client, settings, auth_as,
):
    """REGRESSION: a user with stripe_customer_id=None hitting a session
    whose customer field is also None must NOT pass ownership via
    ``None == None`` vacuous-truth."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='nullcust@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = None
    user.save(update_fields=['stripe_customer_id'])
    auth_as(api_client, user)
    sess = _fake_session(
        customer=None,
        meta_user_id='someone-else-entirely',
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_NULL',
        )
    assert response.status_code == 403


@pytest.mark.django_db
def test_metadata_match_with_null_customer_id_still_allowed(
    seeded, api_client, settings, auth_as,
):
    """Positive twin: if subscription metadata names the requesting user,
    the sync proceeds even with both customer fields None."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='metaok@t.com', password='x', is_verified=True,
    )
    auth_as(api_client, user)
    sess = _fake_session(customer=None, meta_user_id=str(user.id))
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_META',
        )
    assert response.status_code == 200


@pytest.mark.django_db
def test_payment_incomplete_returns_400(
    seeded, api_client, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='unpaid@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_UNPAID'
    user.save()
    auth_as(api_client, user)
    sess = _fake_session(
        customer='cus_UNPAID', meta_user_id=str(user.id),
        payment_status='unpaid',
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_X',
        )
    assert response.status_code == 400
    sub = UserSubscription.objects.filter(user=user).first()
    if sub is not None:
        assert sub.plan.name == 'free'


@pytest.mark.django_db
def test_idempotent_re_run_is_noop(seeded, api_client, settings, auth_as):
    """Webhook ran first and stamped sub_id; sync_from_session converges."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    plus = SubscriptionPlan.objects.get(name='plus')
    user = User.objects.create_user(
        email='dup@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_DUP'
    user.save()
    pre, _ = UserSubscription.objects.update_or_create(
        user=user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_DUP',
        },
    )
    auth_as(api_client, user)
    sess = _fake_session(
        customer='cus_DUP', meta_user_id=str(user.id), sub_id='sub_DUP',
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_X',
        )
    assert response.status_code == 200
    pre.refresh_from_db()
    assert pre.plan.name == 'plus'
    assert pre.stripe_subscription_id == 'sub_DUP'
    assert UserSubscription.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_cancel_at_period_end_persisted(
    seeded, api_client, settings, auth_as,
):
    """Cancellation flag is persisted so /settings/billing renders banner."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='canc@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_CANC'
    user.save()
    auth_as(api_client, user)
    sess = _fake_session(
        customer='cus_CANC', meta_user_id=str(user.id),
        cancel_at_period_end=True, period_end=1800000000,
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_CANC',
        )
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=user)
    assert sub.cancel_at_period_end is True
    assert sub.current_period_end == 1800000000


@pytest.mark.django_db
def test_unknown_session_returns_404(
    seeded, api_client, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='ghost@t.com', password='x', is_verified=True,
    )
    auth_as(api_client, user)
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        side_effect=stripe.error.InvalidRequestError(
            message='No such checkout session', param='id',
        ),
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_GHOST',
        )
    assert response.status_code == 404


@pytest.mark.django_db
def test_missing_session_id_returns_400(
    seeded, api_client, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='nox@t.com', password='x', is_verified=True,
    )
    auth_as(api_client, user)
    response = api_client.post('/api/billing/sync-from-session/')
    assert response.status_code == 400


@pytest.mark.django_db
def test_unknown_price_id_returns_500(
    seeded, api_client, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='wat@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_WAT'
    user.save()
    auth_as(api_client, user)
    sess = _fake_session(
        customer='cus_WAT', meta_user_id=str(user.id),
        price_id='price_UNKNOWN',
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_X',
        )
    assert response.status_code == 500


@pytest.mark.django_db
def test_billing_status_endpoint_renders_period_fields(
    seeded, api_client, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    plus = SubscriptionPlan.objects.get(name='plus')
    user = User.objects.create_user(
        email='status@t.com', password='x', is_verified=True,
    )
    UserSubscription.objects.update_or_create(
        user=user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_STATUS',
            'current_period_end': 1900000000,
            'cancel_at_period_end': True,
        },
    )
    auth_as(api_client, user)
    response = api_client.get('/api/billing/status/')
    assert response.status_code == 200
    body = response.json()
    assert body['plan'] == 'plus'
    assert body['is_paid'] is True
    assert body['current_period_end'] == 1900000000
    assert body['cancel_at_period_end'] is True


@pytest.mark.django_db
def test_billing_status_free_user_has_null_period(
    seeded, api_client, settings, auth_as,
):
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='freestatus@t.com', password='x', is_verified=True,
    )
    auth_as(api_client, user)
    response = api_client.get('/api/billing/status/')
    assert response.status_code == 200
    body = response.json()
    assert body['plan'] == 'free'
    assert body['is_paid'] is False
    assert body['current_period_end'] is None
    assert body['cancel_at_period_end'] is False


@pytest.mark.django_db
@pytest.mark.parametrize('dead_status', [
    'canceled', 'unpaid', 'incomplete_expired', 'past_due', 'paused',
])
def test_replayed_session_with_dead_subscription_rejected(
    seeded, api_client, settings, auth_as, dead_status,
):
    """REPLAY GUARD: an old paid session_id stays retrievable after the
    subscription is canceled. Re-POSTing it must NOT re-grant the paid
    plan for free — only 'active'/'trialing' subscriptions reconcile."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email=f'replay-{dead_status}@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_REPLAY'
    user.save()
    auth_as(api_client, user)
    sess = _fake_session(
        customer='cus_REPLAY', meta_user_id=str(user.id),
        sub_status=dead_status,
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_REPLAY',
        )
    assert response.status_code == 409
    assert response.json()['error'] == 'subscription_not_active'
    sub = UserSubscription.objects.filter(user=user).first()
    if sub is not None:
        assert sub.plan.name == 'free'
        assert sub.stripe_subscription_id in (None, '')


@pytest.mark.django_db
def test_trialing_subscription_is_accepted(
    seeded, api_client, settings, auth_as,
):
    """Positive twin of the replay guard: a live trial reconciles."""
    settings.STRIPE_API_KEY = 'sk_test_FAKE'
    user = User.objects.create_user(
        email='trial@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_TRIAL'
    user.save()
    auth_as(api_client, user)
    sess = _fake_session(
        customer='cus_TRIAL', meta_user_id=str(user.id),
        sub_status='trialing',
    )
    with patch(
        'usage_quota.billing.stripe_checkout.stripe.checkout.Session.retrieve',
        return_value=sess,
    ):
        response = api_client.post(
            '/api/billing/sync-from-session/?session_id=cs_TRIAL',
        )
    assert response.status_code == 200
    assert UserSubscription.objects.get(user=user).plan.name == 'plus'
