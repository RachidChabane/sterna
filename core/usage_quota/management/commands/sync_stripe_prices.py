"""Manual one-time price sync — Stripe Products + Prices ↔ SubscriptionPlan.

Run order:
  1. stripe.Product.list / create (idempotent by metadata.slug)
  2. stripe.Price.list / create (idempotent by recurring.interval +
     unit_amount under the matched product)
  3. SubscriptionPlan.objects.filter(name=…).update(
         stripe_price_id_monthly=…, stripe_price_id_yearly=…)

Idempotency: re-running on a synced DB is a no-op. Re-running after a
Stripe Product was archived will detect the missing Product and
recreate it; the resulting Price IDs will replace the DB values.

Run AFTER:
  - settings.STRIPE_API_KEY is set in the environment (sk_test_… in
    dev/staging, sk_live_… in prod).
  - SubscriptionPlan rows for plus + pro exist (seeded by
    usage_quota/migrations/0007_seed_tiers.py).
"""

from __future__ import annotations

import logging

import stripe
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from usage_quota._tier_seed import TIER_DEFINITIONS
from usage_quota.models import SubscriptionPlan
from usage_quota.services.stripe_customer import _stripe_configured

logger = logging.getLogger(__name__)

# Free plan has no $/mo; skip. We hard-code the slug list rather than
# filter on weekly_limit_usd because that field is the usage budget,
# not the subscription price.
BILLABLE_TIER_SLUGS = ("plus", "pro")

# Stripe tax code for SaaS — Cloud Software (subscription-based cloud
# software). See https://stripe.com/docs/tax/tax-codes
SAAS_TAX_CODE = "txcd_10103000"

# Displayed prices are tax-EXCLUSIVE (tax added on top at Checkout).
# Without an explicit tax_behavior, Stripe creates Prices as
# 'unspecified' and automatic_tax Checkout sessions fail.
PRICE_TAX_BEHAVIOR = "exclusive"


class Command(BaseCommand):
    help = (
        "Mirror Sterna SubscriptionPlan rows to Stripe Products + "
        "Prices. Idempotent. Run once per environment after the "
        "STRIPE_API_KEY secret is set (see infra-migration/README.md "
        "for how secrets are populated)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print actions; do not call Stripe or write to DB.",
        )

    def handle(self, *args, dry_run: bool = False, **opts):
        if not _stripe_configured():
            raise CommandError(
                "STRIPE_API_KEY is not set. Configure it before running "
                "sync_stripe_prices."
            )

        by_slug = {t["name"]: t for t in TIER_DEFINITIONS}

        results = []
        for slug in BILLABLE_TIER_SLUGS:
            tier = by_slug[slug]
            try:
                plan = SubscriptionPlan.objects.get(name=slug)
            except SubscriptionPlan.DoesNotExist:
                self.stderr.write(self.style.WARNING(
                    f"Plan '{slug}' not in DB — skipping. "
                    "Run migrations + setup_usage_quota first."
                ))
                continue

            monthly_id, yearly_id = self._sync_one(plan, tier, dry_run=dry_run)
            results.append((slug, monthly_id, yearly_id))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("sync_stripe_prices complete"))
        for slug, m, y in results:
            self.stdout.write(f"  {slug}: monthly={m or '—'}, yearly={y or '—'}")

    def _sync_one(self, plan, tier, *, dry_run: bool):
        product = self._find_or_create_product(plan, dry_run=dry_run)
        if product is None:
            return (None, None)

        monthly_amount = tier["monthly_unit_amount_cents"]
        yearly_amount = tier["yearly_unit_amount_cents"]

        monthly_price = self._find_or_create_price(
            product, monthly_amount, "month", dry_run=dry_run,
        )
        yearly_price = self._find_or_create_price(
            product, yearly_amount, "year", dry_run=dry_run,
        )

        if not dry_run:
            with transaction.atomic():
                plan.stripe_price_id_monthly = (
                    monthly_price.id if monthly_price else None
                )
                plan.stripe_price_id_yearly = (
                    yearly_price.id if yearly_price else None
                )
                plan.save(update_fields=[
                    "stripe_price_id_monthly",
                    "stripe_price_id_yearly",
                    "updated_at",
                ])

        return (
            monthly_price.id if monthly_price else None,
            yearly_price.id if yearly_price else None,
        )

    def _find_or_create_product(self, plan, *, dry_run: bool):
        """Find a Product by metadata.slug or create it.

        On reuse of a pre-existing Product, backfill ``tax_code`` via
        ``Product.modify`` if missing or wrong. Stripe Prices inherit
        their Product's tax_code automatically; no per-Price update.
        """
        existing = None
        products = stripe.Product.list(active=True, limit=100)
        for p in products.auto_paging_iter():
            if p.metadata.get("slug") == plan.name:
                existing = p
                break

        if existing:
            current_tax_code = getattr(existing, "tax_code", None) or None
            if current_tax_code != SAAS_TAX_CODE:
                if dry_run:
                    self.stdout.write(
                        f"  [{plan.name}] DRY-RUN would modify product "
                        f"tax_code: {current_tax_code!r} -> {SAAS_TAX_CODE!r}"
                    )
                else:
                    existing = stripe.Product.modify(
                        existing.id, tax_code=SAAS_TAX_CODE,
                    )
                    self.stdout.write(self.style.SUCCESS(
                        f"  [{plan.name}] updated tax_code to {SAAS_TAX_CODE}"
                    ))
            else:
                self.stdout.write(
                    f"  [{plan.name}] product exists: {existing.id} "
                    f"(tax_code={current_tax_code})"
                )
            return existing

        if dry_run:
            self.stdout.write(f"  [{plan.name}] DRY-RUN would create product")
            return None

        product = stripe.Product.create(
            name=f"Sterna {plan.display_name}",
            description=plan.description or "",
            metadata={"slug": plan.name},
            tax_code=SAAS_TAX_CODE,
        )
        self.stdout.write(self.style.SUCCESS(
            f"  [{plan.name}] created product: {product.id}"
        ))
        return product

    def _find_or_create_price(self, product, amount_cents, interval, *, dry_run: bool):
        """Find a recurring Price for this Product with the given amount + interval.

        ``tax_behavior`` is part of the match predicate: a pre-existing
        Price with 'unspecified' tax_behavior is NOT reused (Stripe
        forbids flipping tax_behavior once set to a definite value, and
        'unspecified' Prices break automatic_tax Checkout) — a fresh
        tax-exclusive Price is created instead and replaces it in the
        DB. The old Price stays in Stripe, unused.
        """
        prices = stripe.Price.list(product=product.id, active=True, limit=100)
        for p in prices.auto_paging_iter():
            if (
                p.recurring
                and p.recurring.interval == interval
                and p.unit_amount == amount_cents
                and p.currency == "usd"
                and getattr(p, "tax_behavior", None) == PRICE_TAX_BEHAVIOR
            ):
                self.stdout.write(f"    {interval} price exists: {p.id}")
                return p

        if dry_run:
            self.stdout.write(
                f"    DRY-RUN would create {interval} price @ {amount_cents}¢"
            )
            return None

        price = stripe.Price.create(
            product=product.id,
            unit_amount=amount_cents,
            currency="usd",
            recurring={"interval": interval},
            tax_behavior=PRICE_TAX_BEHAVIOR,
        )
        self.stdout.write(self.style.SUCCESS(
            f"    created {interval} price: {price.id}"
        ))
        return price
