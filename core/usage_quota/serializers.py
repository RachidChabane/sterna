"""Serializers for Usage & Quota API endpoints."""

from rest_framework import serializers

from .models import UsageLog, SubscriptionPlan, ServiceType, FeatureType


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plan details."""

    class Meta:
        model = SubscriptionPlan
        fields = [
            'name',
            'display_name',
            'weekly_limit_usd',
            'session_limit_usd',
            'features',
        ]


class QuotaInfoSerializer(serializers.Serializer):
    """Serializer for quota information response."""

    plan = serializers.CharField(source='plan_name')
    plan_display_name = serializers.CharField()

    weekly = serializers.SerializerMethodField()
    session = serializers.SerializerMethodField()
    features = serializers.DictField()
    by_service = serializers.DictField()
    by_feature = serializers.DictField()

    def get_weekly(self, obj):
        return {
            'limit_usd': str(obj.weekly_limit_usd),
            'used_usd': str(obj.weekly_used_usd),
            'remaining_usd': str(obj.weekly_remaining_usd),
            'window_start': obj.window_start,
            'window_end': obj.window_end,
        }

    def get_session(self, obj):
        return {
            'limit_usd': str(obj.session_limit_usd),
            'used_usd': str(obj.session_used_usd),
            'remaining_usd': str(obj.session_remaining_usd),
            'window_start': obj.session_window_start,
            'window_end': obj.session_window_end,
        }


class UsageLogSerializer(serializers.ModelSerializer):
    """Serializer for usage log entries."""

    cost_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)

    class Meta:
        model = UsageLog
        fields = [
            'id',
            'timestamp',
            'service',
            'feature',
            'session_id',
            'model_id',
            'prompt_tokens',
            'completion_tokens',
            'total_tokens',
            'character_count',
            'audio_seconds',
            'request_count',
            'cost_usd',
        ]


class UsageSummarySerializer(serializers.Serializer):
    """Serializer for usage summary response."""

    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    total_cost_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)
    total_requests = serializers.IntegerField()

    by_service = serializers.DictField()
    by_feature = serializers.DictField()
    by_day = serializers.ListField()


class QuotaCheckRequestSerializer(serializers.Serializer):
    """Serializer for internal quota check request.

    The target user is always ``request.user`` (the JWT-authenticated
    caller). The legacy ``user_id`` field was removed in task-29 to
    close an IDOR (C1) — callers like brave-search forward the
    end-user's JWT, so ``request.user`` IS the right target.
    """

    service = serializers.ChoiceField(choices=ServiceType.choices)
    # Cost can be provided directly OR calculated from request_count
    estimated_cost_usd = serializers.DecimalField(
        max_digits=10, decimal_places=6, required=False, allow_null=True
    )
    request_count = serializers.IntegerField(required=False, default=1)
    feature = serializers.ChoiceField(choices=FeatureType.choices, default=FeatureType.CHAT)
    session_id = serializers.CharField(required=False, allow_blank=True)


class QuotaCheckResponseSerializer(serializers.Serializer):
    """Serializer for quota check response."""

    allowed = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    remaining_weekly_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)
    remaining_session_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)
    weekly_limit_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)
    session_limit_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)


class UsageDeductRequestSerializer(serializers.Serializer):
    """Serializer for internal usage deduction request.

    The target user is always ``request.user`` (the JWT-authenticated
    caller). See ``QuotaCheckRequestSerializer`` for the C1 rationale.
    """

    service = serializers.ChoiceField(choices=ServiceType.choices)
    # Cost can be provided directly OR calculated from request_count/character_count/audio_seconds
    cost_usd = serializers.DecimalField(
        max_digits=10, decimal_places=6, required=False, allow_null=True
    )
    feature = serializers.ChoiceField(choices=FeatureType.choices, default=FeatureType.CHAT)
    session_id = serializers.CharField(required=False, allow_blank=True)
    model_id = serializers.CharField(required=False, allow_blank=True, default='')
    prompt_tokens = serializers.IntegerField(required=False, default=0)
    completion_tokens = serializers.IntegerField(required=False, default=0)
    character_count = serializers.IntegerField(required=False, default=0)
    audio_seconds = serializers.FloatField(required=False, default=0)
    request_count = serializers.IntegerField(required=False, default=1)
    request_id = serializers.CharField(required=False, allow_blank=True, default='')
    extra_data = serializers.DictField(required=False, default=dict)


class UsageDeductResponseSerializer(serializers.Serializer):
    """Serializer for usage deduction response."""

    success = serializers.BooleanField()
    usage_log_id = serializers.CharField(allow_null=True)
    cost_usd = serializers.DecimalField(
        max_digits=10, decimal_places=6, coerce_to_string=True, required=False
    )
    new_weekly_used_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)
    new_remaining_weekly_usd = serializers.DecimalField(max_digits=10, decimal_places=6, coerce_to_string=True)


class SubscriptionPlanDetailSerializer(serializers.ModelSerializer):
    """Public serializer for the user's current plan (read-only).

    Includes per-feature count limits (via ``get_per_feature_limits()``)
    and the Stripe price-id placeholders that task 11 will populate.
    """

    per_feature_limits = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = [
            "name",
            "display_name",
            "description",
            "weekly_limit_usd",
            "session_limit_usd",
            "features",
            "per_feature_limits",
            "stripe_price_id_monthly",
            "stripe_price_id_yearly",
            "is_active",
        ]

    def get_per_feature_limits(self, obj):
        return obj.get_per_feature_limits()


# =============================================================================
# Stripe Checkout + Customer Portal (task 12)
# =============================================================================


class CheckoutSessionRequestSerializer(serializers.Serializer):
    """Body for ``POST /api/billing/checkout-session/``.

    ``plan_slug`` excludes ``'free'`` because Free has no Stripe price; the
    400 from ChoiceField is clean and avoids a wasted DB lookup.
    """

    plan_slug = serializers.ChoiceField(choices=['plus', 'pro'])
    billing_cycle = serializers.ChoiceField(choices=['monthly', 'yearly'])


class CheckoutSessionResponseSerializer(serializers.Serializer):
    """Successful 200 from ``POST /api/billing/checkout-session/``."""

    url = serializers.URLField()


class PortalSessionResponseSerializer(serializers.Serializer):
    """Successful 200 from ``POST /api/billing/portal-session/``."""

    url = serializers.URLField()


class SyncFromSessionResponseSerializer(serializers.Serializer):
    """Successful 200 from ``POST /api/billing/sync-from-session/``."""

    plan = serializers.CharField()
    plan_display_name = serializers.CharField()
    status = serializers.CharField()
    current_period_end = serializers.IntegerField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()


class BillingStatusSerializer(serializers.Serializer):
    """Surface for ``GET /api/billing/status/`` (the /settings/billing page).

    Bundles the current plan name + display name + the two new cached
    Stripe fields so the frontend can render renewal date + cancellation
    banner without a separate Stripe API call. Free-plan users get
    ``current_period_end=None`` and ``cancel_at_period_end=False``.
    """

    plan = serializers.CharField()
    plan_display_name = serializers.CharField()
    plan_description = serializers.CharField(allow_blank=True)
    is_paid = serializers.BooleanField()
    current_period_end = serializers.IntegerField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()


class UsageWithLimitsSerializer(serializers.Serializer):
    """Shape returned by ``GET /api/subscription/usage/``.

    ``per_feature`` is a dict keyed by feature name (``voice_room``,
    ``code_session``, ``image_gen``, ``video_gen``, ``mcp``,
    ``kb_storage_mb``, ``kb_docs``) with nested
    ``{used: int|null, used_usd: str, limit: int|null}``. ``used`` is
    nullable when the backend cannot reliably attribute usage to that
    feature yet (task 10 closes this gap).
    """

    weekly_used_usd = serializers.DecimalField(
        max_digits=10, decimal_places=6, coerce_to_string=True
    )
    weekly_limit_usd = serializers.DecimalField(
        max_digits=10, decimal_places=6, coerce_to_string=True
    )
    weekly_window_end = serializers.CharField(allow_blank=True)
    session_used_usd = serializers.DecimalField(
        max_digits=10, decimal_places=6, coerce_to_string=True
    )
    session_limit_usd = serializers.DecimalField(
        max_digits=10, decimal_places=6, coerce_to_string=True
    )
    session_window_end = serializers.CharField(allow_blank=True)
    per_feature = serializers.DictField(child=serializers.DictField())
