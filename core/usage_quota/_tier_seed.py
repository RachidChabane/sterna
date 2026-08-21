"""Shared tier-seed data + function used by migration 0007 and tests.

The migration imports ``_seed_tiers`` (the ``RunPython`` forward callable).
Tests import ``seed_tiers_for_tests`` to populate the DB without invoking
``MigrationExecutor`` — same logic, no migration-runner fragility.

``TIER_DEFINITIONS`` is the single source of truth for the free/plus/pro
tier set: name, display, descriptions, USD budgets, per-feature count
limits, Stripe placeholders, and feature-access flags.
"""

from decimal import Decimal


TIER_DEFINITIONS = [
    {
        "name": "free",
        "display_name": "Free",
        "description": "Free tier — basic access with limited usage.",
        "weekly_limit_usd": Decimal("1.50"),
        "session_limit_usd": Decimal("0.75"),
        "is_default": True,
        "is_active": True,
        # Per-feature $ budgets — left null (advisory; task 10 wires)
        "chat_weekly_limit_usd": None,
        "voice_room_weekly_limit_usd": None,
        "code_session_weekly_limit_usd": None,
        # Per-feature count limits (this task)
        "voice_room_sessions_weekly_limit": 0,
        "voice_room_minutes_per_session_limit": 0,
        "code_session_weekly_limit": 0,
        "kb_storage_mb_limit": 50,
        "kb_docs_limit": 10,
        "image_gen_weekly_limit": 5,
        "video_gen_seconds_weekly_limit": 0,
        "mcp_invocations_weekly_limit": 0,
        "stripe_price_id_monthly": None,
        "stripe_price_id_yearly": None,
        "features": {
            "chat": True, "search": True,
            "voice_rooms": False, "code_sessions": False,
            "knowledge_base": True, "image_gen": True, "video_gen": False,
            "sparks_view": True, "sparks_create": False,
            "mcp": False, "byok": True, "priority_coding_agent": False,
        },
    },
    {
        "name": "plus",
        "display_name": "Plus",
        "description": "Plus tier — $20/mo, expanded weekly budgets and feature access.",
        "weekly_limit_usd": Decimal("15.00"),
        "session_limit_usd": Decimal("5.00"),
        "is_default": False,
        "is_active": True,
        "chat_weekly_limit_usd": None,
        "voice_room_weekly_limit_usd": None,
        "code_session_weekly_limit_usd": None,
        "voice_room_sessions_weekly_limit": 5,
        "voice_room_minutes_per_session_limit": 10,
        "code_session_weekly_limit": 20,
        "kb_storage_mb_limit": 1024,
        "kb_docs_limit": 100,
        "image_gen_weekly_limit": 50,
        "video_gen_seconds_weekly_limit": 30,
        "mcp_invocations_weekly_limit": None,
        "stripe_price_id_monthly": None,
        "stripe_price_id_yearly": None,
        # task 11: consumed by sync_stripe_prices (not stored on the model)
        "monthly_unit_amount_cents": 2000,
        "yearly_unit_amount_cents": 20000,
        "features": {
            "chat": True, "search": True,
            "voice_rooms": True, "code_sessions": True,
            "knowledge_base": True, "image_gen": True, "video_gen": True,
            "sparks_view": True, "sparks_create": True,
            "mcp": True, "byok": True, "priority_coding_agent": False,
        },
    },
    {
        "name": "pro",
        "display_name": "Pro",
        "description": "Pro tier — $100/mo, the highest weekly budgets and limits.",
        "weekly_limit_usd": Decimal("80.00"),
        "session_limit_usd": Decimal("20.00"),
        "is_default": False,
        "is_active": True,
        "chat_weekly_limit_usd": None,
        "voice_room_weekly_limit_usd": None,
        "code_session_weekly_limit_usd": None,
        "voice_room_sessions_weekly_limit": 30,
        "voice_room_minutes_per_session_limit": 30,
        "code_session_weekly_limit": 200,
        "kb_storage_mb_limit": 10240,
        "kb_docs_limit": None,
        "image_gen_weekly_limit": 500,
        "video_gen_seconds_weekly_limit": 300,
        "mcp_invocations_weekly_limit": None,
        "stripe_price_id_monthly": None,
        "stripe_price_id_yearly": None,
        # task 11: consumed by sync_stripe_prices (not stored on the model)
        "monthly_unit_amount_cents": 10000,
        "yearly_unit_amount_cents": 100000,
        "features": {
            "chat": True, "search": True,
            "voice_rooms": True, "code_sessions": True,
            "knowledge_base": True, "image_gen": True, "video_gen": True,
            "sparks_view": True, "sparks_create": True,
            "mcp": True, "byok": True, "priority_coding_agent": True,
        },
    },
]


# Keys in ``TIER_DEFINITIONS`` that are not model fields — consumed only
# by ``sync_stripe_prices``. Stripped before passing to ``Plan.objects``.
_NON_MODEL_KEYS = frozenset({
    "monthly_unit_amount_cents",
    "yearly_unit_amount_cents",
})


def _seed_tiers(apps, schema_editor):
    """Upsert the canonical tier set (free/plus/pro) and deactivate enterprise.

    Idempotent: every field is overwritten on each run, so stale values
    written by 0003 (e.g. pro.weekly_limit_usd=200) get corrected.

    Used both as a ``RunPython`` forward callable (migration 0007) and via
    ``seed_tiers_for_tests`` (test helper).
    """
    SubscriptionPlan = apps.get_model("usage_quota", "SubscriptionPlan")

    # Race-safe: ensure only `free` keeps is_default=True after seeding.
    SubscriptionPlan.objects.filter(is_default=True).exclude(
        name__in=["free"]
    ).update(is_default=False)

    for tier in TIER_DEFINITIONS:
        slug = tier["name"]
        tier_fields = {k: v for k, v in tier.items() if k not in _NON_MODEL_KEYS}
        existing = SubscriptionPlan.objects.filter(name=slug).first()
        if existing is None:
            SubscriptionPlan.objects.create(**tier_fields)
        else:
            for key, value in tier_fields.items():
                if key == "name":
                    continue
                setattr(existing, key, value)
            existing.save()

    # Deactivate `enterprise` if present (don't delete — PROTECT FK on
    # UserSubscription.plan would block deletion if anyone is subscribed).
    SubscriptionPlan.objects.filter(name="enterprise").update(
        is_active=False,
        is_default=False,
    )


def seed_tiers_for_tests():
    """Test helper: seed tiers using the live app registry (not historical).

    Called from test ``setUpTestData`` / ``setUp`` to populate the canonical
    tier set without invoking ``MigrationExecutor``.
    """
    from django.apps import apps as live_apps
    _seed_tiers(live_apps, schema_editor=None)
