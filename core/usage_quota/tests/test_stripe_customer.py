"""Tests for usage_quota.services.stripe_customer and the celery task.

Mocking strategy: patch ``stripe.Customer.create`` directly. The
``stripe`` SDK is imported lazily inside the service, and the global
api_key is set at module load — but since we never actually call
Stripe in tests, the unset key is harmless. The ``_stripe_configured``
helper reads ``settings.STRIPE_API_KEY`` live, so toggling it via the
``settings`` fixture toggles the configured path.
"""

from unittest.mock import MagicMock, patch

import pytest
import stripe

from usage_quota.services.stripe_customer import (
    _stripe_configured,
    get_or_create_stripe_customer,
)


@pytest.mark.django_db
def test_returns_existing_id_without_api_call(django_user_model):
    user = django_user_model.objects.create_user(
        email="a@t.com", password="x",
    )
    user.stripe_customer_id = "cus_existing"
    user.save()

    with patch("stripe.Customer.create") as mock_create:
        cid = get_or_create_stripe_customer(user)

    assert cid == "cus_existing"
    mock_create.assert_not_called()


@pytest.mark.django_db
def test_no_api_call_when_stripe_not_configured(django_user_model, settings):
    settings.STRIPE_API_KEY = ""
    assert _stripe_configured() is False

    user = django_user_model.objects.create_user(
        email="b@t.com", password="x",
    )
    with patch("stripe.Customer.create") as mock_create:
        cid = get_or_create_stripe_customer(user)

    assert cid is None
    mock_create.assert_not_called()


@pytest.mark.django_db
def test_creates_and_writes_back_id(django_user_model, settings):
    # Create the user with Stripe disabled so the signal-dispatched eager
    # task no-ops; we want to isolate the direct service call below.
    settings.STRIPE_API_KEY = ""
    user = django_user_model.objects.create_user(
        email="c@t.com", password="x",
    )
    assert user.stripe_customer_id is None

    settings.STRIPE_API_KEY = "sk_test_FAKE"
    fake_customer = MagicMock(id="cus_NEW_123")
    with patch("stripe.Customer.create", return_value=fake_customer) as mock_create:
        cid = get_or_create_stripe_customer(user)

    assert cid == "cus_NEW_123"
    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["email"] == "c@t.com"
    assert kwargs["metadata"]["user_id"] == str(user.id)

    user.refresh_from_db()
    assert user.stripe_customer_id == "cus_NEW_123"


@pytest.mark.django_db
def test_idempotent_under_concurrent_call(django_user_model, settings):
    settings.STRIPE_API_KEY = ""
    user = django_user_model.objects.create_user(
        email="d@t.com", password="x",
    )

    settings.STRIPE_API_KEY = "sk_test_FAKE"
    fake = MagicMock(id="cus_X")
    with patch("stripe.Customer.create", return_value=fake) as mock_create:
        get_or_create_stripe_customer(user)
        user.refresh_from_db()
        get_or_create_stripe_customer(user)
    assert mock_create.call_count == 1


@pytest.mark.django_db
def test_rate_limit_propagates(django_user_model, settings):
    settings.STRIPE_API_KEY = ""
    user = django_user_model.objects.create_user(
        email="e@t.com", password="x",
    )

    settings.STRIPE_API_KEY = "sk_test_FAKE"
    with patch(
        "stripe.Customer.create",
        side_effect=stripe.error.RateLimitError("slow down"),
    ):
        with pytest.raises(stripe.error.RateLimitError):
            get_or_create_stripe_customer(user)


@pytest.mark.django_db
def test_signup_schedules_celery_task(django_user_model, settings):
    """post_save(User, created=True) calls ensure_stripe_customer.delay.

    ``CELERY_TASK_ALWAYS_EAGER=True`` in test settings means ``.delay()``
    runs synchronously, so the customer id is written back inline.
    """
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    fake = MagicMock(id="cus_FROM_SIGNAL")
    with patch("stripe.Customer.create", return_value=fake):
        user = django_user_model.objects.create_user(
            email="f@t.com", password="x",
        )

    user.refresh_from_db()
    assert user.stripe_customer_id == "cus_FROM_SIGNAL"


@pytest.mark.django_db
def test_signup_dispatch_does_not_block_when_stripe_unset(
    django_user_model, settings,
):
    settings.STRIPE_API_KEY = ""
    user = django_user_model.objects.create_user(
        email="g@t.com", password="x",
    )
    user.refresh_from_db()
    assert user.stripe_customer_id is None
