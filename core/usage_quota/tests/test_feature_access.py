"""Asserts BillingService.check_feature_access for the full tier × feature matrix.

Each cell is the contract for "what does this plan grant this user?" — if
this matrix ever drifts from the plan in [[skills-removal-task-2]]'s sister
tasks (8, 10, 11), this is the canary that catches the regression.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.billing.service import get_billing_service
from usage_quota.models import SubscriptionPlan, UserSubscription


User = get_user_model()


FEATURE_MATRIX = {
    # feature_name: (free, plus, pro)
    "voice_rooms":           (False, True,  True),
    "code_sessions":         (False, True,  True),
    "knowledge_base":        (True,  True,  True),
    "image_gen":             (True,  True,  True),
    "video_gen":             (False, True,  True),
    "sparks_view":           (True,  True,  True),
    "sparks_create":         (False, True,  True),
    "mcp":                   (False, True,  True),
    "byok":                  (True,  True,  True),
    "priority_coding_agent": (False, False, True),
}


class FeatureAccessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        SubscriptionPlan.objects.all().delete()
        seed_tiers_for_tests()
        cls.user_free = User.objects.create_user(email="free@test.com", password="x")
        cls.user_plus = User.objects.create_user(email="plus@test.com", password="x")
        cls.user_pro = User.objects.create_user(email="pro@test.com", password="x")
        for user, slug in (
            (cls.user_free, "free"),
            (cls.user_plus, "plus"),
            (cls.user_pro, "pro"),
        ):
            UserSubscription.objects.create(
                user=user,
                plan=SubscriptionPlan.objects.get(name=slug),
            )

    def test_matrix(self):
        billing = get_billing_service()
        for feature, (expected_free, expected_plus, expected_pro) in FEATURE_MATRIX.items():
            with self.subTest(feature=feature):
                self.assertEqual(
                    billing.check_feature_access(self.user_free, feature),
                    expected_free,
                    msg=f"free × {feature}",
                )
                self.assertEqual(
                    billing.check_feature_access(self.user_plus, feature),
                    expected_plus,
                    msg=f"plus × {feature}",
                )
                self.assertEqual(
                    billing.check_feature_access(self.user_pro, feature),
                    expected_pro,
                    msg=f"pro × {feature}",
                )

    def test_unknown_feature_returns_false(self):
        billing = get_billing_service()
        self.assertFalse(
            billing.check_feature_access(self.user_pro, "feature_that_does_not_exist")
        )

    def test_get_user_plan_returns_correct_plan(self):
        billing = get_billing_service()
        self.assertEqual(billing.get_user_plan(self.user_free).name, "free")
        self.assertEqual(billing.get_user_plan(self.user_plus).name, "plus")
        self.assertEqual(billing.get_user_plan(self.user_pro).name, "pro")

    def test_get_user_plan_falls_back_to_default_for_new_user(self):
        billing = get_billing_service()
        new_user = User.objects.create_user(email="newbie@test.com", password="x")
        # No UserSubscription created — should get the default plan via
        # QuotaService._create_default_subscription.
        plan = billing.get_user_plan(new_user)
        self.assertEqual(plan.name, "free")
