"""
Usage & Quota Models.

Centralized usage tracking and quota enforcement for all billable external services.
Normalizes costs to USD and enforces fixed 7-day and 3-hour session limits.
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from authentication.models import User


class ServiceType(models.TextChoices):
    """External services that are tracked for usage and billing."""
    OPENROUTER = 'openrouter', 'OpenRouter LLM'
    ELEVENLABS_TTS = 'elevenlabs_tts', 'ElevenLabs TTS'
    OPENAI_TTS = 'openai_tts', 'OpenAI TTS'
    DEEPGRAM_STT = 'deepgram_stt', 'Deepgram STT'
    BRAVE_SEARCH = 'brave_search', 'Brave Search'
    IMAGE_GENERATION = 'image_generation', 'Image Generation'
    VIDEO_GENERATION = 'video_generation', 'Video Generation'
    KNOWLEDGE_BASE_EMBEDDING = 'kb_embedding', 'Knowledge Base Embedding'
    KNOWLEDGE_BASE_QUERY = 'kb_query', 'Knowledge Base Query'
    CODE_SESSION = 'code_session', 'Code Session (Claude CLI)'
    MCP_TOOL_INVOCATION = 'mcp_tool_invocation', 'MCP Tool Invocation'
    GOOGLE_MAPS = 'google_maps', 'Google Maps Platform'


class FeatureType(models.TextChoices):
    """Features that consume billable resources."""
    CHAT = 'chat', 'Chat'
    VOICE_ROOM = 'voice_room', 'Voice Room'
    CODE_SESSION = 'code_session', 'Code Session'
    SEARCH = 'search', 'Search'
    CONSIGLIERE = 'consigliere', 'Consigliere'
    KNOWLEDGE_BASE = 'knowledge_base', 'Knowledge Base'
    OTHER = 'other', 'Other'


class SubscriptionPlan(models.Model):
    """
    Defines subscription tiers with their limits and feature access.

    Examples: 'free', 'pro', 'enterprise'
    """
    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    # Plan identification
    name: models.CharField = models.CharField(
        max_length=50, unique=True, db_index=True
    )
    display_name: models.CharField = models.CharField(max_length=100)
    description: models.TextField = models.TextField(blank=True)

    # Global limits (in USD)
    weekly_limit_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Fixed 7-day spending limit in USD (starts on first usage)"
    )
    session_limit_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Per-session spending limit in USD"
    )

    # Feature access flags
    features = models.JSONField(
        default=dict,
        help_text="Feature access flags, e.g., {'voice_rooms': true, 'code_sessions': true}"
    )

    # Per-feature limits (nullable for future flexibility)
    chat_weekly_limit_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional per-feature weekly limit for chat"
    )
    voice_room_weekly_limit_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional per-feature weekly limit for voice rooms"
    )
    code_session_weekly_limit_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional per-feature weekly limit for code sessions"
    )

    # --- Per-feature count limits (task 9) ---
    # Count limits are checked first; the *_weekly_limit_usd fields above
    # are advisory until task 10 wires them into QuotaService.check_quota.
    voice_room_sessions_weekly_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text="Max voice-room sessions per 7-day window. None = unlimited; 0 = feature disabled.",
    )
    voice_room_minutes_per_session_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text="Max minutes per single voice-room session. None = unlimited.",
    )
    code_session_weekly_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text=(
            "Max code-session count per 7-day window. None = unlimited; 0 = feature disabled. "
            "Distinct from code_session_weekly_limit_usd which is a $-budget (advisory until task 10)."
        ),
    )
    kb_storage_mb_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text="Total knowledge-base storage in MB. None = unlimited.",
    )
    kb_docs_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text="Max documents in knowledge base. None = unlimited.",
    )
    image_gen_weekly_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text="Max image generations per 7-day window. None = unlimited; 0 = feature disabled.",
    )
    video_gen_seconds_weekly_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text="Max seconds of generated video per 7-day window. None = unlimited; 0 = feature disabled.",
    )
    mcp_invocations_weekly_limit: models.IntegerField = models.IntegerField(
        null=True, blank=True,
        help_text="Max MCP tool invocations per 7-day window. None = unlimited; 0 = feature disabled.",
    )

    # --- Stripe linkage placeholders (task 11 wires) ---
    stripe_price_id_monthly: models.CharField = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Stripe price ID for monthly billing. Filled by task 11.",
    )
    stripe_price_id_yearly: models.CharField = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Stripe price ID for yearly billing. Filled by task 11.",
    )

    # Status
    is_active: models.BooleanField = models.BooleanField(default=True)
    is_default: models.BooleanField = models.BooleanField(
        default=False,
        help_text="If true, new users are assigned this plan by default"
    )

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"
        ordering = ['weekly_limit_usd']

    def __str__(self):
        return f"{self.display_name} (${self.weekly_limit_usd}/week)"

    def has_feature(self, feature: str) -> bool:
        """Check if this plan includes a specific feature."""
        return self.features.get(feature, False)

    def get_per_feature_limits(self) -> dict:
        """Return per-feature count limits as a dict. ``None`` means unlimited."""
        return {
            "voice_room": self.voice_room_sessions_weekly_limit,
            "code_session": self.code_session_weekly_limit,
            "image_gen": self.image_gen_weekly_limit,
            "video_gen": self.video_gen_seconds_weekly_limit,
            "mcp": self.mcp_invocations_weekly_limit,
            "kb_storage_mb": self.kb_storage_mb_limit,
            "kb_docs": self.kb_docs_limit,
        }

    @classmethod
    def get_default_plan(cls):
        """Get the default plan for new users."""
        return cls.objects.filter(is_default=True, is_active=True).first()


class UserSubscription(models.Model):
    """
    Links a user to their subscription plan.

    Supports custom limit overrides for enterprise/special cases.
    """
    if TYPE_CHECKING:
        # Shadow attribute Django generates for the `plan` ForeignKey;
        # not otherwise visible to mypy without the django-stubs plugin.
        plan_id: uuid.UUID

    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    user: "models.OneToOneField[User, User]" = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan: "models.ForeignKey[SubscriptionPlan, SubscriptionPlan]" = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )

    # Custom limit overrides (for enterprise/special deals)
    custom_weekly_limit_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override weekly limit (if set, takes precedence over plan)"
    )
    custom_session_limit_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override session limit (if set, takes precedence over plan)"
    )

    # --- Stripe linkage placeholder (task 11 wires) ---
    stripe_subscription_id: models.CharField = models.CharField(
        max_length=255, null=True, blank=True, db_index=True,
        help_text="Stripe subscription ID (sub_…). Filled by task 11.",
    )

    # Cached Stripe subscription state (task 12) — populated by
    # sync_from_session and (post-task-13) the webhook handler so
    # /settings/billing can render the renewal date + cancellation banner
    # without a Stripe API call on each page load. NULL for free-plan
    # users (no Stripe subscription).
    current_period_end: models.BigIntegerField = models.BigIntegerField(
        null=True, blank=True,
        help_text="Unix seconds when the current Stripe billing period ends.",
    )
    cancel_at_period_end: models.BooleanField = models.BooleanField(
        default=False,
        help_text="True iff the user has cancelled and the sub ends at period end.",
    )
    stripe_event_created: models.BigIntegerField = models.BigIntegerField(
        null=True, blank=True,
        help_text=(
            "Unix seconds `created` of the newest Stripe subscription "
            "event applied to this row. Webhook handlers skip writes "
            "from events older than this marker (out-of-order delivery "
            "guard)."
        ),
    )

    # Fixed usage windows (start on first usage, expire after duration)
    # Null means no active window - new window starts on next usage
    session_window_start: models.DateTimeField = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of current session window (3h). Null = no active session."
    )
    weekly_window_start: models.DateTimeField = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of current weekly window (7d). Null = no active window."
    )

    # Status
    is_active: models.BooleanField = models.BooleanField(default=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Subscription"
        verbose_name_plural = "User Subscriptions"

    def __str__(self):
        return f"{self.user.email} - {self.plan.name}"

    @property
    def effective_weekly_limit(self) -> Decimal:
        """Get the effective weekly limit (custom override or plan default)."""
        if self.custom_weekly_limit_usd is not None:
            return self.custom_weekly_limit_usd
        return self.plan.weekly_limit_usd

    @property
    def effective_session_limit(self) -> Decimal:
        """Get the effective session limit (custom override or plan default)."""
        if self.custom_session_limit_usd is not None:
            return self.custom_session_limit_usd
        return self.plan.session_limit_usd

    def has_feature(self, feature: str) -> bool:
        """Check if user has access to a feature via their plan."""
        return self.plan.has_feature(feature)


class ServicePricing(models.Model):
    """
    Pricing configuration for external services.

    Supports per-model pricing with effective dates for pricing changes.
    All prices normalized to USD.
    """
    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    service: models.CharField = models.CharField(
        max_length=50,
        choices=ServiceType.choices,
        db_index=True
    )
    model_id: models.CharField = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Specific model identifier (blank for service-wide default)"
    )

    # Pricing units (set the relevant one based on service type)
    price_per_1m_input_tokens: models.DecimalField = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per 1M input/prompt tokens (for LLM services)"
    )
    price_per_1m_output_tokens: models.DecimalField = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per 1M output/completion tokens (for LLM services)"
    )
    price_per_1k_chars: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per 1K characters (for TTS services)"
    )
    price_per_minute: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per audio minute (for STT services)"
    )
    price_per_request: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per request (for search services)"
    )

    # Effective dates
    effective_from: models.DateTimeField = models.DateTimeField(db_index=True)
    effective_until: models.DateTimeField = models.DateTimeField(null=True, blank=True)

    # Status
    is_active: models.BooleanField = models.BooleanField(default=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Service Pricing"
        verbose_name_plural = "Service Pricing"
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['service', 'model_id', 'effective_from']),
        ]

    def __str__(self):
        model_str = f"/{self.model_id}" if self.model_id else ""
        return f"{self.get_service_display()}{model_str} (from {self.effective_from.date()})"


BILLING_ORIGIN_CHOICES = [
    ('platform', 'Platform'),
    ('byok', 'BYOK'),
]


class UsageLog(models.Model):
    """
    Append-only ledger of record for every billable service usage event.

    This is the sole source of truth for billing and quota decisions,
    service-agnostic and normalized to USD. Provider-specific analytics
    (e.g. OpenRouter generation records) are a separate concern and must
    never be read for billing or quota purposes.
    """
    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    user: "models.ForeignKey[User, User]" = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='usage_logs'
    )

    # Service identification
    service: models.CharField = models.CharField(
        max_length=50,
        choices=ServiceType.choices,
        db_index=True
    )

    # Feature context
    feature: models.CharField = models.CharField(
        max_length=50,
        choices=FeatureType.choices,
        db_index=True,
        help_text="Which feature triggered this usage"
    )
    session_id: models.CharField = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Session ID for grouping related usage (e.g., voice room session)"
    )

    # Service-specific usage details
    model_id: models.CharField = models.CharField(max_length=255, blank=True)
    prompt_tokens: models.IntegerField = models.IntegerField(default=0)
    completion_tokens: models.IntegerField = models.IntegerField(default=0)
    total_tokens: models.IntegerField = models.IntegerField(default=0)
    character_count: models.IntegerField = models.IntegerField(default=0)
    audio_seconds: models.FloatField = models.FloatField(default=0)
    request_count: models.IntegerField = models.IntegerField(default=1)

    # Normalized cost (always in USD)
    cost_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="Cost in USD"
    )

    # Request metadata
    request_id: models.CharField = models.CharField(
        max_length=255,
        blank=True,
        help_text="External request ID (e.g., OpenRouter request ID)"
    )
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional service-specific metadata"
    )

    # Who pays for this usage: 'platform' or 'byok'. See usage_quota.constants.
    billing_origin: models.CharField = models.CharField(
        max_length=16,
        choices=BILLING_ORIGIN_CHOICES,
        default='platform',
        db_index=True,
        help_text=(
            "Who pays for this usage: 'platform' (Sterna) or 'byok' "
            "(user-uploaded OpenRouter key)."
        ),
    )

    # Timestamp
    timestamp: models.DateTimeField = models.DateTimeField(
        auto_now_add=True, db_index=True
    )

    class Meta:
        verbose_name = "Usage Log"
        verbose_name_plural = "Usage Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['user', 'service', 'timestamp']),
            models.Index(fields=['user', 'feature', 'timestamp']),
            models.Index(fields=['session_id', 'timestamp']),
            models.Index(
                fields=['user', 'billing_origin', 'timestamp'],
                name='usage_user_billorg_ts_idx',
            ),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.service} - ${self.cost_usd} ({self.timestamp.date()})"


class StripeWebhookEvent(models.Model):
    """Idempotency + audit log for Stripe webhook deliveries.

    The webhook view writes one row per delivered ``event.id`` BEFORE
    dispatching to the handler. The handler updates ``processed_status``
    after running. A Stripe retry of the same ``event.id`` is a noop iff
    the prior row's status is ``ok``; on ``error`` the handler is
    re-run.
    """

    PROCESSED_STATUS_OK = 'ok'
    PROCESSED_STATUS_ERROR = 'error'
    PROCESSED_STATUS_SKIPPED = 'skipped'
    PROCESSED_STATUS_PROCESSING = 'processing'

    # A 'processing' claim older than this is considered abandoned
    # (worker crashed between claim and terminal write) and becomes
    # claimable again by the CAS in the webhook view / admin replay.
    PROCESSING_CLAIM_TTL = timedelta(minutes=5)
    PROCESSED_STATUS_CHOICES = [
        (PROCESSED_STATUS_OK, 'OK'),
        (PROCESSED_STATUS_ERROR, 'Error'),
        (PROCESSED_STATUS_SKIPPED, 'Skipped'),
        (PROCESSED_STATUS_PROCESSING, 'Processing'),
    ]

    # event.id from Stripe ("evt_…"). PK so duplicates collide at DB
    # level — race-safe against parallel deliveries even if our
    # application-level check misses.
    id: models.CharField = models.CharField(max_length=255, primary_key=True)
    type: models.CharField = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField()
    processed_at: models.DateTimeField = models.DateTimeField(null=True, blank=True)
    claimed_at: models.DateTimeField = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "When the current 'processing' claim was taken. Claims "
            "older than PROCESSING_CLAIM_TTL are treated as abandoned "
            "and become claimable again."
        ),
    )
    processed_status: models.CharField = models.CharField(
        max_length=16,
        choices=PROCESSED_STATUS_CHOICES,
        null=True, blank=True,
        db_index=True,
    )
    error_message: models.TextField = models.TextField(null=True, blank=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stripe Webhook Event"
        verbose_name_plural = "Stripe Webhook Events"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['type', 'processed_status'],
                         name='swh_type_status_idx'),
            models.Index(fields=['processed_at'],
                         name='swh_processed_at_idx'),
        ]

    def __str__(self):
        return f"{self.type} {self.id} [{self.processed_status or 'pending'}]"
