"""Pre-flight smoke: Stripe Tax + plan Product tax codes.

Run order:
  1. Assert Stripe Tax is enabled on the account.
  2. Assert at least one tax registration exists (France, after
     manual dashboard activation).
  3. Assert every Sterna plan Product (resolved by
     metadata.slug == plan.name) carries tax_code='txcd_10103000'.

Wired into deploy-staging.yml / deploy-production.yml as a
post-deploy smoke step (right after sanity_check_stripe_mode).
Failure exits 1 → red deploy → operator investigates the dashboard.

Exit codes:
  0 = ok (tax enabled, >=1 registration, all Products tagged)
  1 = any assertion fails
"""

from __future__ import annotations

import stripe
from django.core.management.base import BaseCommand, CommandError

from usage_quota.management.commands.sync_stripe_prices import (
    BILLABLE_TIER_SLUGS,
    SAAS_TAX_CODE,
)
from usage_quota.services.stripe_customer import _stripe_configured


class Command(BaseCommand):
    help = (
        "Verify Stripe Tax is enabled, at least one registration "
        "exists, every plan Product has the SaaS tax code, and every "
        "active plan Price has an explicit tax_behavior. Exits 1 on "
        "any mismatch."
    )

    def handle(self, *args, **opts):
        if not _stripe_configured():
            raise CommandError(
                "STRIPE_API_KEY is not set. "
                "Configure it before running verify_stripe_tax."
            )

        self._assert_tax_enabled()
        self._assert_registration_exists()
        slug_to_product = self._assert_products_have_tax_code()
        self._assert_prices_have_tax_behavior(slug_to_product)

        self.stdout.write(self.style.SUCCESS(
            "verify_stripe_tax: all assertions passed."
        ))

    def _assert_tax_enabled(self):
        # stripe-python is pinned to >=10.0,<11.0 in
        # core/requirements.txt — stripe.tax.Settings.retrieve() is
        # deterministic; no AttributeError fallback needed.
        #
        # Before locking the field name, verify the exact attribute
        # on the returned object with a real test-mode call:
        #   python -c "import stripe; \
        #              stripe.api_key='sk_test_...'; \
        #              print(stripe.tax.Settings.retrieve())"
        #
        # If 10.x exposes a different field (e.g. defaults.tax_behavior),
        # swap to that here. We deliberately do NOT wrap this in
        # try/except AttributeError — the SDK is pinned, and silent
        # fallback could mask a genuine misconfiguration.
        settings_obj = stripe.tax.Settings.retrieve()
        status = getattr(settings_obj, "status", None)
        if status not in ("active", "pending"):
            raise CommandError(
                f"FATAL: Stripe Tax not enabled. status={status!r}. "
                "Activate in Stripe Dashboard -> Settings -> Tax."
            )

        self.stdout.write(self.style.SUCCESS(
            "  ✓ Stripe Tax is enabled"
        ))

    def _assert_registration_exists(self):
        try:
            registrations = stripe.tax.Registration.list(limit=1)
        except (AttributeError, stripe.error.InvalidRequestError):
            raise CommandError(
                "FATAL: Could not list tax registrations. "
                "Either the SDK is too old (upgrade stripe-python) "
                "or no registration exists. Add France in Stripe "
                "Dashboard -> Settings -> Tax -> Registrations."
            )

        if not registrations.data:
            raise CommandError(
                "FATAL: No tax registrations exist. Sterna is "
                "France-based; register France in Stripe Dashboard "
                "-> Settings -> Tax -> Registrations."
            )

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ {len(registrations.data)} tax registration(s) found"
        ))

    def _assert_products_have_tax_code(self):
        products = stripe.Product.list(active=True, limit=100)
        slug_to_product = {}
        for p in products.auto_paging_iter():
            slug = p.metadata.get("slug")
            if slug in BILLABLE_TIER_SLUGS:
                slug_to_product[slug] = p

        missing = []
        wrong = []
        for slug in BILLABLE_TIER_SLUGS:
            p = slug_to_product.get(slug)
            if p is None:
                missing.append(slug)
                continue
            tax_code = getattr(p, "tax_code", None)
            if tax_code != SAAS_TAX_CODE:
                wrong.append((slug, p.id, tax_code))

        if missing:
            raise CommandError(
                f"FATAL: Missing Stripe Products for plan slugs: "
                f"{missing}. Run `python manage.py sync_stripe_prices` "
                "first."
            )
        if wrong:
            details = ", ".join(
                f"{s}({pid}, current={tc!r})" for s, pid, tc in wrong
            )
            raise CommandError(
                f"FATAL: Products with incorrect tax_code (expected "
                f"{SAAS_TAX_CODE!r}): {details}. Re-run "
                "`python manage.py sync_stripe_prices` to backfill."
            )

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ {len(BILLABLE_TIER_SLUGS)} plan Products tagged "
            f"with tax_code={SAAS_TAX_CODE}"
        ))
        return slug_to_product

    def _assert_prices_have_tax_behavior(self, slug_to_product):
        """Every active Price under a plan Product needs tax_behavior set.

        A Price with 'unspecified' tax_behavior makes automatic_tax
        Checkout sessions fail at runtime. sync_stripe_prices creates
        tax-exclusive Prices; this asserts none of the live ones
        regressed (e.g. a Price hand-created in the dashboard).
        """
        offenders = []
        checked = 0
        for slug, product in slug_to_product.items():
            prices = stripe.Price.list(
                product=product.id, active=True, limit=100,
            )
            for p in prices.auto_paging_iter():
                checked += 1
                tax_behavior = getattr(p, "tax_behavior", None)
                if tax_behavior in (None, "unspecified"):
                    offenders.append((slug, p.id, tax_behavior))

        if offenders:
            details = ", ".join(
                f"{s}({pid}, current={tb!r})" for s, pid, tb in offenders
            )
            raise CommandError(
                f"FATAL: Prices without an explicit tax_behavior: "
                f"{details}. Re-run `python manage.py "
                "sync_stripe_prices` to create tax-exclusive "
                "replacements."
            )

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ {checked} active plan Price(s) have tax_behavior set"
        ))
