"""
Admin configuration for Knowledge Base models.
"""

from django.contrib import admin
from .models import (
    KnowledgeBaseSettings,
    KnowledgeDocument,
    KnowledgeChunk,
    KnowledgeQueryLog,
)


@admin.register(KnowledgeBaseSettings)
class KnowledgeBaseSettingsAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'is_enabled', 'total_documents',
        'total_chunks', 'storage_used_display', 'created_at'
    ]
    list_filter = ['is_enabled', 'created_at']
    search_fields = ['user__email']
    readonly_fields = [
        'total_documents', 'total_chunks',
        'total_storage_bytes', 'created_at', 'updated_at'
    ]

    @admin.display(description='Storage Used')
    def storage_used_display(self, obj):
        return f"{obj.storage_used_mb:.2f} MB"


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'filename', 'user', 'document_type', 'status',
        'file_size_display', 'chunk_count', 'uploaded_at'
    ]
    list_filter = ['status', 'document_type', 'uploaded_at']
    search_fields = ['filename', 'user__email']
    readonly_fields = [
        'id', 'content_hash', 'extracted_text',
        'chunk_count', 'uploaded_at', 'processed_at'
    ]
    raw_id_fields = ['user']

    @admin.display(description='File Size')
    def file_size_display(self, obj):
        if obj.file_size_bytes < 1024:
            return f"{obj.file_size_bytes} B"
        elif obj.file_size_bytes < 1024 * 1024:
            return f"{obj.file_size_bytes / 1024:.1f} KB"
        else:
            return f"{obj.file_size_bytes / (1024 * 1024):.1f} MB"


@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'document', 'chunk_index',
        'token_count', 'page_number', 'created_at'
    ]
    list_filter = ['embedding_model', 'created_at']
    search_fields = ['document__filename', 'content']
    readonly_fields = ['id', 'embedding', 'created_at']
    raw_id_fields = ['user', 'document']


@admin.register(KnowledgeQueryLog)
class KnowledgeQueryLogAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'invocation_type', 'chunks_returned',
        'top_similarity_score', 'latency_ms', 'created_at'
    ]
    list_filter = ['invocation_type', 'created_at']
    search_fields = ['user__email', 'query_text']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['user']
