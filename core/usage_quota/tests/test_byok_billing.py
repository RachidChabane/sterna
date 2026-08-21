"""Tests for BYOK billing bypass + platform-exclusion guard (task 8)."""

import pytest
from decimal import Decimal
from django.utils import timezone

from authentication.models import User
from usage_quota.billing.service import get_billing_service
from usage_quota.billing.operations import BillableOperation
from usage_quota.constants import (
    OPENROUTER_BACKED_SERVICES,
    PLATFORM_ONLY_SERVICES,
    BILLING_ORIGIN_BYOK,
    BILLING_ORIGIN_PLATFORM,
)
from usage_quota.exceptions import BillingMisconfiguration
from usage_quota.models import (
    ServiceType,
    FeatureType,
    UsageLog,
    SubscriptionPlan,
    UserSubscription,
)


@pytest.fixture
def billing(db):
    """Fresh BillingService instance (avoids singleton state bleed between tests)."""
    from usage_quota.billing import service as svc
    svc._billing_service = None
    return get_billing_service()


@pytest.fixture
def free_plan(db):
    return SubscriptionPlan.objects.get_or_create(
        name='task8_test_free',
        defaults=dict(
            display_name='Task-8 Test Free',
            weekly_limit_usd=Decimal('5'),
            session_limit_usd=Decimal('1'),
            is_active=True,
            is_default=False,
        ),
    )[0]


@pytest.fixture
def user_with_byok(db, free_plan):
    u = User.objects.create_user(email='byok@test.com', password='x')
    u.openrouter_api_key = 'sk-or-v1-test-byok'
    u.openrouter_key_provisioned_at = None
    u.save()
    UserSubscription.objects.create(user=u, plan=free_plan, is_active=True)
    return u


@pytest.fixture
def user_with_provisioned(db, free_plan):
    """Provisioned key user — looks identical except provisioned_at IS NOT NULL."""
    u = User.objects.create_user(email='prov@test.com', password='x')
    u.openrouter_api_key = 'sk-or-v1-test-provisioned'
    u.openrouter_key_provisioned_at = timezone.now()
    u.openrouter_key_hash = 'someplatformhash'
    u.save()
    UserSubscription.objects.create(user=u, plan=free_plan, is_active=True)
    return u


@pytest.mark.django_db
def test_byok_chat_records_zero_cost_and_does_not_decrement(billing, user_with_byok):
    op = BillableOperation(
        service=ServiceType.OPENROUTER,
        feature=FeatureType.CHAT,
        model_id='openai/gpt-4o',
        prompt_tokens=1000,
        completion_tokens=500,
        cost_usd=Decimal('0.05'),
    )
    billing.record_usage(user_with_byok, op, billing_origin=BILLING_ORIGIN_BYOK)

    log = UsageLog.objects.get(user=user_with_byok)
    assert log.cost_usd == Decimal('0')
    assert log.billing_origin == 'byok'
    # Quota window not started — no platform spending occurred.
    sub = UserSubscription.objects.get(user=user_with_byok)
    assert sub.weekly_window_start is None


@pytest.mark.django_db
def test_platform_chat_records_real_cost_and_decrements(billing, user_with_byok):
    op = BillableOperation(
        service=ServiceType.OPENROUTER,
        feature=FeatureType.CHAT,
        model_id='openai/gpt-4o',
        cost_usd=Decimal('0.05'),
    )
    billing.record_usage(user_with_byok, op, billing_origin=BILLING_ORIGIN_PLATFORM)

    log = UsageLog.objects.get(user=user_with_byok)
    assert log.cost_usd == Decimal('0.05')
    assert log.billing_origin == 'platform'
    sub = UserSubscription.objects.get(user=user_with_byok)
    assert sub.weekly_window_start is not None


@pytest.mark.django_db
def test_video_with_byok_origin_raises(billing, user_with_byok):
    """Hard exclusion: video gen never honors BYOK."""
    op = BillableOperation(
        service=ServiceType.VIDEO_GENERATION,
        feature=FeatureType.CHAT,
        cost_usd=Decimal('1.50'),
    )
    with pytest.raises(BillingMisconfiguration) as exc:
        billing.record_usage(user_with_byok, op, billing_origin=BILLING_ORIGIN_BYOK)
    assert 'not OpenRouter-backed' in str(exc.value.message)


@pytest.mark.django_db
@pytest.mark.parametrize('service', [
    ServiceType.ELEVENLABS_TTS,
    ServiceType.OPENAI_TTS,
    ServiceType.DEEPGRAM_STT,
    ServiceType.BRAVE_SEARCH,
    ServiceType.GOOGLE_MAPS,
    ServiceType.VIDEO_GENERATION,
])
def test_platform_only_services_reject_byok(billing, user_with_byok, service):
    op = BillableOperation(service=service, cost_usd=Decimal('0.10'))
    with pytest.raises(BillingMisconfiguration):
        billing.record_usage(user_with_byok, op, billing_origin=BILLING_ORIGIN_BYOK)


@pytest.mark.django_db
def test_invalid_billing_origin_raises(billing, user_with_byok):
    op = BillableOperation(service=ServiceType.OPENROUTER, cost_usd=Decimal('0.01'))
    with pytest.raises(BillingMisconfiguration):
        billing.record_usage(user_with_byok, op, billing_origin='paid_by_aliens')


@pytest.mark.django_db
def test_resolver_origin_byok(user_with_byok):
    from llm.services.api_key_resolver import resolve_with_origin
    key, origin = resolve_with_origin(user=user_with_byok)
    assert key == 'sk-or-v1-test-byok'
    assert origin == 'byok'


@pytest.mark.django_db
def test_resolver_origin_provisioned_is_platform(user_with_provisioned):
    from llm.services.api_key_resolver import resolve_with_origin
    key, origin = resolve_with_origin(user=user_with_provisioned)
    assert key == 'sk-or-v1-test-provisioned'
    assert origin == 'platform'


@pytest.mark.django_db
def test_resolver_origin_no_user_falls_back_platform(settings):
    settings.OPENROUTER_API_KEY = 'sk-or-fallback'
    from llm.services.api_key_resolver import resolve_with_origin
    # Reset cached resolver so the new OPENROUTER_API_KEY is picked up.
    import llm.services.api_key_resolver as mod
    mod._resolver = None
    key, origin = resolve_with_origin(user=None)
    assert origin == 'platform'
    assert key == 'sk-or-fallback'


def test_constants_disjoint():
    overlap = OPENROUTER_BACKED_SERVICES & PLATFORM_ONLY_SERVICES
    assert overlap == frozenset(), f"Overlap: {overlap}"


def test_constants_cover_all_service_types():
    all_services = {s.value for s in ServiceType}
    covered = OPENROUTER_BACKED_SERVICES | PLATFORM_ONLY_SERVICES
    uncovered = all_services - covered
    assert uncovered == set(), f"Service(s) not classified: {uncovered}"


@pytest.mark.django_db
def test_image_generation_byok_origin_accepted_at_billing_layer(billing, user_with_byok):
    """IMAGE_GENERATION is mixed-provider (OpenRouter + Google AI Studio).
    Membership in OPENROUTER_BACKED_SERVICES means the guard allows
    'byok'. Call-site enforcement at image_tools.py:_record_billing
    hard-codes 'platform' for the Google AI Studio path; this test
    documents that intentional gap.
    """
    op = BillableOperation(
        service=ServiceType.IMAGE_GENERATION,
        feature=FeatureType.CHAT,
        cost_usd=Decimal('0.04'),
    )
    billing.record_usage(user_with_byok, op, billing_origin=BILLING_ORIGIN_BYOK)
    log = UsageLog.objects.get(user=user_with_byok)
    assert log.cost_usd == Decimal('0')
    assert log.billing_origin == 'byok'


@pytest.mark.django_db
def test_check_quota_assume_origin_does_not_bypass_platform_only(billing, user_with_byok):
    """assume_origin='byok' for ELEVENLABS_TTS still hits the real check."""
    status = billing.check_quota(
        user=user_with_byok,
        service=ServiceType.ELEVENLABS_TTS,
        estimated_cost=Decimal('0.50'),
        feature=FeatureType.VOICE_ROOM,
        assume_origin=BILLING_ORIGIN_BYOK,
    )
    # weekly_limit_usd should be populated from the plan, NOT the
    # short-circuit zeros (which would prove we bypassed).
    assert status.weekly_limit_usd == Decimal('5')


@pytest.mark.django_db
def test_check_quota_assume_origin_byok_skips_for_openrouter(billing, user_with_byok):
    """assume_origin='byok' for OPENROUTER returns short-circuit allowed."""
    status = billing.check_quota(
        user=user_with_byok,
        service=ServiceType.OPENROUTER,
        estimated_cost=Decimal('100'),
        feature=FeatureType.CHAT,
        assume_origin=BILLING_ORIGIN_BYOK,
    )
    assert status.allowed is True
    assert status.weekly_limit_usd == Decimal('0')


@pytest.mark.django_db
def test_provisioned_then_byok_uploads_classify_as_byok(db, free_plan):
    """Regression for review-1.md #1: user uploads own key → classified BYOK."""
    from llm.services.api_key_resolver import resolve_with_origin

    u = User.objects.create_user(email='switcher@test.com', password='x')
    UserSubscription.objects.create(user=u, plan=free_plan, is_active=True)
    # State 1: auto-provisioned
    u.openrouter_api_key = 'sk-or-platform-provisioned'
    u.openrouter_key_provisioned_at = timezone.now()
    u.openrouter_key_hash = 'someplatformhash'
    u.save()
    _, origin = resolve_with_origin(user=u)
    assert origin == 'platform'

    # State 2: user uploads their own key — POST handler nulls markers
    u.openrouter_api_key = 'sk-or-user-uploaded'
    u.openrouter_key_provisioned_at = None
    u.openrouter_key_hash = None
    u.save()
    key, origin = resolve_with_origin(user=u)
    assert key == 'sk-or-user-uploaded'
    assert origin == 'byok'
