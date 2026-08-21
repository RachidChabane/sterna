"""Tests for ``POST /api/billing/webhook/`` (task 13).

Patch surface: ``usage_quota.views.stripe.Webhook.construct_event`` —
bypass signature math by returning a dict-shaped event directly.
``api_client``, ``seeded``, ``auth_as`` come from conftest.py.
"""

import logging
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
import stripe
from django.utils import timezone

from authentication.models import User
from usage_quota.models import (
    StripeWebhookEvent,
    SubscriptionPlan,
    UserSubscription,
)


# ---------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------

def _evt(*, event_type, event_id=None, obj, previous_attributes=None):
    """Build an event payload dict.

    Deliberately OMITS ``previous_attributes`` from the body when the
    caller doesn't supply one — exercises the handlers' default-empty
    code path. Pass an explicit ``{}`` only if you mean "an .updated
    event that happened to have no prior values".
    """
    data: dict = {'object': obj}
    if previous_attributes is not None:
        data['previous_attributes'] = previous_attributes
    return {
        'id': event_id or f'evt_{uuid.uuid4().hex[:24]}',
        'type': event_type,
        'data': data,
    }


def _sub_obj(
    *, sub_id='sub_X', customer='cus_TEST',
    plan_slug='plus', price_id='price_PLUS_M',
    sub_status='active', period_end=1799999999,
    cancel_at_period_end=False, user_id=None, trial_end=None,
):
    metadata = {}
    if user_id:
        metadata['user_id'] = user_id
    if plan_slug:
        metadata['plan_slug'] = plan_slug
    obj = {
        'id': sub_id,
        'customer': customer,
        'status': sub_status,
        'current_period_end': period_end,
        'cancel_at_period_end': cancel_at_period_end,
        'metadata': metadata,
        'items': {'data': [{'price': {'id': price_id}}]},
    }
    if trial_end is not None:
        obj['trial_end'] = trial_end
    return obj


def _invoice_obj(
    *, customer='cus_TEST', amount_paid=2000, currency='usd',
    period_start=1700000000, period_end=1702592000,
    number='INV-0042', invoice_pdf='https://pdf.example',
    price_id='price_PLUS_M',
):
    return {
        'id': f'in_{uuid.uuid4().hex[:24]}',
        'customer': customer,
        'amount_paid': amount_paid,
        'currency': currency,
        'period_start': period_start,
        'period_end': period_end,
        'number': number,
        'hosted_invoice_url': invoice_pdf,
        'invoice_pdf': invoice_pdf,
        'lines': {'data': [{'price': {'id': price_id}}]},
    }


def _post(api_client, sig='t=1,v1=fake'):
    return api_client.post(
        '/api/billing/webhook/', data=b'{}',
        content_type='application/json',
        HTTP_STRIPE_SIGNATURE=sig,
    )


@pytest.fixture
def webhook_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = 'whsec_FAKE'
    return settings


@pytest.fixture
def paid_user(seeded):
    """A user with stripe_customer_id, no UserSubscription row yet."""
    user = User.objects.create_user(
        email='wh@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_TEST'
    user.save()
    return user


# ---------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_bad_signature_returns_400_no_row_created(
    mock_construct, webhook_secret, api_client,
):
    mock_construct.side_effect = stripe.error.SignatureVerificationError(
        'bad sig', sig_header='t=1,v1=bad',
    )
    pre = StripeWebhookEvent.objects.count()
    response = _post(api_client, sig='t=1,v1=bad')
    assert response.status_code == 400
    assert StripeWebhookEvent.objects.count() == pre


@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_malformed_payload_returns_400(
    mock_construct, webhook_secret, api_client,
):
    mock_construct.side_effect = ValueError('garbage')
    pre = StripeWebhookEvent.objects.count()
    response = _post(api_client)
    assert response.status_code == 400
    assert StripeWebhookEvent.objects.count() == pre


@pytest.mark.django_db
def test_no_secret_returns_503(settings, api_client):
    settings.STRIPE_WEBHOOK_SECRET = ''
    pre = StripeWebhookEvent.objects.count()
    response = _post(api_client)
    assert response.status_code == 503
    assert StripeWebhookEvent.objects.count() == pre


# ---------------------------------------------------------------------
# Idempotency + race
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_duplicate_event_id_is_noop(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    evt_id = 'evt_dup_test_001'
    event = _evt(
        event_type='customer.subscription.created',
        event_id=evt_id,
        obj=_sub_obj(customer='cus_TEST'),
    )
    mock_construct.return_value = event

    r1 = _post(api_client)
    assert r1.status_code == 200
    assert r1.json().get('dedup') is None
    row = StripeWebhookEvent.objects.get(id=evt_id)
    assert row.processed_status == 'ok'
    assert mock_email.call_count == 1

    r2 = _post(api_client)
    assert r2.status_code == 200
    assert r2.json().get('dedup') is True
    assert StripeWebhookEvent.objects.filter(id=evt_id).count() == 1
    assert mock_email.call_count == 1


@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_replay_after_error_runs_again(
    mock_construct, webhook_secret, api_client, paid_user,
):
    evt_id = 'evt_retry_test_001'
    event = _evt(
        event_type='customer.subscription.created',
        event_id=evt_id,
        obj=_sub_obj(customer='cus_TEST'),
    )
    mock_construct.return_value = event

    # First attempt: handler raises (e.g. transient DB outage).
    with patch(
        'usage_quota.services.stripe_webhooks.UserSubscription.objects.update_or_create',
        side_effect=RuntimeError('boom'),
    ):
        response = api_client.post(
            '/api/billing/webhook/', data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=fake',
        )
    assert response.status_code == 500
    row = StripeWebhookEvent.objects.get(id=evt_id)
    assert row.processed_status == 'error'
    assert row.error_message and 'boom' in row.error_message

    # Second attempt: handler succeeds, row flips to 'ok'.
    r2 = _post(api_client)
    assert r2.status_code == 200
    row.refresh_from_db()
    assert row.processed_status == 'ok'
    assert row.error_message is None


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_parallel_delivery_in_flight_returns_200(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    evt_id = 'evt_inflight_001'
    # Pre-create the row as 'processing' (simulating another worker
    # holding the CAS claim).
    StripeWebhookEvent.objects.create(
        id=evt_id,
        type='customer.subscription.created',
        payload={'id': evt_id, 'type': 'customer.subscription.created'},
        processed_status='processing',
    )
    event = _evt(
        event_type='customer.subscription.created',
        event_id=evt_id,
        obj=_sub_obj(customer='cus_TEST'),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert response.json().get('in_flight') is True
    # CAS refused to re-claim: status stays 'processing', no dispatch.
    row = StripeWebhookEvent.objects.get(id=evt_id)
    assert row.processed_status == 'processing'
    assert mock_email.call_count == 0


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_insert_race_falls_through_to_cas(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    """Simulate a parallel INSERT that beat us: the row already exists
    at status=NULL when our create() raises IntegrityError. We must
    fall through to the CAS step, claim the row, dispatch once.
    """
    evt_id = 'evt_race_insert_001'
    # Row already present (simulating parallel-worker INSERT).
    StripeWebhookEvent.objects.create(
        id=evt_id,
        type='customer.subscription.created',
        payload={'id': evt_id, 'type': 'customer.subscription.created'},
        processed_status=None,
    )
    event = _evt(
        event_type='customer.subscription.created',
        event_id=evt_id,
        obj=_sub_obj(customer='cus_TEST'),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    body = response.json()
    assert body.get('in_flight') is None
    assert body.get('dedup') is None
    row = StripeWebhookEvent.objects.get(id=evt_id)
    assert row.processed_status == 'ok'
    assert mock_email.call_count == 1


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_stale_processing_claim_is_reclaimed(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    """A 'processing' claim older than PROCESSING_CLAIM_TTL is abandoned
    (worker crashed before the terminal write). The next delivery must
    re-claim and dispatch instead of dropping the event forever."""
    evt_id = 'evt_stale_claim_001'
    StripeWebhookEvent.objects.create(
        id=evt_id,
        type='customer.subscription.created',
        payload={'id': evt_id, 'type': 'customer.subscription.created'},
        processed_status='processing',
        claimed_at=timezone.now() - timedelta(minutes=6),
    )
    event = _evt(
        event_type='customer.subscription.created',
        event_id=evt_id,
        obj=_sub_obj(customer='cus_TEST'),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    body = response.json()
    assert body.get('in_flight') is None
    row = StripeWebhookEvent.objects.get(id=evt_id)
    assert row.processed_status == 'ok'
    assert mock_email.call_count == 1


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_fresh_processing_claim_still_returns_in_flight(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    """A claim younger than PROCESSING_CLAIM_TTL is a live worker —
    parallel deliveries must still short-circuit as in_flight."""
    evt_id = 'evt_fresh_claim_001'
    StripeWebhookEvent.objects.create(
        id=evt_id,
        type='customer.subscription.created',
        payload={'id': evt_id, 'type': 'customer.subscription.created'},
        processed_status='processing',
        claimed_at=timezone.now(),
    )
    event = _evt(
        event_type='customer.subscription.created',
        event_id=evt_id,
        obj=_sub_obj(customer='cus_TEST'),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert response.json().get('in_flight') is True
    row = StripeWebhookEvent.objects.get(id=evt_id)
    assert row.processed_status == 'processing'
    assert mock_email.call_count == 0


# ---------------------------------------------------------------------
# customer.subscription.created
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_via_meta_plan_slug(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug='plus',
            price_id='price_PLUS_M',
            period_end=1799999999,
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'plus'
    assert sub.stripe_subscription_id == 'sub_X'
    assert sub.current_period_end == 1799999999
    assert sub.cancel_at_period_end is False
    # First-time subscription → from_plan=None
    args, _kwargs = mock_email.call_args
    assert args[0] == paid_user
    assert args[1] is None
    assert args[2].name == 'plus'


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_falls_back_to_price_id_when_no_meta_slug(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M',
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert UserSubscription.objects.get(user=paid_user).plan.name == 'plus'
    assert mock_email.call_count == 1


@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_no_user_returns_200_skipped(
    mock_construct, webhook_secret, api_client, seeded,
):
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(customer='cus_UNKNOWN', plan_slug=None),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert response.json().get('skipped') is True
    row = StripeWebhookEvent.objects.get(id=event['id'])
    assert row.processed_status == 'skipped'


@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_unknown_price_500_retries(
    mock_construct, webhook_secret, api_client, paid_user,
):
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_NEVER_SYNCED',
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 500
    row = StripeWebhookEvent.objects.get(id=event['id'])
    assert row.processed_status == 'error'


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_slug_price_mismatch_warns_price_wins(
    mock_construct, mock_email, webhook_secret, api_client, paid_user, caplog,
):
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug='plus',
            price_id='price_PRO_M',
        ),
    )
    mock_construct.return_value = event
    with caplog.at_level(logging.WARNING):
        response = _post(api_client)
    assert response.status_code == 200
    # price_id wins over conflicting slug.
    assert UserSubscription.objects.get(user=paid_user).plan.name == 'pro'
    assert any(
        'plan_resolution_mismatch' in r.message for r in caplog.records
    )


# ---------------------------------------------------------------------
# customer.subscription.created — superseded-subscription cancelation
# (belt+braces for the paid→paid double-subscription defect)
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('audit_logging.services.AuditService.log_action')
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.delete')
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.retrieve')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_cancels_superseded_active_subscription(
    mock_construct, mock_retrieve, mock_delete, mock_email, mock_audit,
    webhook_secret, api_client, paid_user,
):
    """If a second Checkout slipped through, the .created webhook for
    the NEW subscription cancels the OLD one so the user isn't
    double-charged."""
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.update_or_create(
        user=paid_user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_OLD',
        },
    )
    mock_retrieve.return_value = {'id': 'sub_OLD', 'status': 'active'}
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            sub_id='sub_NEW', customer='cus_TEST',
            plan_slug='pro', price_id='price_PRO_M',
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'pro'
    assert sub.stripe_subscription_id == 'sub_NEW'
    mock_retrieve.assert_called_once_with('sub_OLD')
    mock_delete.assert_called_once_with('sub_OLD')
    assert mock_audit.call_count == 1
    assert mock_audit.call_args.kwargs['action'] == (
        'stripe_superseded_subscription_canceled'
    )


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.delete')
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.retrieve')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_superseded_already_canceled_is_noop(
    mock_construct, mock_retrieve, mock_delete, mock_email,
    webhook_secret, api_client, paid_user,
):
    """Idempotency: replaying the .created event after the old sub was
    already canceled must not call delete again."""
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.update_or_create(
        user=paid_user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_OLD',
        },
    )
    mock_retrieve.return_value = {'id': 'sub_OLD', 'status': 'canceled'}
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            sub_id='sub_NEW', customer='cus_TEST',
            plan_slug='pro', price_id='price_PRO_M',
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    mock_delete.assert_not_called()
    assert UserSubscription.objects.get(
        user=paid_user,
    ).stripe_subscription_id == 'sub_NEW'


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.delete')
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.retrieve')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_superseded_cancel_failure_still_ok(
    mock_construct, mock_retrieve, mock_delete, mock_email,
    webhook_secret, api_client, paid_user, caplog,
):
    """A Stripe error while canceling the old sub must not fail the
    webhook — the row mutation already happened; the failure is logged
    for operator follow-up."""
    caplog.set_level(
        logging.ERROR, logger='usage_quota.services.stripe_webhooks',
    )
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.update_or_create(
        user=paid_user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_OLD',
        },
    )
    mock_retrieve.return_value = {'id': 'sub_OLD', 'status': 'active'}
    mock_delete.side_effect = stripe.error.APIError('stripe down')
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            sub_id='sub_NEW', customer='cus_TEST',
            plan_slug='pro', price_id='price_PRO_M',
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    row = StripeWebhookEvent.objects.get(id=event['id'])
    assert row.processed_status == 'ok'
    assert UserSubscription.objects.get(
        user=paid_user,
    ).stripe_subscription_id == 'sub_NEW'
    assert any(
        'superseded_subscription_cancel_failed' in r.message
        for r in caplog.records
    )


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.delete')
@patch('usage_quota.services.stripe_webhooks.stripe.Subscription.retrieve')
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_created_same_sub_id_does_not_cancel(
    mock_construct, mock_email, mock_retrieve, mock_delete,
    webhook_secret, api_client, paid_user,
):
    """Replaying .created for the row's own subscription id must not
    touch Stripe at all."""
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.update_or_create(
        user=paid_user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_X',
        },
    )
    event = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(sub_id='sub_X', customer='cus_TEST'),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    mock_retrieve.assert_not_called()
    mock_delete.assert_not_called()


# ---------------------------------------------------------------------
# Out-of-order delivery guard (stripe_event_created marker)
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_late_subscription_created_does_not_overwrite_newer_plan(
    mock_construct, mock_email, webhook_secret, api_client, paid_user,
):
    """A late-delivered .created (older event.created) must not clobber
    a newer plan change that was already applied."""
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.update_or_create(
        user=paid_user,
        defaults={
            'plan': plus, 'is_active': True,
            'stripe_subscription_id': 'sub_X',
        },
    )

    # Newer .updated: plus → pro at event.created = 2000.
    newer = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PRO_M', period_end=1800000000,
        ),
    )
    newer['created'] = 2000
    mock_construct.return_value = newer
    assert _post(api_client).status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'pro'
    assert sub.stripe_event_created == 2000

    # Late .created from the original checkout (event.created = 1000).
    late = _evt(
        event_type='customer.subscription.created',
        obj=_sub_obj(
            sub_id='sub_STALE', customer='cus_TEST',
            plan_slug='plus', price_id='price_PLUS_M',
        ),
    )
    late['created'] = 1000
    mock_construct.return_value = late
    response = _post(api_client)
    assert response.status_code == 200
    sub.refresh_from_db()
    assert sub.plan.name == 'pro'                    # not clobbered
    assert sub.stripe_subscription_id == 'sub_X'     # not clobbered
    assert sub.stripe_event_created == 2000
    # Only the first (applied) event sent a plan-change email.
    assert mock_email.call_count == 1


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_late_subscription_deleted_does_not_downgrade_resubscribed_user(
    mock_construct, mock_cancel, webhook_secret, api_client, paid_user,
):
    """.deleted for an OLD subscription delivered after the user already
    re-subscribed (newer marker) must not downgrade the new plan."""
    pro = SubscriptionPlan.objects.get(name='pro')
    UserSubscription.objects.update_or_create(
        user=paid_user,
        defaults={
            'plan': pro, 'is_active': True,
            'stripe_subscription_id': 'sub_NEW',
            'stripe_event_created': 2000,
        },
    )
    late_delete = _evt(
        event_type='customer.subscription.deleted',
        obj=_sub_obj(sub_id='sub_OLD', customer='cus_TEST', plan_slug=None),
    )
    late_delete['created'] = 1000
    mock_construct.return_value = late_delete
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'pro'
    assert sub.stripe_subscription_id == 'sub_NEW'
    assert mock_cancel.call_count == 0


# ---------------------------------------------------------------------
# customer.subscription.updated
# ---------------------------------------------------------------------

def _seed_user_subscription(user, plan_name='plus', **kwargs):
    plan = SubscriptionPlan.objects.get(name=plan_name)
    defaults = {
        'plan': plan,
        'stripe_subscription_id': 'sub_X',
        'is_active': True,
        'current_period_end': 1700000000,
        'cancel_at_period_end': False,
    }
    defaults.update(kwargs)
    UserSubscription.objects.update_or_create(user=user, defaults=defaults)


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_plan_change_updates_row_and_sends_email(
    mock_construct, mock_cancel, mock_change,
    webhook_secret, api_client, paid_user,
):
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PRO_M', period_end=1800000000,
        ),
        previous_attributes={'items': {'data': [{'price': {'id': 'price_PLUS_M'}}]}},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'pro'
    assert sub.current_period_end == 1800000000
    assert mock_change.call_count == 1
    args, _kw = mock_change.call_args
    assert args[0] == paid_user
    assert args[1].name == 'plus'  # from_plan
    assert args[2].name == 'pro'   # to_plan
    assert mock_cancel.call_count == 0


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_cancel_at_period_end_set_sends_cancel(
    mock_construct, mock_cancel, webhook_secret, api_client, paid_user,
):
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M', cancel_at_period_end=True,
            period_end=1799999999,
        ),
        previous_attributes={'cancel_at_period_end': False},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert UserSubscription.objects.get(
        user=paid_user,
    ).cancel_at_period_end is True
    assert mock_cancel.call_count == 1
    _args, kwargs = mock_cancel.call_args
    assert 'period_end' in kwargs
    assert kwargs['period_end']  # non-empty formatted string


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_cancel_reverted_no_email(
    mock_construct, mock_cancel, webhook_secret, api_client, paid_user,
):
    _seed_user_subscription(
        paid_user, plan_name='plus', cancel_at_period_end=True,
    )
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M', cancel_at_period_end=False,
        ),
        previous_attributes={'cancel_at_period_end': True},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert UserSubscription.objects.get(
        user=paid_user,
    ).cancel_at_period_end is False
    assert mock_cancel.call_count == 0


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_payment_failed')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_past_due_does_not_send_dunning(
    mock_construct, mock_dunning, webhook_secret, api_client, paid_user,
):
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M', sub_status='past_due',
        ),
        previous_attributes={'status': 'active'},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    # invoice.payment_failed is the sole dunning trigger.
    assert mock_dunning.call_count == 0


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_payment_failed')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_past_due_sparse_diff_no_dunning(
    mock_construct, mock_dunning, webhook_secret, api_client, paid_user,
):
    """Regression: nuisance .updated during Smart Retries — sparse diff
    without ``status``. .updated must NOT send dunning."""
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M', sub_status='past_due',
        ),
        previous_attributes={'latest_invoice': 'in_old'},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert mock_dunning.call_count == 0


@pytest.mark.django_db
@pytest.mark.parametrize('terminal_status', ['unpaid', 'incomplete_expired'])
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_dunning_terminal_status_downgrades_to_free(
    mock_construct, mock_cancel, webhook_secret, api_client, paid_user,
    terminal_status,
):
    """Dunning terminal states (Smart Retries exhausted / incomplete
    window expired) must downgrade in code — Stripe only emits .deleted
    if 'cancel subscription' is configured, so without this the user
    keeps paid limits forever while never paying."""
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M', sub_status=terminal_status,
        ),
        previous_attributes={'status': 'past_due'},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'free'
    assert sub.stripe_subscription_id is None
    assert sub.current_period_end is None
    assert sub.cancel_at_period_end is False
    assert sub.session_window_start is None
    assert mock_cancel.call_count == 1


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_past_due_is_grace_no_downgrade(
    mock_construct, mock_cancel, webhook_secret, api_client, paid_user,
    caplog,
):
    """'past_due' stays a grace period: plan untouched, structured log
    only. The downgrade waits for 'unpaid'/'incomplete_expired' or
    .deleted."""
    caplog.set_level(
        logging.INFO, logger='usage_quota.services.stripe_webhooks',
    )
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M', sub_status='past_due',
        ),
        previous_attributes={'status': 'active'},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'plus'
    assert sub.stripe_subscription_id == 'sub_X'
    assert mock_cancel.call_count == 0
    assert any(
        'dunning_grace' in r.message for r in caplog.records
    )


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_plan_change_email')
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_no_relevant_diff_is_idempotent_noop(
    mock_construct, mock_cancel, mock_change,
    webhook_secret, api_client, paid_user,
):
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M', period_end=1700000000,
        ),
        previous_attributes={'latest_invoice': 'in_old'},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert mock_change.call_count == 0
    assert mock_cancel.call_count == 0


@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_unknown_price_warns_no_clobber(
    mock_construct, webhook_secret, api_client, paid_user, caplog,
):
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_NOT_SYNCED',
        ),
    )
    mock_construct.return_value = event
    with caplog.at_level(logging.WARNING):
        response = _post(api_client)
    assert response.status_code == 200
    # plan unchanged
    assert UserSubscription.objects.get(user=paid_user).plan.name == 'plus'
    assert any(
        'updated_unknown_price' in r.message for r in caplog.records
    )


@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_downgrade_resets_session_window(
    mock_construct, webhook_secret, api_client, paid_user,
):
    from django.utils import timezone
    _seed_user_subscription(
        paid_user, plan_name='pro',
        session_window_start=timezone.now(),
    )
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PLUS_M',
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'plus'
    assert sub.session_window_start is None


@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_updated_upgrade_preserves_session_window(
    mock_construct, webhook_secret, api_client, paid_user,
):
    from django.utils import timezone
    window = timezone.now()
    _seed_user_subscription(
        paid_user, plan_name='plus', session_window_start=window,
    )
    event = _evt(
        event_type='customer.subscription.updated',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            price_id='price_PRO_M',
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'pro'
    assert sub.session_window_start is not None
    # window preserved (within microseconds)
    assert abs((sub.session_window_start - window).total_seconds()) < 1


# ---------------------------------------------------------------------
# customer.subscription.deleted
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_deleted_downgrades_to_free(
    mock_construct, mock_cancel, webhook_secret, api_client, paid_user,
):
    from django.utils import timezone
    _seed_user_subscription(
        paid_user, plan_name='plus',
        session_window_start=timezone.now(),
    )
    event = _evt(
        event_type='customer.subscription.deleted',
        obj=_sub_obj(customer='cus_TEST', plan_slug=None),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    sub = UserSubscription.objects.get(user=paid_user)
    assert sub.plan.name == 'free'
    assert sub.stripe_subscription_id is None
    assert sub.current_period_end is None
    assert sub.cancel_at_period_end is False
    assert sub.session_window_start is None
    assert mock_cancel.call_count == 1


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_canceled')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_subscription_deleted_was_free_no_email(
    mock_construct, mock_cancel, webhook_secret, api_client, paid_user,
):
    _seed_user_subscription(paid_user, plan_name='free')
    event = _evt(
        event_type='customer.subscription.deleted',
        obj=_sub_obj(customer='cus_TEST', plan_slug=None),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert mock_cancel.call_count == 0


# ---------------------------------------------------------------------
# invoice.payment_succeeded
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_receipt')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_invoice_payment_succeeded_sends_receipt_with_vat(
    mock_construct, mock_receipt, webhook_secret, api_client, paid_user,
):
    """B2C invoice with VAT (19% German rate) → richer invoice_data."""
    _seed_user_subscription(paid_user, plan_name='plus')
    invoice = _invoice_obj(customer='cus_TEST', amount_paid=2380)
    invoice['subtotal'] = 2000
    invoice['tax'] = 380
    invoice['status_transitions'] = {'paid_at': 1700001000}
    invoice['total_tax_amounts'] = [{
        'amount': 380,
        'tax_rate': {
            'percentage': 19.0, 'display_name': 'VAT',
        },
    }]
    event = _evt(event_type='invoice.payment_succeeded', obj=invoice)
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert mock_receipt.call_count == 1
    args, _kw = mock_receipt.call_args
    assert args[0] == paid_user
    inv = args[1]
    assert inv['amount_display'].startswith('$23.80')
    assert inv['subtotal_display'].startswith('$20.00')
    assert inv['tax_display'].startswith('$3.80')
    assert inv['tax_rate_display'] == 'VAT 19%'
    assert inv['hosted_invoice_url'] == 'https://pdf.example'
    assert inv['invoice_pdf'] == 'https://pdf.example'
    assert inv['date_paid_display'] == '2023-11-14'  # 1700001000 UTC
    assert inv['plan_name'] == 'Plus'
    # No longer-existing key:
    assert 'invoice_pdf_url' not in inv


@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_receipt')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_invoice_payment_succeeded_no_vat_omits_tax_fields(
    mock_construct, mock_receipt, webhook_secret, api_client, paid_user,
):
    """Reverse-charge B2B invoice: Stripe sets tax=0, no total_tax_amounts.

    Receipt template gates on tax_display, so an empty string omits
    the VAT row.
    """
    _seed_user_subscription(paid_user, plan_name='plus')
    invoice = _invoice_obj(customer='cus_TEST', amount_paid=2000)
    invoice['subtotal'] = 2000
    invoice['tax'] = 0
    invoice['status_transitions'] = {'paid_at': 1700001000}
    invoice['total_tax_amounts'] = []
    event = _evt(event_type='invoice.payment_succeeded', obj=invoice)
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    inv = mock_receipt.call_args.args[1]
    assert inv['tax_display'] == ''
    assert inv['tax_rate_display'] == ''
    assert inv['subtotal_display'].startswith('$20.00')
    assert inv['amount_display'].startswith('$20.00')


# ---------------------------------------------------------------------
# invoice.payment_failed
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_payment_failed')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_invoice_payment_failed_sends_dunning(
    mock_construct, mock_dunning, webhook_secret, api_client, paid_user,
):
    _seed_user_subscription(paid_user, plan_name='plus')
    event = _evt(
        event_type='invoice.payment_failed',
        obj=_invoice_obj(customer='cus_TEST'),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert mock_dunning.call_count == 1


# ---------------------------------------------------------------------
# customer.subscription.trial_will_end
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.services.stripe_webhooks.send_subscription_trial_ending')
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_trial_will_end_sends_reminder(
    mock_construct, mock_trial, webhook_secret, api_client, paid_user,
):
    event = _evt(
        event_type='customer.subscription.trial_will_end',
        obj=_sub_obj(
            customer='cus_TEST', plan_slug=None,
            trial_end=1799999999,
        ),
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    assert mock_trial.call_count == 1
    _args, kwargs = mock_trial.call_args
    assert kwargs.get('trial_end')


# ---------------------------------------------------------------------
# Unknown event type
# ---------------------------------------------------------------------

@pytest.mark.django_db
@patch('usage_quota.views.stripe.Webhook.construct_event')
def test_unhandled_event_type_returns_200_skipped(
    mock_construct, webhook_secret, api_client, seeded,
):
    event = _evt(
        event_type='charge.refunded',
        obj={'id': 'ch_X', 'customer': 'cus_TEST'},
    )
    mock_construct.return_value = event
    response = _post(api_client)
    assert response.status_code == 200
    row = StripeWebhookEvent.objects.get(id=event['id'])
    assert row.processed_status == 'skipped'


# ---------------------------------------------------------------------
# Admin Replay
# ---------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_replay_resets_status_and_re_dispatches(seeded, paid_user):
    from django.contrib.admin.sites import AdminSite
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory
    from unittest.mock import patch as _patch

    from usage_quota.admin import StripeWebhookEventAdmin

    evt_id = 'evt_admin_replay_001'
    payload = {
        'id': evt_id,
        'type': 'customer.subscription.created',
        'data': {'object': _sub_obj(customer='cus_TEST')},
    }
    row = StripeWebhookEvent.objects.create(
        id=evt_id,
        type='customer.subscription.created',
        payload=payload,
        processed_status='error',
        error_message='prior failure',
    )

    admin_user = User.objects.create_user(
        email='admin@t.com', password='x', is_verified=True, is_staff=True,
    )
    request = RequestFactory().post('/admin/')
    request.user = admin_user
    request.session = SessionStore()
    request._messages = FallbackStorage(request)

    site = StripeWebhookEventAdmin(StripeWebhookEvent, AdminSite())
    with _patch(
        'usage_quota.services.stripe_webhooks.send_plan_change_email',
    ) as mock_email:
        site.replay_events(request, StripeWebhookEvent.objects.filter(id=evt_id))

    row.refresh_from_db()
    assert row.processed_status == 'ok'
    assert row.error_message is None
    assert mock_email.call_count == 1


def _admin_replay_request():
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory

    admin_user = User.objects.create_user(
        email=f'admin-{uuid.uuid4().hex[:8]}@t.com', password='x',
        is_verified=True, is_staff=True,
    )
    request = RequestFactory().post('/admin/')
    request.user = admin_user
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
def test_admin_replay_reclaims_stale_processing_row(seeded, paid_user):
    """Mirror of the webhook view's stale-claim CAS: an abandoned
    'processing' claim (older than PROCESSING_CLAIM_TTL) is replayable
    from the admin."""
    from django.contrib.admin.sites import AdminSite
    from unittest.mock import patch as _patch

    from usage_quota.admin import StripeWebhookEventAdmin

    evt_id = 'evt_admin_stale_001'
    payload = {
        'id': evt_id,
        'type': 'customer.subscription.created',
        'data': {'object': _sub_obj(customer='cus_TEST')},
    }
    row = StripeWebhookEvent.objects.create(
        id=evt_id,
        type='customer.subscription.created',
        payload=payload,
        processed_status='processing',
        claimed_at=timezone.now() - timedelta(minutes=6),
    )

    site = StripeWebhookEventAdmin(StripeWebhookEvent, AdminSite())
    with _patch(
        'usage_quota.services.stripe_webhooks.send_plan_change_email',
    ) as mock_email:
        site.replay_events(
            _admin_replay_request(),
            StripeWebhookEvent.objects.filter(id=evt_id),
        )

    row.refresh_from_db()
    assert row.processed_status == 'ok'
    assert mock_email.call_count == 1


@pytest.mark.django_db
def test_admin_replay_skips_fresh_processing_row(seeded, paid_user):
    """A fresh 'processing' claim belongs to a live worker — the admin
    replay must not double-dispatch it."""
    from django.contrib.admin.sites import AdminSite
    from unittest.mock import patch as _patch

    from usage_quota.admin import StripeWebhookEventAdmin

    evt_id = 'evt_admin_fresh_001'
    payload = {
        'id': evt_id,
        'type': 'customer.subscription.created',
        'data': {'object': _sub_obj(customer='cus_TEST')},
    }
    row = StripeWebhookEvent.objects.create(
        id=evt_id,
        type='customer.subscription.created',
        payload=payload,
        processed_status='processing',
        claimed_at=timezone.now(),
    )

    site = StripeWebhookEventAdmin(StripeWebhookEvent, AdminSite())
    with _patch(
        'usage_quota.services.stripe_webhooks.send_plan_change_email',
    ) as mock_email:
        site.replay_events(
            _admin_replay_request(),
            StripeWebhookEvent.objects.filter(id=evt_id),
        )

    row.refresh_from_db()
    assert row.processed_status == 'processing'
    assert mock_email.call_count == 0
