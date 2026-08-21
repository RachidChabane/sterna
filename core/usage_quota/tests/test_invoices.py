"""Tests for ``GET /api/billing/invoices/`` (task 14).

Patch surface: ``usage_quota.views.stripe.Invoice.list``.
``api_client``, ``seeded``, ``verified_free_user``, ``auth_as``
come from ``conftest.py``.
"""

from unittest.mock import MagicMock, patch

import pytest
import stripe

from authentication.models import User


def _invoice_list(items, has_more=False):
    """Mock for ``stripe.Invoice.list`` return value.

    The view reads ``.data`` directly (first page only), per the
    24-row cap. We deliberately expose ``.data`` and rig
    ``.auto_paging_iter`` as a trip-wire: if the view ever regresses
    to calling the paginator, the test fails loudly.
    """
    m = MagicMock()
    m.data = list(items)
    m.has_more = has_more
    m.auto_paging_iter.side_effect = AssertionError(
        "auto_paging_iter must not be called — see plan §1.6 (24-row cap)"
    )
    return m


def _mock_invoice(**kw):
    defaults = {
        'id': 'in_TEST',
        'number': 'INV-0001',
        'created': 1700000000,
        'total': 2400,
        'subtotal': 2000,
        'tax': 400,
        'currency': 'eur',
        'status': 'paid',
        'hosted_invoice_url': 'https://invoice.stripe.com/i/test',
        'invoice_pdf': 'https://invoice.stripe.com/p/test/pdf',
    }
    defaults.update(kw)
    obj = MagicMock(spec_set=list(defaults.keys()) + ['lines'])
    for k, v in defaults.items():
        setattr(obj, k, v)
    # Default lines structure for _resolve_plan_name_from_invoice
    obj.lines = MagicMock(data=[MagicMock(
        price=MagicMock(id='price_PLUS_M'),
    )])
    return obj


@pytest.mark.django_db
def test_unauthenticated_returns_401(api_client):
    response = api_client.get('/api/billing/invoices/')
    assert response.status_code == 401


@pytest.mark.django_db
def test_free_user_no_customer_id_returns_empty_list(
    seeded, api_client, auth_as,
):
    user = User.objects.create_user(
        email='free-nocus@t.com', password='x', is_verified=True,
    )
    # The autouse stripe.Customer.create patch may have set the
    # customer id via the post_save signal; force it back to None
    # to test the "user genuinely has no Stripe customer" path.
    user.stripe_customer_id = None
    user.save(update_fields=['stripe_customer_id'])
    auth_as(api_client, user)
    with patch('usage_quota.views.stripe.Invoice.list') as m:
        response = api_client.get('/api/billing/invoices/')
    assert response.status_code == 200
    assert response.json() == {'results': []}
    m.assert_not_called()


@pytest.mark.django_db
def test_returns_trimmed_invoice_fields(
    seeded, api_client, verified_free_user, auth_as,
):
    auth_as(api_client, verified_free_user)
    inv = _mock_invoice()
    with patch(
        'usage_quota.views.stripe.Invoice.list',
        return_value=_invoice_list([inv]),
    ) as m:
        response = api_client.get('/api/billing/invoices/')
    assert response.status_code == 200
    body = response.json()
    assert 'results' in body
    assert len(body['results']) == 1
    row = body['results'][0]
    # Whitelisted fields only:
    assert set(row.keys()) == {
        'id', 'number', 'created', 'total', 'subtotal_excl_tax',
        'tax', 'currency', 'status', 'hosted_invoice_url',
        'invoice_pdf', 'plan_name',
    }
    assert row['id'] == 'in_TEST'
    assert row['total'] == 2400
    assert row['subtotal_excl_tax'] == 2000
    assert row['tax'] == 400
    assert row['currency'] == 'eur'
    assert row['plan_name'] == 'Plus'
    # Stripe API called with customer scoping AND lines.data.price
    # expansion (required for _resolve_plan_name_from_invoice).
    assert m.call_args.kwargs == {
        'customer': verified_free_user.stripe_customer_id,
        'limit': 24,
        'expand': ['data.lines.data.price'],
    }


@pytest.mark.django_db
def test_cross_user_isolation(
    seeded, api_client, auth_as,
):
    """User A's invoices list query passes ONLY user A's customer
    id to Stripe — never user B's.
    """
    user_a = User.objects.create_user(
        email='a@t.com', password='x', is_verified=True,
    )
    user_a.stripe_customer_id = 'cus_A'
    user_a.save()
    user_b = User.objects.create_user(
        email='b@t.com', password='x', is_verified=True,
    )
    user_b.stripe_customer_id = 'cus_B'
    user_b.save()

    auth_as(api_client, user_a)
    inv_a = _mock_invoice(id='in_A')
    with patch(
        'usage_quota.views.stripe.Invoice.list',
        return_value=_invoice_list([inv_a]),
    ) as m:
        response = api_client.get('/api/billing/invoices/')
    assert response.status_code == 200
    assert m.call_args.kwargs['customer'] == 'cus_A'
    assert m.call_args.kwargs['customer'] != 'cus_B'


@pytest.mark.django_db
def test_stripe_error_returns_502(
    seeded, api_client, verified_free_user, auth_as,
):
    auth_as(api_client, verified_free_user)
    with patch(
        'usage_quota.views.stripe.Invoice.list',
        side_effect=stripe.error.APIConnectionError('network blip'),
    ):
        response = api_client.get('/api/billing/invoices/')
    assert response.status_code == 502
    assert response.json()['error'] == 'stripe_error'


@pytest.mark.django_db
def test_zero_invoices_returns_empty_results(
    seeded, api_client, verified_free_user, auth_as,
):
    auth_as(api_client, verified_free_user)
    with patch(
        'usage_quota.views.stripe.Invoice.list',
        return_value=_invoice_list([]),
    ):
        response = api_client.get('/api/billing/invoices/')
    assert response.status_code == 200
    assert response.json() == {'results': []}


@pytest.mark.django_db
def test_does_not_paginate_beyond_first_page(
    seeded, api_client, verified_free_user, auth_as,
):
    """24-row hard cap: even if Stripe reports has_more=True, the
    view must NOT auto-page through subsequent results.

    Two enforcements:
      1. _invoice_list rigs auto_paging_iter to raise on call (trip-wire).
      2. We assert stripe.Invoice.list is called exactly once.
    """
    auth_as(api_client, verified_free_user)
    invoices = [
        _mock_invoice(id=f'in_{i}', number=f'INV-{i:04d}')
        for i in range(24)
    ]
    with patch(
        'usage_quota.views.stripe.Invoice.list',
        return_value=_invoice_list(invoices, has_more=True),
    ) as m:
        response = api_client.get('/api/billing/invoices/')
    assert response.status_code == 200
    assert m.call_count == 1
    body = response.json()
    assert len(body['results']) == 24
