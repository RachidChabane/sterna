"""Task-29 C1 regression: quota endpoints must derive user from JWT,
not from a body-supplied ``user_id``.

Previously, ``check_quota`` / ``deduct_usage`` looked up the target
user with ``User.objects.get(id=data['user_id'])`` and only required
``IsAuthenticated``. Any user A could pass user B's UUID and either
exhaust B's weekly budget (DoS) or enumerate B's quota state.

After the fix:
- the serializer no longer declares a ``user_id`` field;
- the views use ``request.user`` exclusively;
- DRF silently ignores the extra ``user_id`` key in the body.

These tests assert all three properties stay true.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from authentication.models import User


pytestmark = pytest.mark.django_db


@pytest.fixture
def user_a(seeded):
    return User.objects.create_user(email="a@t.com", password="x", is_verified=True)


@pytest.fixture
def user_b(seeded):
    return User.objects.create_user(email="b@t.com", password="x", is_verified=True)


def test_check_quota_uses_request_user_not_body(
    api_client, auth_as, user_a, user_b
):
    """POST as A with user_id=B in body — quota MUST reflect A, not B.

    Strong assertion: pre-deduct B to a known weekly_used state. Then
    A's check_quota response must report A's remaining quota (full
    allowance), NOT B's diminished allowance. A 200 alone is necessary
    but not sufficient.
    """
    from decimal import Decimal

    from usage_quota.services.quota_service import get_quota_service

    quota_service = get_quota_service()
    # Burn B's quota down so any leak would show up as A's remaining
    # being lower than expected.
    quota_service.deduct_usage(
        user=user_b,
        service="brave_search",
        cost_usd=Decimal("5.00"),
        feature="search",
    )

    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("usage_quota:quota-check"),
        data={
            "user_id": str(user_b.id),  # attacker-supplied — must be ignored
            "service": "brave_search",
            "estimated_cost_usd": "0.001",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    # A's remaining quota must be UNAFFECTED by B's $5 burn.
    a_sub = quota_service._get_or_create_subscription(user_a)
    expected_remaining = a_sub.effective_weekly_limit
    actual_remaining = Decimal(response.data["remaining_weekly_usd"])
    assert actual_remaining >= expected_remaining - Decimal("0.01"), (
        f"Cross-tenant leak: A's remaining_weekly_usd={actual_remaining} "
        f"is less than A's effective_weekly_limit={expected_remaining} — "
        f"the view returned B's diminished quota state."
    )


def test_deduct_usage_uses_request_user_not_body(
    api_client, auth_as, user_a, user_b
):
    """POST as A with user_id=B — B's usage MUST be unchanged; A's increments."""
    from usage_quota.services.quota_service import get_quota_service

    quota_service = get_quota_service()
    # Snapshot B's pre-state by creating the subscription lazily.
    b_sub_before = quota_service._get_or_create_subscription(user_b)
    b_weekly_used_before = quota_service.get_weekly_usage(
        user_b, b_sub_before.weekly_window_start
    )

    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("usage_quota:quota-deduct"),
        data={
            "user_id": str(user_b.id),  # attacker-supplied — must be ignored
            "service": "brave_search",
            "cost_usd": "0.010",
        },
        format="json",
    )
    assert response.status_code == 200, response.data

    # B's weekly usage MUST not have changed.
    b_weekly_used_after = quota_service.get_weekly_usage(
        user_b, b_sub_before.weekly_window_start
    )
    assert b_weekly_used_after == b_weekly_used_before, (
        f"Cross-tenant deduction leaked: B's weekly_used went from "
        f"{b_weekly_used_before} to {b_weekly_used_after}"
    )

    # A's weekly usage MUST reflect the deducted amount.
    a_sub = quota_service._get_or_create_subscription(user_a)
    a_weekly_used = quota_service.get_weekly_usage(
        user_a, a_sub.weekly_window_start
    )
    assert a_weekly_used >= Decimal("0.010"), (
        f"A's weekly usage did not increase as expected: {a_weekly_used}"
    )


def test_check_quota_rejects_unauthenticated(api_client, seeded):
    response = api_client.post(
        reverse("usage_quota:quota-check"),
        data={"service": "brave_search", "estimated_cost_usd": "0.001"},
        format="json",
    )
    assert response.status_code == 401


def test_deduct_usage_rejects_unauthenticated(api_client, seeded):
    response = api_client.post(
        reverse("usage_quota:quota-deduct"),
        data={"service": "brave_search", "cost_usd": "0.001"},
        format="json",
    )
    assert response.status_code == 401


def test_serializer_drops_unknown_user_id_field(api_client, auth_as, user_a):
    """Regression guard: DRF must silently ignore the now-removed user_id."""
    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("usage_quota:quota-check"),
        data={
            "user_id": "00000000-0000-0000-0000-000000000999",
            "service": "brave_search",
        },
        format="json",
    )
    # Even with an unknown user_id (bad UUID format wouldn't matter
    # since the field is no longer in the serializer schema), the
    # request succeeds because the field is silently dropped.
    assert response.status_code == 200, response.data
