"""
Data migration to ensure initial subscription plans and pricing are loaded.

Originally used ``call_command('loaddata', ...)`` which routes through the
LIVE app registry's model. Once later migrations add new columns, the live
model's ``_meta.local_concrete_fields`` includes them, and the INSERT
compiler references columns that don't exist yet at this migration's
schema state — fresh DBs fail at this step before later migrations even run.

Rewritten to use the historical model from ``apps.get_model(...)``, whose
concrete-field list is frozen at this migration's state, so the INSERT only
references columns that exist in 0003's schema. The fixture JSON files are
kept on disk for historical reference but are no longer loaded — see the
note at the top of each fixture file.

The forward callable is idempotent (skips if rows already exist) and
preserves the original PKs from the fixture files so any FK references
survive a re-load.
"""

import json
from decimal import Decimal
from pathlib import Path

from django.db import migrations


# Frozen at 0003's schema — DO NOT ADD NEW FIELDS HERE.
# Per-feature count limits + Stripe placeholders land in 0006 + 0007.
INITIAL_PLANS = [
    {
        "pk": "00000000-0000-0000-0000-000000000001",
        "name": "free",
        "display_name": "Free Plan",
        "description": "Basic access with limited usage",
        "weekly_limit_usd": Decimal("50.00"),
        "session_limit_usd": Decimal("20.00"),
        "features": {
            "chat": True,
            "voice_rooms": True,
            "code_sessions": False,
            "search": True,
        },
        "chat_weekly_limit_usd": None,
        "voice_room_weekly_limit_usd": None,
        "code_session_weekly_limit_usd": None,
        "is_active": True,
        "is_default": True,
    },
    {
        "pk": "00000000-0000-0000-0000-000000000002",
        "name": "pro",
        "display_name": "Pro Plan",
        "description": "Full access with higher limits",
        "weekly_limit_usd": Decimal("200.00"),
        "session_limit_usd": Decimal("50.00"),
        "features": {
            "chat": True,
            "voice_rooms": True,
            "code_sessions": True,
            "search": True,
        },
        "chat_weekly_limit_usd": None,
        "voice_room_weekly_limit_usd": None,
        "code_session_weekly_limit_usd": None,
        "is_active": True,
        "is_default": False,
    },
    {
        "pk": "00000000-0000-0000-0000-000000000003",
        "name": "enterprise",
        "display_name": "Enterprise Plan",
        "description": "Unlimited access for teams",
        "weekly_limit_usd": Decimal("100.00"),
        "session_limit_usd": Decimal("20.00"),
        "features": {
            "chat": True,
            "voice_rooms": True,
            "code_sessions": True,
            "search": True,
            "priority_support": True,
        },
        "chat_weekly_limit_usd": None,
        "voice_room_weekly_limit_usd": None,
        "code_session_weekly_limit_usd": None,
        "is_active": True,
        "is_default": False,
    },
]


_DECIMAL_PRICE_FIELDS = (
    "price_per_1m_input_tokens",
    "price_per_1m_output_tokens",
    "price_per_1k_chars",
    "price_per_minute",
    "price_per_request",
)


def _load_service_pricing(ServicePricing):
    """Inline ServicePricing rows from fixtures/service_pricing.json.

    Decimal fields are constructed as Decimal(str(...)) to avoid
    float-precision drift on Postgres. Same shape as the fixture: each
    entry has {"pk", "fields": {...}} with fields matching the
    ServicePricing schema at 0003.
    """
    fixture_path = (
        Path(__file__).resolve().parent.parent / "fixtures" / "service_pricing.json"
    )
    with fixture_path.open() as fp:
        rows = json.load(fp)
    for row in rows:
        fields = dict(row["fields"])
        for key in _DECIMAL_PRICE_FIELDS:
            if key in fields and fields[key] is not None:
                fields[key] = Decimal(str(fields[key]))
        ServicePricing.objects.update_or_create(
            pk=row["pk"],
            defaults=fields,
        )


def load_initial_data(apps, schema_editor):
    """Load initial subscription plans + pricing if they don't exist.

    Uses the historical model via ``apps.get_model`` so the INSERT
    references only columns that exist at this migration's schema state.
    """
    SubscriptionPlan = apps.get_model("usage_quota", "SubscriptionPlan")
    ServicePricing = apps.get_model("usage_quota", "ServicePricing")

    if not SubscriptionPlan.objects.exists():
        for plan in INITIAL_PLANS:
            data = {k: v for k, v in plan.items() if k != "pk"}
            SubscriptionPlan.objects.update_or_create(
                pk=plan["pk"],
                defaults=data,
            )

    if not ServicePricing.objects.exists():
        _load_service_pricing(ServicePricing)


def reverse_migration(apps, schema_editor):
    """No-op reverse - don't delete data on rollback."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0002_add_fixed_window_fields'),
    ]

    operations = [
        migrations.RunPython(load_initial_data, reverse_migration),
    ]
