"""Tests for ``usage_quota.services.quota_service.QuotaService``.

Covers the atomic ``check_and_deduct`` and non-atomic ``deduct_usage``
enforcement paths, feature-access checks, the settings-UI quota summary
(``get_user_quota_info``), the async wrappers (including the
per-feature-name gating in ``acheck_quota``), and the deprecated
rolling/fixed-window helpers. These methods are pure domain logic over
the real (sqlite) test database — no external I/O to mock. The one
seam that reaches into other apps' models, ``feature_registry.get``, is
patched with a locally defined ``FeatureSpec`` so these tests do not
depend on ``voice_rooms``/``code_sessions`` fixtures.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone

from authentication.models import User
from usage_quota.exceptions import (
    BillingMisconfiguration,
    FeatureNotAvailableException,
    QuotaExceededException,
    SubscriptionNotFoundException,
)
from usage_quota.feature_registry import FeatureSpec
from usage_quota.models import FeatureType, ServiceType, SubscriptionPlan, UsageLog
from usage_quota.services.quota_service import QuotaService, get_quota_service


pytestmark = pytest.mark.django_db


def _make_user(seeded, email):
    return User.objects.create_user(email=email, password="x", is_verified=True)


@pytest.fixture
def service():
    return QuotaService()


# ---------------------------------------------------------------------------
# check_and_deduct (atomic)
# ---------------------------------------------------------------------------


class TestCheckAndDeduct:
    def test_creates_default_subscription_and_deducts(self, seeded, service):
        user = _make_user(seeded, "cad-new-sub@t.com")

        result = service.check_and_deduct(
            user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.50"),
        )

        assert result.success
        assert result.new_weekly_used_usd == Decimal("0.50")
        assert result.new_remaining_weekly_usd == Decimal("1.00")  # free tier: 1.50 - 0.50

    def test_over_weekly_limit_raises_with_weekly_reason(self, seeded, service):
        user = _make_user(seeded, "cad-weekly-deny@t.com")

        with pytest.raises(QuotaExceededException) as exc_info:
            service.check_and_deduct(
                user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("2.00"),
            )

        assert exc_info.value.limit_type == "weekly"
        assert exc_info.value.message == "Weekly usage limit exceeded"

    def test_over_session_limit_but_under_weekly_raises_with_session_reason(self, seeded, service):
        user = _make_user(seeded, "cad-session-deny@t.com")
        # Free tier: weekly=1.50, session=0.75. $1.00 clears the weekly
        # check but blows the tighter session budget.
        with pytest.raises(QuotaExceededException) as exc_info:
            service.check_and_deduct(
                user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("1.00"),
            )

        assert exc_info.value.limit_type == "session"
        assert "Session rate limit exceeded" in exc_info.value.message

    def test_accepted_operation_creates_a_usage_log(self, seeded, service):
        user = _make_user(seeded, "cad-log@t.com")

        result = service.check_and_deduct(
            user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.10"),
            feature=FeatureType.CHAT, model_id="m", request_id="req-1",
        )

        log = UsageLog.objects.get(id=result.usage_log_id)
        assert log.user_id == user.id
        assert log.cost_usd == Decimal("0.10")
        assert log.request_id == "req-1"

    def test_missing_default_plan_yields_subscription_not_found(self, seeded, service):
        user = _make_user(seeded, "cad-no-default-plan@t.com")

        with patch.object(SubscriptionPlan, "get_default_plan", return_value=None):
            with pytest.raises(SubscriptionNotFoundException):
                service.check_and_deduct(
                    user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.10"),
                )


# ---------------------------------------------------------------------------
# check_quota (non-atomic pre-flight check)
# ---------------------------------------------------------------------------


class TestCheckQuota:
    def test_within_budget_is_allowed(self, seeded, service):
        user = _make_user(seeded, "cq-allowed@t.com")

        result = service.check_quota(user, ServiceType.OPENROUTER, Decimal("0.10"))

        assert result.allowed is True

    def test_over_weekly_remaining_is_denied_with_weekly_reason(self, seeded, service):
        user = _make_user(seeded, "cq-weekly-deny@t.com")

        result = service.check_quota(user, ServiceType.OPENROUTER, Decimal("2.00"))

        assert result.allowed is False
        assert result.reason == "weekly"

    def test_over_session_remaining_is_denied_with_session_reason(self, seeded, service):
        user = _make_user(seeded, "cq-session-deny@t.com")

        # Free tier: weekly=1.50, session=0.75 — $1.00 clears weekly but
        # not the tighter session budget.
        result = service.check_quota(user, ServiceType.OPENROUTER, Decimal("1.00"))

        assert result.allowed is False
        assert result.reason == "session"


# ---------------------------------------------------------------------------
# deduct_usage (non-atomic; does not enforce limits)
# ---------------------------------------------------------------------------


class TestDeductUsage:
    def test_creates_default_subscription_and_records_usage(self, seeded, service):
        user = _make_user(seeded, "deduct-new-sub@t.com")

        result = service.deduct_usage(
            user=user, service=ServiceType.BRAVE_SEARCH, cost_usd=Decimal("0.05"),
        )

        assert result.success
        assert result.new_weekly_used_usd == Decimal("0.05")
        assert UsageLog.objects.filter(user=user).count() == 1

    def test_does_not_enforce_limits(self, seeded, service):
        """Unlike check_and_deduct, an over-budget deduction still succeeds —
        this method is a ledger write, not a gate."""
        user = _make_user(seeded, "deduct-over-limit@t.com")

        result = service.deduct_usage(
            user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("100.00"),
        )

        assert result.success
        assert result.new_remaining_weekly_usd == Decimal("0")  # clamped, not negative

    def test_missing_default_plan_yields_subscription_not_found(self, seeded, service):
        user = _make_user(seeded, "deduct-no-default-plan@t.com")

        with patch.object(SubscriptionPlan, "get_default_plan", return_value=None):
            with pytest.raises(SubscriptionNotFoundException):
                service.deduct_usage(
                    user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.10"),
                )


# ---------------------------------------------------------------------------
# check_feature_access
# ---------------------------------------------------------------------------


class TestCheckFeatureAccess:
    def test_allowed_feature_returns_true(self, seeded, service):
        user = _make_user(seeded, "feature-allowed@t.com")
        assert service.check_feature_access(user, "chat") is True

    def test_denied_feature_raises_with_plan_display_name(self, seeded, service):
        user = _make_user(seeded, "feature-denied@t.com")

        with pytest.raises(FeatureNotAvailableException) as exc_info:
            service.check_feature_access(user, "voice_rooms")  # free tier: False

        assert exc_info.value.feature == "voice_rooms"
        assert exc_info.value.plan_name == "Free"


# ---------------------------------------------------------------------------
# get_user_quota_info
# ---------------------------------------------------------------------------


class TestGetUserQuotaInfo:
    def test_fresh_subscription_has_empty_inactive_windows(self, seeded, service):
        user = _make_user(seeded, "quota-info-fresh@t.com")

        info = service.get_user_quota_info(user)

        assert info.plan_name == "free"
        assert info.weekly_used_usd == Decimal("0")
        assert info.window_start == ""
        assert info.window_end == ""
        assert info.by_service == {}
        assert info.by_feature == {}

    def test_active_window_reports_usage_breakdown(self, seeded, service):
        user = _make_user(seeded, "quota-info-active@t.com")
        service.deduct_usage(
            user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.30"),
            feature=FeatureType.CHAT,
        )

        info = service.get_user_quota_info(user)

        assert info.weekly_used_usd == Decimal("0.30")
        assert info.window_start != ""
        assert Decimal(info.by_service[str(ServiceType.OPENROUTER)]["used_usd"]) == Decimal("0.30")
        assert info.by_service[str(ServiceType.OPENROUTER)]["requests"] == 1
        assert Decimal(info.by_feature[str(FeatureType.CHAT)]["used_usd"]) == Decimal("0.30")

    def test_by_service_breakdown_includes_optional_usage_dimensions(self, seeded, service):
        user = _make_user(seeded, "quota-info-dimensions@t.com")
        service.deduct_usage(
            user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.10"),
            feature=FeatureType.CHAT, prompt_tokens=100, completion_tokens=50,
            total_tokens=150, character_count=42, audio_seconds=3.5,
        )

        info = service.get_user_quota_info(user)

        row = info.by_service[str(ServiceType.OPENROUTER)]
        assert row["tokens"] == 150
        assert row["characters"] == 42
        assert row["audio_seconds"] == 3.5


# ---------------------------------------------------------------------------
# get_weekly_usage / get_session_usage — expired-window short circuit
# ---------------------------------------------------------------------------


class TestUsageWindowExpiry:
    def test_get_weekly_usage_returns_zero_once_the_window_has_expired(self, seeded, service):
        from datetime import timedelta

        user = _make_user(seeded, "weekly-expired@t.com")
        long_ago = timezone.now() - timedelta(days=30)

        assert service.get_weekly_usage(user, long_ago) == Decimal("0")

    def test_get_session_usage_returns_zero_once_the_window_has_expired(self, seeded, service):
        from datetime import timedelta

        user = _make_user(seeded, "session-expired@t.com")
        long_ago = timezone.now() - timedelta(hours=30)

        assert service.get_session_usage(user, long_ago) == Decimal("0")


# ---------------------------------------------------------------------------
# Subscription caching / default-plan edge case
# ---------------------------------------------------------------------------


class TestSubscriptionCaching:
    def test_second_lookup_is_served_from_cache(self, seeded, service):
        user = _make_user(seeded, "cache-hit@t.com")
        first = service._get_or_create_subscription(user)
        second = service._get_subscription_cached(user)

        assert second is not None
        assert second.pk == first.pk

    def test_repeated_lookup_of_absent_subscription_is_served_from_negative_cache(self, seeded, service):
        user = _make_user(seeded, "cache-miss-twice@t.com")

        first = service._get_subscription_cached(user)
        second = service._get_subscription_cached(user)

        assert first is None
        assert second is None

    def test_missing_default_plan_yields_no_subscription(self, seeded, service):
        user = _make_user(seeded, "no-default-plan@t.com")

        with patch.object(SubscriptionPlan, "get_default_plan", return_value=None):
            with pytest.raises(SubscriptionNotFoundException):
                service.check_quota(user, ServiceType.OPENROUTER, Decimal("0.01"))


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------


class TestAsyncWrappers:
    def test_acheck_quota_without_feature_name_delegates_to_check_quota(self, seeded, service):
        user = _make_user(seeded, "acheck-basic@t.com")

        result = async_to_sync(service.acheck_quota)(
            user, ServiceType.OPENROUTER, Decimal("0.01"),
        )

        assert result.allowed is True

    def test_adeduct_usage_delegates_to_deduct_usage(self, seeded, service):
        user = _make_user(seeded, "adeduct@t.com")

        result = async_to_sync(service.adeduct_usage)(
            user, ServiceType.OPENROUTER, Decimal("0.02"),
        )

        assert result.success
        assert UsageLog.objects.filter(user=user).count() == 1

    def test_acheck_and_deduct_delegates_to_check_and_deduct(self, seeded, service):
        user = _make_user(seeded, "acad@t.com")

        result = async_to_sync(service.acheck_and_deduct)(
            user, ServiceType.OPENROUTER, Decimal("0.02"),
        )

        assert result.success

    def test_acheck_and_deduct_still_enforces_limits(self, seeded, service):
        user = _make_user(seeded, "acad-deny@t.com")

        with pytest.raises(QuotaExceededException):
            async_to_sync(service.acheck_and_deduct)(
                user, ServiceType.OPENROUTER, Decimal("5.00"),
            )


class TestAcheckQuotaFeatureGating:
    """``acheck_quota(..., feature_name=...)`` runs a cascading guard —
    unknown feature, plan flag, per-feature count limit — before falling
    through to the ordinary $-budget check."""

    def test_unknown_feature_name_raises_billing_misconfiguration(self, seeded, service):
        user = _make_user(seeded, "gate-unknown@t.com")

        with pytest.raises(BillingMisconfiguration):
            async_to_sync(service.acheck_quota)(
                user, ServiceType.OPENROUTER, Decimal("0.01"),
                feature_name="not_a_real_feature",
            )

    def test_flag_gate_denies_when_plan_lacks_the_flag(self, seeded, service):
        user = _make_user(seeded, "gate-flag@t.com")  # free tier: voice_rooms flag is False
        spec = FeatureSpec(
            feature_name="fake_flagged",
            flag_key="voice_rooms",
            limit_field=None,
            count_provider=None,
            unit="count",
        )

        with patch("usage_quota.feature_registry.get", return_value=spec):
            with pytest.raises(FeatureNotAvailableException):
                async_to_sync(service.acheck_quota)(
                    user, ServiceType.OPENROUTER, Decimal("0.01"),
                    feature_name="fake_flagged",
                )

    def test_zero_limit_field_hard_disables_regardless_of_flag(self, seeded, service):
        user = _make_user(seeded, "gate-zero-limit@t.com")  # free tier: code_session_weekly_limit=0
        spec = FeatureSpec(
            feature_name="fake_limited",
            flag_key=None,
            limit_field="code_session_weekly_limit",
            count_provider=None,
            unit="count",
        )

        with patch("usage_quota.feature_registry.get", return_value=spec):
            with pytest.raises(FeatureNotAvailableException):
                async_to_sync(service.acheck_quota)(
                    user, ServiceType.OPENROUTER, Decimal("0.01"),
                    feature_name="fake_limited",
                )

    def test_count_provider_over_limit_raises_quota_exceeded_with_counts(self, seeded, service):
        user = _make_user(seeded, "gate-over-count@t.com")
        # Plus tier allows a positive code-session limit; stamp it via a
        # custom subscription so the count gate (not the zero-limit gate)
        # is what fires.
        from usage_quota.models import UserSubscription

        plus_plan = SubscriptionPlan.objects.get(name="plus")
        UserSubscription.objects.create(
            user=user, plan=plus_plan, is_active=True, weekly_window_start=timezone.now(),
        )

        spec = FeatureSpec(
            feature_name="fake_counted",
            flag_key=None,
            limit_field="code_session_weekly_limit",
            count_provider=lambda user, plan: 999,
            unit="count",
            quota_window="weekly",
        )

        with patch("usage_quota.feature_registry.get", return_value=spec):
            with pytest.raises(QuotaExceededException) as exc_info:
                async_to_sync(service.acheck_quota)(
                    user, ServiceType.OPENROUTER, Decimal("0.01"),
                    feature_name="fake_counted",
                )

        assert exc_info.value.limit_type == "weekly"
        assert exc_info.value.resets_in_seconds is not None

    def test_storage_quota_window_reports_no_reset_time(self, seeded, service):
        user = _make_user(seeded, "gate-storage@t.com")
        from usage_quota.models import UserSubscription

        plus_plan = SubscriptionPlan.objects.get(name="plus")
        UserSubscription.objects.create(user=user, plan=plus_plan, is_active=True)

        spec = FeatureSpec(
            feature_name="fake_storage",
            flag_key=None,
            limit_field="kb_storage_mb_limit",
            count_provider=lambda user, plan: 99999,
            unit="mb",
            quota_window="storage",
        )

        with patch("usage_quota.feature_registry.get", return_value=spec):
            with pytest.raises(QuotaExceededException) as exc_info:
                async_to_sync(service.acheck_quota)(
                    user, ServiceType.OPENROUTER, Decimal("0.01"),
                    feature_name="fake_storage",
                )

        assert exc_info.value.resets_in_seconds is None

    def test_gate_passing_falls_through_to_budget_check(self, seeded, service):
        user = _make_user(seeded, "gate-pass@t.com")
        spec = FeatureSpec(
            feature_name="fake_ok",
            flag_key="chat",  # free tier: True
            limit_field=None,
            count_provider=None,
            unit="count",
        )

        with patch("usage_quota.feature_registry.get", return_value=spec):
            result = async_to_sync(service.acheck_quota)(
                user, ServiceType.OPENROUTER, Decimal("0.01"),
                feature_name="fake_ok",
            )

        assert result.allowed is True


# ---------------------------------------------------------------------------
# Deprecated rolling / fixed-window helpers
# ---------------------------------------------------------------------------


class TestLegacyWindowHelpers:
    def test_get_rolling_usage_sums_recent_logs(self, seeded, service):
        user = _make_user(seeded, "rolling@t.com")
        service.deduct_usage(user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.40"))
        service.deduct_usage(user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.10"))

        assert service.get_rolling_usage(user, days=7) == Decimal("0.50")

    def test_get_fixed_window_usage_delegates_to_weekly_for_7_day_duration(self, seeded, service):
        from datetime import timedelta

        user = _make_user(seeded, "fixed-weekly@t.com")
        service.deduct_usage(user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.20"))
        subscription = service._get_or_create_subscription(user)

        direct = service.get_weekly_usage(user, subscription.weekly_window_start)
        via_helper = service.get_fixed_window_usage(
            user, subscription.weekly_window_start, timedelta(days=7),
        )

        assert via_helper == direct == Decimal("0.20")

    def test_get_fixed_window_usage_delegates_to_session_for_3_hour_duration(self, seeded, service):
        from datetime import timedelta

        user = _make_user(seeded, "fixed-session@t.com")
        service.deduct_usage(user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.20"))
        subscription = service._get_or_create_subscription(user)

        direct = service.get_session_usage(user, subscription.session_window_start)
        via_helper = service.get_fixed_window_usage(
            user, subscription.session_window_start, timedelta(hours=3),
        )

        assert via_helper == direct == Decimal("0.20")

    def test_get_fixed_window_usage_generic_fallback_with_no_window_start(self, seeded, service):
        from datetime import timedelta

        user = _make_user(seeded, "fixed-generic-none@t.com")
        assert service.get_fixed_window_usage(user, None, timedelta(minutes=42)) == Decimal("0")

    def test_get_fixed_window_usage_generic_fallback_expired_window(self, seeded, service):
        from datetime import timedelta

        user = _make_user(seeded, "fixed-generic-expired@t.com")
        long_ago = timezone.now() - timedelta(days=30)

        assert service.get_fixed_window_usage(user, long_ago, timedelta(minutes=5)) == Decimal("0")

    def test_get_fixed_window_usage_generic_fallback_active_window_sums_usage(self, seeded, service):
        from datetime import timedelta

        user = _make_user(seeded, "fixed-generic-active@t.com")
        service.deduct_usage(user=user, service=ServiceType.OPENROUTER, cost_usd=Decimal("0.15"))
        window_start = timezone.now() - timedelta(minutes=1)

        total = service.get_fixed_window_usage(user, window_start, timedelta(minutes=42))

        assert total == Decimal("0.15")


# ---------------------------------------------------------------------------
# get_quota_service singleton
# ---------------------------------------------------------------------------


def test_get_quota_service_returns_the_same_instance_every_call():
    assert get_quota_service() is get_quota_service()
