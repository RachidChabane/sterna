from django.contrib import admin
from .models import Conversation, Chat, Message


class ChatInline(admin.TabularInline):
    model = Chat
    extra = 0
    readonly_fields = ['id', 'created_at']
    fields = ['id', 'model_id', 'model_provider', 'is_disabled', 'is_hidden', 'created_at']
    ordering = ['created_at']


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ['id', 'sequence', 'created_at']
    fields = ['sequence', 'role', 'content', 'model_id', 'created_at']
    ordering = ['sequence']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'user', 'chat_count', 'message_count', 'is_archived', 'is_pinned', 'updated_at']
    list_filter = ['is_archived', 'is_pinned', 'created_at']
    search_fields = ['name', 'user__email', 'id']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_message_at', 'message_count', 'chat_count']
    ordering = ['-updated_at']
    inlines = [ChatInline]

    fieldsets = (
        (None, {
            'fields': ('id', 'user', 'name', 'is_custom_name')
        }),
        ('Status', {
            'fields': ('is_archived', 'is_pinned', 'consigliere_session_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_message_at'),
            'classes': ('collapse',)
        }),
    )

    def message_count(self, obj):
        return obj.message_count
    message_count.short_description = 'Messages'

    def chat_count(self, obj):
        return obj.chat_count
    chat_count.short_description = 'Chats'


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'model_id', 'model_provider', 'message_count', 'is_disabled', 'created_at']
    list_filter = ['model_provider', 'is_disabled', 'is_hidden', 'created_at']
    search_fields = ['conversation__name', 'conversation__id', 'model_id']
    readonly_fields = ['id', 'created_at', 'updated_at', 'message_count']
    ordering = ['-created_at']
    inlines = [MessageInline]

    fieldsets = (
        (None, {
            'fields': ('id', 'conversation')
        }),
        ('Model Configuration', {
            'fields': ('model_id', 'model_provider', 'parameters'),
        }),
        ('Status', {
            'fields': ('is_disabled', 'is_hidden')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def message_count(self, obj):
        return obj.message_count
    message_count.short_description = 'Messages'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'chat', 'role', 'sequence', 'model_id', 'created_at']
    list_filter = ['role', 'model_provider', 'created_at']
    search_fields = ['chat__conversation__name', 'chat__conversation__id', 'chat__id']
    readonly_fields = ['id', 'created_at']
    ordering = ['chat', 'sequence']

    fieldsets = (
        (None, {
            'fields': ('id', 'chat', 'role', 'sequence')
        }),
        ('Content', {
            'fields': ('content', 'tool_calls', 'tool_call_id', 'steps', 'metadata')
        }),
        ('Model Info', {
            'fields': ('model_id', 'model_provider', 'prompt_tokens', 'completion_tokens', 'cost'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
