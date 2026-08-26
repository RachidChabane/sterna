"""Django admin configuration for Usage & Quota models."""

import json

from django.contrib import admin, messages
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    ServicePricing,
    StripeWebhookEvent,
    SubscriptionPlan,
    UsageLog,
    UserSubscription,
)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """Admin for subscription plans."""

    list_display = [
        'name',
        'display_name',
        'weekly_limit_display',
        'session_limit_display',
        'is_active',
        'is_default',
    ]
    list_filter = ['is_active', 'is_default']
    search_fields = ['name', 'display_name']
    readonly_fields = ['id', 'created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('name', 'display_name', 'description')
        }),
        ('Global Limits', {
            'fields': ('weekly_limit_usd', 'session_limit_usd')
        }),
        ('Per-Feature $ Budgets (advisory until task 10)', {
            'fields': (
                'chat_weekly_limit_usd',
                'voice_room_weekly_limit_usd',
                'code_session_weekly_limit_usd',
            ),
            'classes': ('collapse',)
        }),
        ('Per-Feature Count Limits', {
            'fields': (
                'voice_room_sessions_weekly_limit',
                'voice_room_minutes_per_session_limit',
                'code_session_weekly_limit',
                'image_gen_weekly_limit',
                'video_gen_seconds_weekly_limit',
                'mcp_invocations_weekly_limit',
                'kb_storage_mb_limit',
                'kb_docs_limit',
            ),
        }),
        ('Stripe Linkage (task 11)', {
            'fields': ('stripe_price_id_monthly', 'stripe_price_id_yearly'),
            'classes': ('collapse',)
        }),
        ('Feature Access', {
            'fields': ('features',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_default')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Weekly Limit')
    def weekly_limit_display(self, obj):
        return f"${obj.weekly_limit_usd}"

    @admin.display(description='Session Limit')
    def session_limit_display(self, obj):
        return f"${obj.session_limit_usd}"


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    """Admin for user subscriptions."""

    list_display = [
        'user_email',
        'plan',
        'effective_weekly_limit_display',
        'effective_session_limit_display',
        'is_active',
        'created_at',
    ]
    list_filter = ['plan', 'is_active']
    search_fields = ['user__email', 'user__full_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['user']

    fieldsets = (
        (None, {
            'fields': ('user', 'plan')
        }),
        ('Custom Overrides', {
            'fields': ('custom_weekly_limit_usd', 'custom_session_limit_usd'),
            'classes': ('collapse',)
        }),
        ('Stripe Linkage (task 11)', {
            'fields': ('stripe_subscription_id',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='User')
    def user_email(self, obj):
        return obj.user.email

    @admin.display(description='Weekly Limit')
    def effective_weekly_limit_display(self, obj):
        limit = obj.effective_weekly_limit
        if obj.custom_weekly_limit_usd:
            return format_html('<b>${}</b> (custom)', limit)
        return f"${limit}"

    @admin.display(description='Session Limit')
    def effective_session_limit_display(self, obj):
        limit = obj.effective_session_limit
        if obj.custom_session_limit_usd:
            return format_html('<b>${}</b> (custom)', limit)
        return f"${limit}"


@admin.register(ServicePricing)
class ServicePricingAdmin(admin.ModelAdmin):
    """Admin for service pricing configuration."""

    list_display = [
        'service',
        'model_id',
        'pricing_display',
        'effective_from',
        'effective_until',
        'is_active',
    ]
    list_filter = ['service', 'is_active']
    search_fields = ['model_id']
    readonly_fields = ['id', 'created_at']
    ordering = ['-effective_from']

    fieldsets = (
        (None, {
            'fields': ('service', 'model_id')
        }),
        ('Token-based Pricing (LLM)', {
            'fields': ('price_per_1m_input_tokens', 'price_per_1m_output_tokens'),
            'classes': ('collapse',)
        }),
        ('Character-based Pricing (TTS)', {
            'fields': ('price_per_1k_chars',),
            'classes': ('collapse',)
        }),
        ('Time-based Pricing (STT)', {
            'fields': ('price_per_minute',),
            'classes': ('collapse',)
        }),
        ('Request-based Pricing (Search)', {
            'fields': ('price_per_request',),
            'classes': ('collapse',)
        }),
        ('Validity', {
            'fields': ('effective_from', 'effective_until', 'is_active')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Pricing')
    def pricing_display(self, obj):
        """Display the relevant pricing for this service type."""
        if obj.price_per_1m_input_tokens:
            return f"${obj.price_per_1m_input_tokens}/1M in, ${obj.price_per_1m_output_tokens}/1M out"
        if obj.price_per_1k_chars:
            return f"${obj.price_per_1k_chars}/1K chars"
        if obj.price_per_minute:
            return f"${obj.price_per_minute}/min"
        if obj.price_per_request:
            return f"${obj.price_per_request}/request"
        return "-"


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    """Admin for usage logs (read-only)."""

    list_display = [
        'timestamp',
        'user_email',
        'service',
        'feature',
        'cost_display',
        'usage_display',
    ]
    list_filter = ['service', 'feature', 'timestamp']
    search_fields = ['user__email', 'session_id', 'model_id']
    readonly_fields = [
        'id', 'user', 'service', 'feature', 'session_id',
        'model_id', 'prompt_tokens', 'completion_tokens', 'total_tokens',
        'character_count', 'audio_seconds', 'request_count',
        'cost_usd', 'request_id', 'extra_data', 'timestamp'
    ]
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='User')
    def user_email(self, obj):
        return obj.user.email

    @admin.display(description='Cost (USD)')
    def cost_display(self, obj):
        return f"${obj.cost_usd:.6f}"

    @admin.display(description='Usage')
    def usage_display(self, obj):
        """Display relevant usage metric based on service type."""
        if obj.total_tokens:
            return f"{obj.total_tokens} tokens"
        if obj.character_count:
            return f"{obj.character_count} chars"
        if obj.audio_seconds:
            return f"{obj.audio_seconds:.1f}s audio"
        if obj.request_count > 1:
            return f"{obj.request_count} requests"
        return "1 request"


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    """Admin for the Stripe webhook event dedup/audit log (task 13)."""

    list_display = [
        'created_at', 'type', 'id', 'processed_status_display',
        'processed_at',
    ]
    list_filter = ['processed_status', 'type', 'created_at']
    search_fields = ['id', 'type', 'error_message']
    readonly_fields = [
        'id', 'type', 'payload_pretty', 'processed_at',
        'processed_status', 'error_message', 'created_at',
    ]
    actions = ['replay_events']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Read-only fields above prevent mutation via the form; we keep
        # change permission so the Replay action remains usable.
        return True

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Status')
    def processed_status_display(self, obj):
        color = {
            'ok': 'green', 'error': 'red',
            'skipped': 'gray', 'processing': 'blue',
        }.get(obj.processed_status, 'orange')
        label = obj.processed_status or 'pending'
        return format_html('<b style="color:{}">{}</b>', color, label)

    @admin.display(description='Payload')
    def payload_pretty(self, obj):
        return format_html(
            '<pre style="white-space:pre-wrap;">{}</pre>',
            json.dumps(obj.payload, indent=2, default=str),
        )

    @admin.action(description='Replay selected events (re-dispatch handler)')
    def replay_events(self, request, queryset):
        from .services.stripe_webhooks import _IgnorableEvent, dispatch

        ok = err = skipped = in_flight = 0
        for row in queryset:
            # CAS-claim the row before dispatching, mirroring the view's
            # race-safety pattern. Admin replay must NOT race against a
            # concurrent Stripe retry that holds a FRESH 'processing'
            # claim, else both dispatchers run the handler in parallel
            # and double-send emails. We only exclude fresh 'processing'
            # (not 'ok' — admin's intent is explicit re-dispatch even of
            # successes for forensic re-runs). A claim older than
            # PROCESSING_CLAIM_TTL is abandoned (worker crashed) and is
            # claimable, mirroring the webhook view's stale-claim CAS.
            stale_cutoff = (
                timezone.now() - StripeWebhookEvent.PROCESSING_CLAIM_TTL
            )
            claimed = (
                StripeWebhookEvent.objects.filter(id=row.id)
                .exclude(
                    Q(processed_status=(
                        StripeWebhookEvent.PROCESSED_STATUS_PROCESSING
                    ))
                    & (Q(claimed_at__isnull=True)
                       | Q(claimed_at__gt=stale_cutoff)),
                )
                .update(
                    processed_status=(
                        StripeWebhookEvent.PROCESSED_STATUS_PROCESSING
                    ),
                    claimed_at=timezone.now(),
                    error_message=None,
                    processed_at=None,
                )
            )
            if claimed == 0:
                in_flight += 1
                continue
            try:
                result = dispatch(row.payload)
                row.processed_status = (
                    StripeWebhookEvent.PROCESSED_STATUS_OK
                    if result == 'ok'
                    else StripeWebhookEvent.PROCESSED_STATUS_SKIPPED
                )
                row.error_message = None
                row.processed_at = timezone.now()
                row.save(update_fields=[
                    'processed_status', 'error_message', 'processed_at',
                ])
                if result == 'ok':
                    ok += 1
                else:
                    skipped += 1
            except _IgnorableEvent as exc:
                row.processed_status = (
                    StripeWebhookEvent.PROCESSED_STATUS_SKIPPED
                )
                row.error_message = str(exc)[:5000]
                row.processed_at = timezone.now()
                row.save(update_fields=[
                    'processed_status', 'error_message', 'processed_at',
                ])
                skipped += 1
            except Exception as exc:
                row.processed_status = (
                    StripeWebhookEvent.PROCESSED_STATUS_ERROR
                )
                row.error_message = str(exc)[:5000]
                row.processed_at = timezone.now()
                row.save(update_fields=[
                    'processed_status', 'error_message', 'processed_at',
                ])
                err += 1
        self.message_user(
            request,
            f"Replayed: {ok} ok, {err} error, {skipped} skipped, "
            f"{in_flight} in-flight (skipped).",
            level=messages.WARNING if err else messages.SUCCESS,
        )
