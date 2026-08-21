"""Tests for the verify_stripe_tax management command.

We patch the three Stripe entry points the command uses:
  - stripe.tax.Settings.retrieve
  - stripe.tax.Registration.list
  - stripe.Product.list

No real HTTP calls.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from usage_quota._tier_seed import seed_tiers_for_tests


def _list_returning(items):
    m = MagicMock()
    m.auto_paging_iter.return_value = iter(items)
    m.data = list(items)
    return m


@pytest.fixture
def seeded(db):
    seed_tiers_for_tests()


@pytest.mark.django_db
def test_errors_when_stripe_not_configured(seeded, settings):
    settings.STRIPE_API_KEY = ""
    with pytest.raises(CommandError, match="STRIPE_API_KEY is not set"):
        call_command("verify_stripe_tax")


def _price(price_id, tax_behavior="exclusive"):
    return MagicMock(id=price_id, tax_behavior=tax_behavior)


@pytest.mark.django_db
def test_happy_path_passes(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    plus_product = MagicMock(
        id="prod_PLUS", metadata={"slug": "plus"},
        tax_code="txcd_10103000",
    )
    pro_product = MagicMock(
        id="prod_PRO", metadata={"slug": "pro"},
        tax_code="txcd_10103000",
    )
    with patch("stripe.tax.Settings.retrieve",
               return_value=MagicMock(status="active")), \
         patch("stripe.tax.Registration.list",
               return_value=_list_returning([MagicMock(id="taxreg_FR")])), \
         patch("stripe.Product.list",
               return_value=_list_returning([plus_product, pro_product])), \
         patch("stripe.Price.list",
               side_effect=[
                   _list_returning([_price("price_PLUS_M"),
                                    _price("price_PLUS_Y")]),
                   _list_returning([_price("price_PRO_M"),
                                    _price("price_PRO_Y")]),
               ]):
        out = StringIO()
        call_command("verify_stripe_tax", stdout=out)

    assert "all assertions passed" in out.getvalue()
    assert "tax_behavior set" in out.getvalue()


@pytest.mark.django_db
def test_errors_when_price_missing_tax_behavior(seeded, settings):
    """A plan Price with 'unspecified' (or absent) tax_behavior fails
    the smoke — automatic_tax Checkout would 500 at runtime."""
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    plus_product = MagicMock(
        id="prod_PLUS", metadata={"slug": "plus"},
        tax_code="txcd_10103000",
    )
    pro_product = MagicMock(
        id="prod_PRO", metadata={"slug": "pro"},
        tax_code="txcd_10103000",
    )
    with patch("stripe.tax.Settings.retrieve",
               return_value=MagicMock(status="active")), \
         patch("stripe.tax.Registration.list",
               return_value=_list_returning([MagicMock(id="taxreg_FR")])), \
         patch("stripe.Product.list",
               return_value=_list_returning([plus_product, pro_product])), \
         patch("stripe.Price.list",
               side_effect=[
                   _list_returning([
                       _price("price_PLUS_M", tax_behavior="unspecified"),
                   ]),
                   _list_returning([_price("price_PRO_M")]),
               ]):
        with pytest.raises(CommandError,
                           match="without an explicit tax_behavior"):
            call_command("verify_stripe_tax")


@pytest.mark.django_db
def test_errors_when_tax_settings_inactive(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    with patch("stripe.tax.Settings.retrieve",
               return_value=MagicMock(status="not_started")):
        with pytest.raises(CommandError,
                           match="Stripe Tax not enabled"):
            call_command("verify_stripe_tax")


@pytest.mark.django_db
def test_errors_when_no_registrations(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    with patch("stripe.tax.Settings.retrieve",
               return_value=MagicMock(status="active")), \
         patch("stripe.tax.Registration.list",
               return_value=_list_returning([])):
        with pytest.raises(CommandError,
                           match="No tax registrations exist"):
            call_command("verify_stripe_tax")


@pytest.mark.django_db
def test_errors_when_product_missing_tax_code(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    plus_product = MagicMock(
        id="prod_PLUS", metadata={"slug": "plus"}, tax_code=None,
    )
    pro_product = MagicMock(
        id="prod_PRO", metadata={"slug": "pro"},
        tax_code="txcd_10103000",
    )
    with patch("stripe.tax.Settings.retrieve",
               return_value=MagicMock(status="active")), \
         patch("stripe.tax.Registration.list",
               return_value=_list_returning([MagicMock(id="taxreg_FR")])), \
         patch("stripe.Product.list",
               return_value=_list_returning([plus_product, pro_product])):
        with pytest.raises(CommandError,
                           match="incorrect tax_code"):
            call_command("verify_stripe_tax")


@pytest.mark.django_db
def test_errors_when_product_missing(seeded, settings):
    settings.STRIPE_API_KEY = "sk_test_FAKE"
    pro_product = MagicMock(
        id="prod_PRO", metadata={"slug": "pro"},
        tax_code="txcd_10103000",
    )
    with patch("stripe.tax.Settings.retrieve",
               return_value=MagicMock(status="active")), \
         patch("stripe.tax.Registration.list",
               return_value=_list_returning([MagicMock(id="taxreg_FR")])), \
         patch("stripe.Product.list",
               return_value=_list_returning([pro_product])):
        with pytest.raises(CommandError, match="Missing Stripe Products"):
            call_command("verify_stripe_tax")
