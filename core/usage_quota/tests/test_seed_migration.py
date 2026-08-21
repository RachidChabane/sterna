"""Validates the seed function + the 0007 migration round-trip.

Split into two classes because the assertions answer different questions:

- ``TierSeedIdempotencyTest`` exercises ``_tier_seed.seed_tiers_for_tests()``
  directly. Same code path as the migration's RunPython callable, but no
  migration runner — fast and deterministic.
- ``SeedMigrationRoundtripTest`` uses ``MigrationExecutor`` to verify the
  forward + reverse operations work end-to-end. Each test's ``setUp``
  steps the migration state back to 0006 and forward to 0007 explicitly,
  because ``TransactionTestCase`` does not flush ``django_migrations``
  between tests.
"""

from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.models import SubscriptionPlan, UserSubscription


class TierSeedIdempotencyTest(TestCase):
    """Properties of the seed function itself (no migration runner)."""

    def setUp(self):
        # 0007 has already run when the test DB was created, so the three
        # tiers exist. Wipe them to re-assert what seed produces on a
        # clean slate.
        UserSubscription.objects.all().delete()
        SubscriptionPlan.objects.all().delete()

    def test_seed_creates_three_tiers(self):
        seed_tiers_for_tests()
        self.assertEqual(
            SubscriptionPlan.objects.filter(name__in=["free", "plus", "pro"]).count(),
            3,
        )

    def test_seed_is_idempotent(self):
        seed_tiers_for_tests()
        seed_tiers_for_tests()
        seed_tiers_for_tests()
        self.assertEqual(
            SubscriptionPlan.objects.filter(name__in=["free", "plus", "pro"]).count(),
            3,
        )

    def test_seed_overwrites_stale_pro_values(self):
        # Simulate the pre-migration state where 0003 wrote pro with
        # 200.00 / 50.00 — assert the seed corrects them to 80 / 20.
        SubscriptionPlan.objects.create(
            name="pro",
            display_name="Old Pro",
            description="stale",
            weekly_limit_usd=Decimal("200.00"),
            session_limit_usd=Decimal("50.00"),
            features={"chat": True},
            is_default=False,
            is_active=True,
        )
        seed_tiers_for_tests()
        plan = SubscriptionPlan.objects.get(name="pro")
        self.assertEqual(plan.weekly_limit_usd, Decimal("80.00"))
        self.assertEqual(plan.session_limit_usd, Decimal("20.00"))
        # Per-feature limits also populated:
        self.assertEqual(plan.code_session_weekly_limit, 200)
        self.assertEqual(plan.image_gen_weekly_limit, 500)
        self.assertEqual(plan.voice_room_sessions_weekly_limit, 30)

    def test_seed_deactivates_enterprise_if_present(self):
        SubscriptionPlan.objects.create(
            name="enterprise",
            display_name="Legacy Enterprise",
            description="legacy",
            weekly_limit_usd=Decimal("100.00"),
            session_limit_usd=Decimal("20.00"),
            features={"chat": True},
            is_default=False,
            is_active=True,
        )
        seed_tiers_for_tests()
        ent = SubscriptionPlan.objects.get(name="enterprise")
        self.assertFalse(ent.is_active)
        self.assertFalse(ent.is_default)

    def test_seed_clears_is_default_off_non_free(self):
        # If a stale row is_default=True on a non-free plan, the seed
        # should fix that — only `free` ends up with is_default=True.
        SubscriptionPlan.objects.create(
            name="pro",
            display_name="Old Pro",
            description="stale",
            weekly_limit_usd=Decimal("200.00"),
            session_limit_usd=Decimal("50.00"),
            features={"chat": True},
            is_default=True,  # wrong!
            is_active=True,
        )
        seed_tiers_for_tests()
        defaults = list(
            SubscriptionPlan.objects.filter(is_default=True).values_list("name", flat=True)
        )
        self.assertEqual(defaults, ["free"])


class SeedMigrationRoundtripTest(TransactionTestCase):
    """Forward + reverse via MigrationExecutor.

    ``TransactionTestCase`` flushes user-table rows between tests but does
    NOT flush ``django_migrations``. So every test's ``setUp`` explicitly
    steps back to 0006 and forward to 0007 to ensure ``RunPython`` actually
    fires — otherwise the seed only runs once across the entire class
    (the first test) and later tests would silently assert against an
    unchanged DB.
    """

    serialized_rollback = True

    def _migrate_to(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([("usage_quota", target)])

    def setUp(self):
        # Step back then forward so _seed_tiers re-runs every test.
        self._migrate_to("0006_add_tier_limit_fields")

    def tearDown(self):
        # Leave the test DB in the HEAD migration state for the next class.
        self._migrate_to("0007_seed_tiers")

    def test_forward_creates_three_tiers_and_deactivates_enterprise(self):
        # Refresh `enterprise` plan (it survives the 0006 unseed because
        # ``_unseed_tiers`` only deletes free/plus/pro by design — see
        # migration 0007 docstring). update_or_create avoids a UNIQUE
        # constraint when the row already exists.
        SubscriptionPlan.objects.update_or_create(
            name="enterprise",
            defaults={
                "display_name": "Legacy Enterprise",
                "description": "legacy",
                "weekly_limit_usd": Decimal("100.00"),
                "session_limit_usd": Decimal("20.00"),
                "features": {"chat": True},
                "is_default": False,
                "is_active": True,
            },
        )
        self._migrate_to("0007_seed_tiers")
        for slug in ("free", "plus", "pro"):
            self.assertTrue(
                SubscriptionPlan.objects.filter(name=slug).exists(),
                msg=f"{slug} tier should exist after 0007",
            )
        ent = SubscriptionPlan.objects.get(name="enterprise")
        self.assertFalse(ent.is_active)
        self.assertFalse(ent.is_default)
        # Only `free` keeps is_default=True.
        self.assertEqual(
            list(
                SubscriptionPlan.objects.filter(is_default=True)
                .values_list("name", flat=True)
            ),
            ["free"],
        )

    def test_reverse_deletes_seeded_tiers_when_no_subscription_blocks(self):
        self._migrate_to("0007_seed_tiers")
        # No UserSubscription rows reference the seeded plans, so reverse
        # should delete them cleanly.
        self._migrate_to("0006_add_tier_limit_fields")
        self.assertFalse(
            SubscriptionPlan.objects.filter(name__in=["free", "plus", "pro"]).exists()
        )

    def test_forward_overwrites_stale_pro_values(self):
        # Inject pre-migration state: pro with old 200/50 limits.
        SubscriptionPlan.objects.create(
            name="pro",
            display_name="Old Pro",
            description="stale",
            weekly_limit_usd=Decimal("200.00"),
            session_limit_usd=Decimal("50.00"),
            features={"chat": True},
            is_default=False,
            is_active=True,
        )
        self._migrate_to("0007_seed_tiers")
        plan = SubscriptionPlan.objects.get(name="pro")
        self.assertEqual(plan.weekly_limit_usd, Decimal("80.00"))
        self.assertEqual(plan.session_limit_usd, Decimal("20.00"))
        self.assertEqual(plan.code_session_weekly_limit, 200)
