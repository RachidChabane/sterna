"""Django admin configuration for Voice Rooms."""

from django.contrib import admin
from .models import VoiceRoom, VoiceRoomAgent, VoiceRoomSession, VoiceRoomMessage


class VoiceRoomAgentInline(admin.TabularInline):
    """Inline admin for agents within a room."""

    model = VoiceRoomAgent
    extra = 0
    fields = ["display_name", "model_id", "voice_name", "order", "is_active"]


@admin.register(VoiceRoom)
class VoiceRoomAdmin(admin.ModelAdmin):
    """Admin for VoiceRoom model."""

    list_display = ["name", "user", "language", "is_active", "created_at", "updated_at"]
    list_filter = ["is_active", "language", "created_at"]
    search_fields = ["name", "user__email", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [VoiceRoomAgentInline]


@admin.register(VoiceRoomAgent)
class VoiceRoomAgentAdmin(admin.ModelAdmin):
    """Admin for VoiceRoomAgent model."""

    list_display = ["display_name", "room", "model_id", "voice_name", "order", "is_active"]
    list_filter = ["is_active", "model_id"]
    search_fields = ["display_name", "room__name", "model_id"]
    readonly_fields = ["id", "created_at", "updated_at"]


class VoiceRoomMessageInline(admin.TabularInline):
    """Inline admin for messages within a session."""

    model = VoiceRoomMessage
    extra = 0
    fields = ["role", "content", "agent", "audio_duration_ms", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(VoiceRoomSession)
class VoiceRoomSessionAdmin(admin.ModelAdmin):
    """Admin for VoiceRoomSession model."""

    list_display = [
        "id", "room", "status", "detected_language",
        "total_duration_ms", "started_at", "ended_at"
    ]
    list_filter = ["status", "detected_language", "started_at"]
    search_fields = ["room__name", "room__user__email"]
    readonly_fields = ["id", "started_at"]
    inlines = [VoiceRoomMessageInline]


@admin.register(VoiceRoomMessage)
class VoiceRoomMessageAdmin(admin.ModelAdmin):
    """Admin for VoiceRoomMessage model."""

    list_display = [
        "id", "session", "role", "agent", "audio_duration_ms", "created_at"
    ]
    list_filter = ["role", "created_at"]
    search_fields = ["content", "session__room__name"]
    readonly_fields = ["id", "created_at"]
