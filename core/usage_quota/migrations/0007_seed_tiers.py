"""Seed the canonical tier set (free / plus / pro) and deactivate the legacy
``enterprise`` plan.

Forward (idempotent):
- Upsert (by slug) the three tiers with the exact field values from task 9.
  Every field is overwritten — if ``0003_load_initial_data`` previously
  seeded different limits (e.g. ``pro.weekly_limit_usd=200``), this
  migration corrects them.
- Set ``enterprise.is_active=False`` if it exists. ``UserSubscription.plan``
  is ``on_delete=PROTECT`` so we never delete enterprise; we just hide it
  from the active-plan listings.

Reverse (dev/staging only — DO NOT roll back in production casually):
- Attempt to delete the three seeded tiers by slug. If any tier has active
  ``UserSubscription`` rows the ``PROTECT`` FK raises ``ProtectedError`` and
  we re-raise with a clear message. The forward-deactivation of
  ``enterprise`` is NOT re-activated — its limits never matched the new
  spec anyway.

[MEM: sqlite-test-infra-cascade] Pure ORM upserts via the historical
model. No ``RunSQL``, no PG-only operators, no pgvector — runs identically
on SQLite (test DB) and Postgres (staging/prod).
"""

from django.db import migrations
from django.db.models import ProtectedError

from usage_quota._tier_seed import _seed_tiers


def _unseed_tiers(apps, schema_editor):
    SubscriptionPlan = apps.get_model("usage_quota", "SubscriptionPlan")
    for slug in ("free", "plus", "pro"):
        try:
            SubscriptionPlan.objects.filter(name=slug).delete()
        except ProtectedError as exc:
            raise ProtectedError(
                f"Cannot reverse 0007: plan '{slug}' has active "
                f"UserSubscription rows. Reassign subscriptions first.",
                exc.protected_objects,
            )
    # Note: `enterprise.is_active=False` is intentionally NOT reverted.


class Migration(migrations.Migration):

    dependencies = [
        ("usage_quota", "0006_add_tier_limit_fields"),
    ]

    operations = [
        migrations.RunPython(_seed_tiers, _unseed_tiers),
    ]
