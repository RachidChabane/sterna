"""Asserts each tier's field values match the spec in task 9.

Does NOT use the migration runner — calls ``seed_tiers_for_tests`` directly
against the live app registry, which is the same code path the migration's
RunPython callable uses (both go through ``_tier_seed._seed_tiers``).

This file is the fastest, most deterministic check against the canonical
tier definitions; the migration round-trip lives in ``test_seed_migration``.
"""

from decimal import Decimal

from django.test import TestCase

from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.models import SubscriptionPlan


class TierDefinitionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Wipe whatever was seeded by 0003 / 0007 so we re-assert what the
        # seed function produces on a clean slate (no leftover ``enterprise``).
        SubscriptionPlan.objects.all().delete()
        seed_tiers_for_tests()

    def test_three_tiers_exist(self):
        names = set(SubscriptionPlan.objects.values_list("name", flat=True))
        self.assertEqual(names, {"free", "plus", "pro"})

    def test_free_tier_values(self):
        plan = SubscriptionPlan.objects.get(name="free")
        self.assertEqual(plan.weekly_limit_usd, Decimal("1.50"))
        self.assertEqual(plan.session_limit_usd, Decimal("0.75"))
        self.assertEqual(plan.voice_room_sessions_weekly_limit, 0)
        self.assertEqual(plan.voice_room_minutes_per_session_limit, 0)
        self.assertEqual(plan.code_session_weekly_limit, 0)
        self.assertEqual(plan.kb_storage_mb_limit, 50)
        self.assertEqual(plan.kb_docs_limit, 10)
        self.assertEqual(plan.image_gen_weekly_limit, 5)
        self.assertEqual(plan.video_gen_seconds_weekly_limit, 0)
        self.assertEqual(plan.mcp_invocations_weekly_limit, 0)
        self.assertTrue(plan.is_default)
        self.assertTrue(plan.is_active)
        self.assertFalse(plan.features["voice_rooms"])
        self.assertFalse(plan.features["code_sessions"])
        self.assertFalse(plan.features["mcp"])
        self.assertFalse(plan.features["video_gen"])
        self.assertFalse(plan.features["sparks_create"])
        self.assertFalse(plan.features["priority_coding_agent"])
        self.assertTrue(plan.features["byok"])
        self.assertTrue(plan.features["chat"])
        self.assertTrue(plan.features["sparks_view"])

    def test_plus_tier_values(self):
        plan = SubscriptionPlan.objects.get(name="plus")
        self.assertEqual(plan.weekly_limit_usd, Decimal("15.00"))
        self.assertEqual(plan.session_limit_usd, Decimal("5.00"))
        self.assertEqual(plan.voice_room_sessions_weekly_limit, 5)
        self.assertEqual(plan.voice_room_minutes_per_session_limit, 10)
        self.assertEqual(plan.code_session_weekly_limit, 20)
        self.assertEqual(plan.kb_storage_mb_limit, 1024)
        self.assertEqual(plan.kb_docs_limit, 100)
        self.assertEqual(plan.image_gen_weekly_limit, 50)
        self.assertEqual(plan.video_gen_seconds_weekly_limit, 30)
        self.assertIsNone(plan.mcp_invocations_weekly_limit)  # unlimited
        self.assertFalse(plan.is_default)
        self.assertTrue(plan.is_active)
        self.assertTrue(plan.features["voice_rooms"])
        self.assertTrue(plan.features["code_sessions"])
        self.assertTrue(plan.features["sparks_create"])
        self.assertTrue(plan.features["mcp"])
        self.assertTrue(plan.features["video_gen"])
        self.assertFalse(plan.features["priority_coding_agent"])

    def test_pro_tier_values(self):
        plan = SubscriptionPlan.objects.get(name="pro")
        self.assertEqual(plan.weekly_limit_usd, Decimal("80.00"))
        self.assertEqual(plan.session_limit_usd, Decimal("20.00"))
        self.assertEqual(plan.voice_room_sessions_weekly_limit, 30)
        self.assertEqual(plan.voice_room_minutes_per_session_limit, 30)
        self.assertEqual(plan.code_session_weekly_limit, 200)
        self.assertEqual(plan.kb_storage_mb_limit, 10240)
        self.assertIsNone(plan.kb_docs_limit)  # unlimited
        self.assertEqual(plan.image_gen_weekly_limit, 500)
        self.assertEqual(plan.video_gen_seconds_weekly_limit, 300)
        self.assertIsNone(plan.mcp_invocations_weekly_limit)
        self.assertFalse(plan.is_default)
        self.assertTrue(plan.is_active)
        self.assertTrue(plan.features["priority_coding_agent"])
        self.assertTrue(plan.features["sparks_create"])

    def test_stripe_placeholders_null(self):
        for slug in ("free", "plus", "pro"):
            plan = SubscriptionPlan.objects.get(name=slug)
            self.assertIsNone(plan.stripe_price_id_monthly)
            self.assertIsNone(plan.stripe_price_id_yearly)

    def test_per_feature_limits_dict_shape(self):
        plan = SubscriptionPlan.objects.get(name="pro")
        limits = plan.get_per_feature_limits()
        self.assertEqual(
            set(limits.keys()),
            {
                "voice_room",
                "code_session",
                "image_gen",
                "video_gen",
                "mcp",
                "kb_storage_mb",
                "kb_docs",
            },
        )
        self.assertEqual(limits["voice_room"], 30)
        self.assertEqual(limits["code_session"], 200)
        self.assertEqual(limits["image_gen"], 500)
        self.assertEqual(limits["video_gen"], 300)
        self.assertIsNone(limits["mcp"])
        self.assertEqual(limits["kb_storage_mb"], 10240)
        self.assertIsNone(limits["kb_docs"])
