from django.contrib import admin

from llm.models import (
    RoutingConversationScore,
    RoutingLog,
    RoutingPool,
)


@admin.register(RoutingPool)
class RoutingPoolAdmin(admin.ModelAdmin):
    list_display = ['model', 'cost_tier', 'min_complexity_score', 'max_complexity_score', 'priority', 'is_active']
    list_filter = ['is_active', 'cost_tier']
    list_editable = ['is_active', 'cost_tier', 'min_complexity_score', 'max_complexity_score', 'priority']


@admin.register(RoutingConversationScore)
class RoutingConversationScoreAdmin(admin.ModelAdmin):
    list_display = ['conversation_id', 'user', 'current_score', 'max_score', 'turn_count', 'consecutive_simple_turns', 'last_model_id', 'updated_at']
    list_filter = ['last_model_id']
    search_fields = ['conversation_id']
    readonly_fields = ['updated_at']


@admin.register(RoutingLog)
class RoutingLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'tier_used', 'final_score', 'resolved_model_id', 'prompt_length', 'is_reroute']
    list_filter = ['tier_used', 'resolved_model_id', 'is_reroute', 'has_images', 'has_code']
    search_fields = ['conversation_id', 'resolved_model_id']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
