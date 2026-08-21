"""Shared fixtures for task-12 billing tests."""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from authentication.jwt_utils import JWTManager
from authentication.models import User
from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.models import SubscriptionPlan


@pytest.fixture(autouse=True)
def _patch_stripe_customer_create():
    """Patch ``stripe.Customer.create`` for every billing test.

    Each test that creates a ``User`` triggers the post_save signal,
    which (under ``CELERY_TASK_ALWAYS_EAGER``) calls
    ``ensure_stripe_customer`` → ``get_or_create_stripe_customer`` →
    ``stripe.Customer.create``. If the test toggled ``STRIPE_API_KEY``
    to a fake test key, that real Stripe call would hit the network.
    Patching at the module level keeps the signal harmless without
    requiring every test to wrap user creation in a ``with patch``.
    """
    with patch(
        'stripe.Customer.create',
        return_value=MagicMock(id='cus_AUTO_PATCHED'),
    ) as m:
        yield m


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def seeded(db):
    """Seed canonical tiers + stamp test Stripe price ids on plus/pro."""
    seed_tiers_for_tests()
    SubscriptionPlan.objects.filter(name='plus').update(
        stripe_price_id_monthly='price_PLUS_M',
        stripe_price_id_yearly='price_PLUS_Y',
    )
    SubscriptionPlan.objects.filter(name='pro').update(
        stripe_price_id_monthly='price_PRO_M',
        stripe_price_id_yearly='price_PRO_Y',
    )


@pytest.fixture
def verified_free_user(seeded):
    """A verified user with stripe_customer_id pre-set; no UserSubscription row.

    Note: ``BillingService.get_user_plan`` goes through
    ``QuotaService._get_or_create_subscription`` and lazily creates a
    Free-plan ``UserSubscription`` row on first read. Tests upgrading to
    ``plus`` / ``pro`` still pass because the auto-created plan is Free.
    """
    user = User.objects.create_user(
        email='free@t.com', password='x', is_verified=True,
    )
    user.stripe_customer_id = 'cus_TEST'
    user.save()
    return user


@pytest.fixture
def auth_as():
    """Factory: attach a JWT for ``user`` to ``client``.

    Uses the project's custom ``JWTManager`` (payload shape ``type:
    access``) which our ``authentication.authentication.JWTAuthentication``
    backend expects. ``rest_framework_simplejwt.RefreshToken`` would emit
    ``token_type: access`` instead and the custom auth would reject it.
    """
    def _auth(client, user):
        access_token = JWTManager.create_access_token(user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        return client
    return _auth
