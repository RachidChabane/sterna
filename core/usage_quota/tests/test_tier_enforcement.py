"""Parametrized (tier × feature) tier-enforcement matrix.

Tests three outcomes per (tier, feature) combination:
- flag-disabled → ``FeatureNotAvailable``
- flag-enabled, within limits → no raise
- flag-enabled, over limit → ``QuotaExceeded`` (with reset_at when applicable)
- unlimited tier × feature, high usage → still allowed

Per-test seeding (function-scoped) avoids pytest-django's session-scope
DB unblock requirement.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from authentication.models import User
from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.billing.service import get_billing_service
from usage_quota.exceptions import (
    FeatureNotAvailableException,
    QuotaExceededException,
)
from usage_quota.feature_registry import all_features
from usage_quota.models import (
    FeatureType,
    ServiceType,
    SubscriptionPlan,
    UsageLog,
    UserSubscription,
)


SERVICE_MAP = {
    'brave_search': (ServiceType.BRAVE_SEARCH, FeatureType.SEARCH),
    'chat': (ServiceType.OPENROUTER, FeatureType.CHAT),
    'voice_session': (ServiceType.ELEVENLABS_TTS, FeatureType.VOICE_ROOM),
    'voice_tts': (ServiceType.ELEVENLABS_TTS, FeatureType.VOICE_ROOM),
    'voice_stt': (ServiceType.DEEPGRAM_STT, FeatureType.VOICE_ROOM),
    'voice_llm': (ServiceType.OPENROUTER, FeatureType.VOICE_ROOM),
    'voice_minutes': (ServiceType.ELEVENLABS_TTS, FeatureType.VOICE_ROOM),
    'code_session': (ServiceType.CODE_SESSION, FeatureType.CODE_SESSION),
    'image_generation': (ServiceType.IMAGE_GENERATION, FeatureType.CHAT),
    'video_generation_seconds': (ServiceType.VIDEO_GENERATION, FeatureType.CHAT),
    'mcp_tool_invocation': (ServiceType.MCP_TOOL_INVOCATION, FeatureType.CHAT),
    'kb_upload': (
        ServiceType.KNOWLEDGE_BASE_EMBEDDING, FeatureType.KNOWLEDGE_BASE,
    ),
    'kb_query': (ServiceType.KNOWLEDGE_BASE_QUERY, FeatureType.KNOWLEDGE_BASE),
    'kb_storage_mb': (
        ServiceType.KNOWLEDGE_BASE_EMBEDDING, FeatureType.KNOWLEDGE_BASE,
    ),
    'spark_generation': (ServiceType.OPENROUTER, FeatureType.CHAT),
    'spark_deploy': (ServiceType.OPENROUTER, FeatureType.OTHER),
    'maps_invocation': (ServiceType.GOOGLE_MAPS, FeatureType.CHAT),
}


def _make_user(tier_slug: str, suffix: str = '') -> User:
    email = f'{tier_slug}{suffix}@test.com'
    user = User.objects.create_user(email=email, password='x')
    plan = SubscriptionPlan.objects.get(name=tier_slug)
    UserSubscription.objects.create(user=user, plan=plan, is_active=True)
    return user


@pytest.fixture(autouse=True)
def _seed_tiers(db):
    seed_tiers_for_tests()


@pytest.mark.django_db
@pytest.mark.parametrize('tier,feature_name', [
    (tier, name)
    for tier in ('free', 'plus', 'pro')
    for name in all_features().keys()
])
def test_flag_disabled_raises_feature_not_available(tier, feature_name):
    """Plan flag_key=False → check_quota raises FeatureNotAvailable."""
    spec = all_features()[feature_name]
    if spec.flag_key is None:
        pytest.skip("no flag gate for this feature")
    plan = SubscriptionPlan.objects.get(name=tier)
    if plan.features.get(spec.flag_key, False):
        pytest.skip("plan has feature enabled — handled in over-limit test")

    user = _make_user(tier, suffix=f'-flag-{feature_name}')
    billing = get_billing_service()
    service, feature = SERVICE_MAP[feature_name]
    with pytest.raises(FeatureNotAvailableException):
        billing.check_quota(
            user=user,
            service=service,
            estimated_cost=Decimal('0'),
            feature=feature,
            feature_name=feature_name,
        )


@pytest.mark.django_db
@pytest.mark.parametrize('tier,feature_name', [
    (tier, name)
    for tier in ('free', 'plus', 'pro')
    for name in all_features().keys()
])
def test_within_limit_allows(tier, feature_name):
    """Flag enabled + no usage → allowed."""
    spec = all_features()[feature_name]
    plan = SubscriptionPlan.objects.get(name=tier)
    if spec.flag_key and not plan.features.get(spec.flag_key, False):
        pytest.skip("flag-gated for this tier")
    if spec.limit_field and getattr(plan, spec.limit_field) == 0:
        pytest.skip("limit field is 0 (same as flag-off)")

    user = _make_user(tier, suffix=f'-within-{feature_name}')
    billing = get_billing_service()
    service, feature = SERVICE_MAP[feature_name]
    billing.check_quota(
        user=user,
        service=service,
        estimated_cost=Decimal('0'),
        feature=feature,
        feature_name=feature_name,
    )


@pytest.mark.django_db
@pytest.mark.parametrize('tier,feature_name', [
    (tier, name)
    for tier in ('free', 'plus', 'pro')
    for name, spec in all_features().items()
    if spec.count_provider is not None
])
def test_over_limit_raises_quota_exceeded(tier, feature_name):
    """Push usage above the limit → QuotaExceeded with reset_at (or None for storage)."""
    spec = all_features()[feature_name]
    plan = SubscriptionPlan.objects.get(name=tier)
    limit = getattr(plan, spec.limit_field)
    if limit is None or limit == 0:
        pytest.skip("unlimited or disabled — handled elsewhere")
    if spec.flag_key and not plan.features.get(spec.flag_key, False):
        pytest.skip("flag-gated for this tier — handled in flag test")

    user = _make_user(tier, suffix=f'-over-{feature_name}')
    sub = UserSubscription.objects.get(user=user)
    sub.weekly_window_start = timezone.now() - timedelta(seconds=1)
    sub.save()

    _seed_n_units(user, feature_name, limit)

    billing = get_billing_service()
    service, feature = SERVICE_MAP[feature_name]
    with pytest.raises(QuotaExceededException) as exc_info:
        billing.check_quota(
            user=user,
            service=service,
            estimated_cost=Decimal('0'),
            feature=feature,
            feature_name=feature_name,
            request_units=1,
        )
    exc = exc_info.value
    assert exc.feature_name == feature_name
    assert exc.limit_count == limit
    if spec.quota_window != 'storage':
        assert exc.reset_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize('tier,feature_name', [
    (tier, name)
    for tier in ('free', 'plus', 'pro')
    for name, spec in all_features().items()
    if spec.count_provider is not None
])
def test_unlimited_stays_unlimited(tier, feature_name):
    """When limit_field is None (unlimited), high usage still allows."""
    spec = all_features()[feature_name]
    plan = SubscriptionPlan.objects.get(name=tier)
    limit = getattr(plan, spec.limit_field)
    if limit is not None:
        pytest.skip("not an unlimited tier for this feature")
    if spec.flag_key and not plan.features.get(spec.flag_key, False):
        pytest.skip("flag-gated for this tier")

    user = _make_user(tier, suffix=f'-unlim-{feature_name}')
    sub = UserSubscription.objects.get(user=user)
    sub.weekly_window_start = timezone.now() - timedelta(seconds=1)
    sub.save()

    _seed_n_units(user, feature_name, 1000)

    billing = get_billing_service()
    service, feature = SERVICE_MAP[feature_name]
    billing.check_quota(
        user=user,
        service=service,
        estimated_cost=Decimal('0'),
        feature=feature,
        feature_name=feature_name,
        request_units=1,
    )


def _seed_n_units(user, feature_name, n):
    """Insert n units so the count provider returns >= n."""
    if feature_name == 'voice_session':
        from voice_rooms.models import VoiceRoom, VoiceRoomSession
        room = VoiceRoom.objects.create(user=user, name='test')
        for _ in range(n):
            VoiceRoomSession.objects.create(room=room, status='idle')
    elif feature_name == 'code_session':
        from code_sessions.models import CodeJob, CodeSession
        session = CodeSession.objects.create(
            user=user,
            name='test-session',
            github_repo_full_name='x/y',
        )
        for _ in range(n):
            CodeJob.objects.create(session=session, prompt='p')
    elif feature_name == 'image_generation':
        for _ in range(n):
            UsageLog.objects.create(
                user=user,
                service=ServiceType.IMAGE_GENERATION,
                feature=FeatureType.CHAT,
                cost_usd=Decimal('0.01'),
                extra_data={'tool': 'generate_image'},
            )
    elif feature_name == 'video_generation_seconds':
        UsageLog.objects.create(
            user=user,
            service=ServiceType.VIDEO_GENERATION,
            feature=FeatureType.CHAT,
            cost_usd=Decimal('0.10'),
            audio_seconds=n,
        )
    elif feature_name == 'mcp_tool_invocation':
        for _ in range(n):
            UsageLog.objects.create(
                user=user,
                service=ServiceType.MCP_TOOL_INVOCATION,
                feature=FeatureType.CHAT,
                cost_usd=Decimal('0.001'),
            )
    elif feature_name == 'kb_upload':
        from knowledge_base.models import (
            DocumentStatus,
            DocumentType,
            KnowledgeDocument,
        )
        for i in range(n):
            KnowledgeDocument.objects.create(
                user=user,
                filename=f'doc{i}.txt',
                original_filename=f'doc{i}.txt',
                document_type=DocumentType.TXT,
                mime_type='text/plain',
                file_size_bytes=1024,
                content_hash=f'hash-{user.id}-{i}',
                status=DocumentStatus.READY,
            )
    elif feature_name == 'kb_storage_mb':
        from knowledge_base.models import KnowledgeBaseSettings
        s, _ = KnowledgeBaseSettings.objects.get_or_create(user=user)
        s.total_storage_bytes = n * 1024 * 1024
        s.save()
