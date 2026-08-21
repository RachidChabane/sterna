"""Single source of truth for per-feature gates.

Every billable surface registers a FeatureSpec here. Views and tools
pass only `feature_name` to BillingService.check_quota — the registry
resolves flag/limit/count provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from authentication.models import User
    from usage_quota.models import SubscriptionPlan


@dataclass(frozen=True)
class FeatureSpec:
    feature_name: str                              # canonical key
    flag_key: Optional[str]                        # SubscriptionPlan.features key
    limit_field: Optional[str]                     # SubscriptionPlan attribute
    count_provider: Optional[Callable[["User", "SubscriptionPlan"], int]]
    unit: str                                      # 'count' | 'seconds' | 'mb' | 'minutes_per_session'
    quota_window: str = "weekly"                   # 'weekly' | 'session' | 'storage'

    def is_disabled(self, plan: "SubscriptionPlan") -> bool:
        """A feature is hard-disabled when the limit field == 0 OR the
        plan flag is False. `None` on the limit field = unlimited.
        """
        if self.flag_key and not plan.features.get(self.flag_key, False):
            return True
        if self.limit_field:
            limit = getattr(plan, self.limit_field, None)
            if limit == 0:
                return True
        return False


# Count providers — one function per feature. Each returns the
# current count within the user's active weekly window (or lifetime
# for storage limits).
def _count_voice_sessions(user, plan):
    from voice_rooms.models import VoiceRoomSession

    window_start = _user_weekly_window_start(user)
    if window_start is None:
        return 0
    return VoiceRoomSession.objects.filter(
        room__user=user,
        started_at__gte=window_start,
    ).count()


def _count_code_sessions(user, plan):
    from code_sessions.models import CodeJob

    window_start = _user_weekly_window_start(user)
    if window_start is None:
        return 0
    return CodeJob.objects.filter(
        session__user=user,
        created_at__gte=window_start,
    ).count()


def _count_image_generations(user, plan):
    from usage_quota.models import ServiceType, UsageLog

    window_start = _user_weekly_window_start(user)
    if window_start is None:
        return 0
    # Single attribution path: every image-gen tool call writes one
    # UsageLog row with service=IMAGE_GENERATION. The aggregate row in
    # langchain_agent's accumulated_tool_cost path subtracts image
    # dollars to avoid double-billing — see Section 2.11.
    return UsageLog.objects.filter(
        user=user,
        service=ServiceType.IMAGE_GENERATION,
        timestamp__gte=window_start,
    ).count()


def _sum_video_seconds(user, plan):
    from django.db.models import Sum

    from usage_quota.models import ServiceType, UsageLog

    window_start = _user_weekly_window_start(user)
    if window_start is None:
        return 0
    total = UsageLog.objects.filter(
        user=user,
        service=ServiceType.VIDEO_GENERATION,
        timestamp__gte=window_start,
    ).aggregate(t=Sum('audio_seconds'))['t']
    return int(total or 0)


def _count_mcp_invocations(user, plan):
    from usage_quota.models import ServiceType, UsageLog

    window_start = _user_weekly_window_start(user)
    if window_start is None:
        return 0
    return UsageLog.objects.filter(
        user=user,
        service=ServiceType.MCP_TOOL_INVOCATION,
        timestamp__gte=window_start,
    ).count()


def _count_kb_docs(user, plan):
    # Lifetime count — docs persist across weekly windows.
    from knowledge_base.models import KnowledgeDocument

    return KnowledgeDocument.objects.filter(user=user).count()


def _kb_storage_used_mb(user, plan):
    from knowledge_base.models import KnowledgeBaseSettings

    s = KnowledgeBaseSettings.objects.filter(user=user).first()
    if s is None:
        return 0
    used_bytes = getattr(s, 'total_storage_bytes', 0) or 0
    return int(used_bytes // (1024 * 1024))


def _user_weekly_window_start(user):
    """Resolve the active weekly window start for the user."""
    from usage_quota.models import UserSubscription

    sub = UserSubscription.objects.filter(user=user, is_active=True).first()
    if sub is None or sub.weekly_window_start is None:
        return None
    return sub.weekly_window_start


_FEATURES: dict[str, FeatureSpec] = {}


def register(spec: FeatureSpec) -> None:
    if spec.feature_name in _FEATURES:
        raise ValueError(f"FeatureSpec {spec.feature_name} already registered")
    _FEATURES[spec.feature_name] = spec


def get(feature_name: str) -> FeatureSpec | None:
    return _FEATURES.get(feature_name)


def all_features() -> dict[str, FeatureSpec]:
    return dict(_FEATURES)


# ============================================================================
# REGISTRATION (alphabetical for grep-ability)
# ============================================================================

register(FeatureSpec(
    feature_name='brave_search',
    flag_key='search',
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='chat',
    flag_key='chat',
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='code_session',
    flag_key='code_sessions',
    limit_field='code_session_weekly_limit',
    count_provider=_count_code_sessions,
    unit='count',
))
register(FeatureSpec(
    feature_name='image_generation',
    flag_key='image_gen',
    limit_field='image_gen_weekly_limit',
    count_provider=_count_image_generations,
    unit='count',
))
register(FeatureSpec(
    feature_name='kb_query',
    flag_key='knowledge_base',
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='kb_storage_mb',
    flag_key='knowledge_base',
    limit_field='kb_storage_mb_limit',
    count_provider=_kb_storage_used_mb,
    unit='mb',
    quota_window='storage',
))
register(FeatureSpec(
    feature_name='kb_upload',
    flag_key='knowledge_base',
    limit_field='kb_docs_limit',
    count_provider=_count_kb_docs,
    unit='count',
    quota_window='storage',
))
register(FeatureSpec(
    feature_name='maps_invocation',
    flag_key=None,
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='mcp_tool_invocation',
    flag_key='mcp',
    limit_field='mcp_invocations_weekly_limit',
    count_provider=_count_mcp_invocations,
    unit='count',
))
register(FeatureSpec(
    feature_name='spark_deploy',
    flag_key='sparks_create',
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='spark_generation',
    flag_key='sparks_create',
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='video_generation_seconds',
    flag_key='video_gen',
    limit_field='video_gen_seconds_weekly_limit',
    count_provider=_sum_video_seconds,
    unit='seconds',
))
register(FeatureSpec(
    feature_name='voice_llm',
    flag_key='voice_rooms',
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='voice_minutes',
    flag_key='voice_rooms',
    limit_field='voice_room_minutes_per_session_limit',
    count_provider=None,
    unit='minutes_per_session',
))
register(FeatureSpec(
    feature_name='voice_session',
    flag_key='voice_rooms',
    limit_field='voice_room_sessions_weekly_limit',
    count_provider=_count_voice_sessions,
    unit='count',
))
register(FeatureSpec(
    feature_name='voice_stt',
    flag_key='voice_rooms',
    limit_field=None,
    count_provider=None,
    unit='count',
))
register(FeatureSpec(
    feature_name='voice_tts',
    flag_key='voice_rooms',
    limit_field=None,
    count_provider=None,
    unit='count',
))
