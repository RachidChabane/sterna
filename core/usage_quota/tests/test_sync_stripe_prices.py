"""Tests for the sync_stripe_prices management command.

We patch the four Stripe entry points the command uses:
  - stripe.Product.list
  - stripe.Product.create
  - stripe.Price.list
  - stripe.Price.create

No real HTTP calls.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.models import SubscriptionPlan


def _list_returning(items):
    """Build a MagicMock that mimics stripe.ListObject.auto_paging_iter()."""
    m = MagicMock()
    m.auto_paging_iter.return_value = iter(items)
    return m


@pytest.fixture
def seeded(db):
    seed_tiers_for_tests()


@pytest.mark.django_db
def test_errors_when_stripe_not_configured(seeded, settings):
    settings.STRIPE_API_KEY = ""
    with pytest.raises(CommandError, match="STRIPE_API_KEY is not set"):
        call_command("sync_stripe_prices")


@pytest.mark.django_db
def test_creates_products_and_prices_first_run(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"

    with patch("stripe.Product.list", return_value=_list_returning([])), \
         patch(
             "stripe.Product.create",
             side_effect=[
                 MagicMock(id="prod_PLUS", metadata={"slug": "plus"}),
                 MagicMock(id="prod_PRO", metadata={"slug": "pro"}),
             ],
         ) as mock_pc, \
         patch("stripe.Price.list", return_value=_list_returning([])), \
         patch(
             "stripe.Price.create",
             side_effect=[
                 MagicMock(id="price_PLUS_M"),
                 MagicMock(id="price_PLUS_Y"),
                 MagicMock(id="price_PRO_M"),
                 MagicMock(id="price_PRO_Y"),
             ],
         ) as mock_pricec:
        out = StringIO()
        call_command("sync_stripe_prices", stdout=out)

    assert mock_pc.call_count == 2
    assert mock_pricec.call_count == 4
    # Task 14: every Product.create call passes the SaaS tax code.
    for call in mock_pc.call_args_list:
        assert call.kwargs.get("tax_code") == "txcd_10103000"
    # Every Price.create call is explicitly tax-exclusive — Prices with
    # 'unspecified' tax_behavior break automatic_tax Checkout.
    for call in mock_pricec.call_args_list:
        assert call.kwargs.get("tax_behavior") == "exclusive"

    plus = SubscriptionPlan.objects.get(name="plus")
    pro = SubscriptionPlan.objects.get(name="pro")
    assert plus.stripe_price_id_monthly == "price_PLUS_M"
    assert plus.stripe_price_id_yearly == "price_PLUS_Y"
    assert pro.stripe_price_id_monthly == "price_PRO_M"
    assert pro.stripe_price_id_yearly == "price_PRO_Y"


@pytest.mark.django_db
def test_idempotent_second_run_skips_creation(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    # Existing Products already carry the SaaS tax code → no modify
    # call on re-run.
    existing_plus = MagicMock(
        id="prod_PLUS", metadata={"slug": "plus"},
        tax_code="txcd_10103000",
    )
    existing_pro = MagicMock(
        id="prod_PRO", metadata={"slug": "pro"},
        tax_code="txcd_10103000",
    )
    plus_monthly = MagicMock(
        id="price_PLUS_M", unit_amount=2000, currency="usd",
        recurring=MagicMock(interval="month"), tax_behavior="exclusive",
    )
    plus_yearly = MagicMock(
        id="price_PLUS_Y", unit_amount=20000, currency="usd",
        recurring=MagicMock(interval="year"), tax_behavior="exclusive",
    )
    pro_monthly = MagicMock(
        id="price_PRO_M", unit_amount=10000, currency="usd",
        recurring=MagicMock(interval="month"), tax_behavior="exclusive",
    )
    pro_yearly = MagicMock(
        id="price_PRO_Y", unit_amount=100000, currency="usd",
        recurring=MagicMock(interval="year"), tax_behavior="exclusive",
    )

    with patch(
        "stripe.Product.list",
        return_value=_list_returning([existing_plus, existing_pro]),
    ), \
         patch("stripe.Product.create") as mock_pc, \
         patch("stripe.Product.modify") as mock_pm, \
         patch(
             "stripe.Price.list",
             side_effect=[
                 _list_returning([plus_monthly, plus_yearly]),
                 _list_returning([plus_monthly, plus_yearly]),
                 _list_returning([pro_monthly, pro_yearly]),
                 _list_returning([pro_monthly, pro_yearly]),
             ],
         ), \
         patch("stripe.Price.create") as mock_pricec:
        call_command("sync_stripe_prices")

    mock_pc.assert_not_called()
    mock_pm.assert_not_called()
    mock_pricec.assert_not_called()

    plus = SubscriptionPlan.objects.get(name="plus")
    assert plus.stripe_price_id_monthly == "price_PLUS_M"
    assert plus.stripe_price_id_yearly == "price_PLUS_Y"


@pytest.mark.django_db
def test_backfills_tax_code_on_existing_product_without_one(seeded, settings):
    """Pre-task-14 Products were created without tax_code. Re-run
    must backfill via Product.modify.
    """
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    plus_product = MagicMock(
        id="prod_PLUS", metadata={"slug": "plus"}, tax_code=None,
    )
    pro_product = MagicMock(
        id="prod_PRO", metadata={"slug": "pro"}, tax_code=None,
    )
    plus_monthly = MagicMock(
        id="price_PLUS_M", unit_amount=2000, currency="usd",
        recurring=MagicMock(interval="month"), tax_behavior="exclusive",
    )
    plus_yearly = MagicMock(
        id="price_PLUS_Y", unit_amount=20000, currency="usd",
        recurring=MagicMock(interval="year"), tax_behavior="exclusive",
    )
    pro_monthly = MagicMock(
        id="price_PRO_M", unit_amount=10000, currency="usd",
        recurring=MagicMock(interval="month"), tax_behavior="exclusive",
    )
    pro_yearly = MagicMock(
        id="price_PRO_Y", unit_amount=100000, currency="usd",
        recurring=MagicMock(interval="year"), tax_behavior="exclusive",
    )

    with patch(
        "stripe.Product.list",
        return_value=_list_returning([plus_product, pro_product]),
    ), \
         patch("stripe.Product.create") as mock_pc, \
         patch(
             "stripe.Product.modify",
             side_effect=lambda pid, **kw: MagicMock(
                 id=pid, tax_code=kw.get("tax_code"),
             ),
         ) as mock_pm, \
         patch(
             "stripe.Price.list",
             side_effect=[
                 _list_returning([plus_monthly, plus_yearly]),
                 _list_returning([plus_monthly, plus_yearly]),
                 _list_returning([pro_monthly, pro_yearly]),
                 _list_returning([pro_monthly, pro_yearly]),
             ],
         ), \
         patch("stripe.Price.create"):
        call_command("sync_stripe_prices")

    mock_pc.assert_not_called()
    assert mock_pm.call_count == 2
    for call in mock_pm.call_args_list:
        assert call.kwargs.get("tax_code") == "txcd_10103000"


@pytest.mark.django_db
def test_price_with_unspecified_tax_behavior_is_not_reused(seeded, settings):
    """A pre-existing Price matching amount+interval but WITHOUT a
    definite tax_behavior must not satisfy the idempotency match —
    a fresh tax-exclusive Price is created and replaces it in the DB
    ('unspecified' Prices break automatic_tax Checkout and Stripe
    forbids flipping tax_behavior once definite)."""
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    existing_plus = MagicMock(
        id="prod_PLUS", metadata={"slug": "plus"},
        tax_code="txcd_10103000",
    )
    existing_pro = MagicMock(
        id="prod_PRO", metadata={"slug": "pro"},
        tax_code="txcd_10103000",
    )
    stale_plus_monthly = MagicMock(
        id="price_PLUS_M_OLD", unit_amount=2000, currency="usd",
        recurring=MagicMock(interval="month"), tax_behavior="unspecified",
    )

    with patch(
        "stripe.Product.list",
        return_value=_list_returning([existing_plus, existing_pro]),
    ), \
         patch("stripe.Product.create") as mock_pc, \
         patch(
             "stripe.Price.list",
             side_effect=[
                 _list_returning([stale_plus_monthly]),
                 _list_returning([]),
                 _list_returning([]),
                 _list_returning([]),
             ],
         ), \
         patch(
             "stripe.Price.create",
             side_effect=[
                 MagicMock(id="price_PLUS_M_NEW"),
                 MagicMock(id="price_PLUS_Y_NEW"),
                 MagicMock(id="price_PRO_M_NEW"),
                 MagicMock(id="price_PRO_Y_NEW"),
             ],
         ) as mock_pricec:
        call_command("sync_stripe_prices")

    mock_pc.assert_not_called()
    assert mock_pricec.call_count == 4
    for call in mock_pricec.call_args_list:
        assert call.kwargs.get("tax_behavior") == "exclusive"
    plus = SubscriptionPlan.objects.get(name="plus")
    assert plus.stripe_price_id_monthly == "price_PLUS_M_NEW"


@pytest.mark.django_db
def test_dry_run_does_not_call_create_or_write_db(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    with patch("stripe.Product.list", return_value=_list_returning([])), \
         patch("stripe.Product.create") as mock_pc, \
         patch("stripe.Price.list", return_value=_list_returning([])), \
         patch("stripe.Price.create") as mock_pricec:
        call_command("sync_stripe_prices", "--dry-run")

    mock_pc.assert_not_called()
    mock_pricec.assert_not_called()

    plus = SubscriptionPlan.objects.get(name="plus")
    assert plus.stripe_price_id_monthly is None
    assert plus.stripe_price_id_yearly is None


@pytest.mark.django_db
def test_skips_missing_plan_without_error(seeded, settings):
    """If 'plus' is missing from DB, log a warning, continue with 'pro'."""
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    SubscriptionPlan.objects.filter(name="plus").delete()

    with patch("stripe.Product.list", return_value=_list_returning([])), \
         patch(
             "stripe.Product.create",
             return_value=MagicMock(id="prod_PRO", metadata={"slug": "pro"}),
         ) as mock_pc, \
         patch("stripe.Price.list", return_value=_list_returning([])), \
         patch(
             "stripe.Price.create",
             side_effect=[
                 MagicMock(id="price_PRO_M"),
                 MagicMock(id="price_PRO_Y"),
             ],
         ):
        call_command("sync_stripe_prices")

    assert mock_pc.call_count == 1
