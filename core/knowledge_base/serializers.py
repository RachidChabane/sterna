"""
DRF serializers for Knowledge Base API.
"""

from rest_framework import serializers
from .models import (
    KnowledgeBaseSettings,
    KnowledgeDocument,
    KnowledgeChunk,
    KnowledgeQueryLog,
)


class KnowledgeBaseSettingsSerializer(serializers.ModelSerializer):
    """Serializer for user's knowledge base settings."""
    storage_used_mb = serializers.SerializerMethodField()
    storage_percentage = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeBaseSettings
        fields = [
            'is_enabled', 'similarity_threshold',
            'max_chunks_per_query', 'storage_limit_mb',
            'total_documents', 'total_chunks', 'total_storage_bytes',
            'storage_used_mb', 'storage_percentage',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'total_documents', 'total_chunks', 'total_storage_bytes',
            'storage_used_mb', 'storage_percentage',
            'created_at', 'updated_at',
        ]

    def get_storage_used_mb(self, obj):
        return round(obj.total_storage_bytes / (1024 * 1024), 2)

    def get_storage_percentage(self, obj):
        if obj.storage_limit_mb == 0:
            return 0
        used_mb = obj.total_storage_bytes / (1024 * 1024)
        return round((used_mb / obj.storage_limit_mb) * 100, 1)


class KnowledgeDocumentListSerializer(serializers.ModelSerializer):
    """Serializer for document list view."""
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeDocument
        fields = [
            'id', 'filename', 'original_filename', 'document_type',
            'file_size_bytes', 'file_size_display', 'status',
            'chunk_count', 'page_count', 'word_count',
            'tags', 'uploaded_at', 'processed_at', 'last_queried_at',
        ]

    def get_file_size_display(self, obj):
        if obj.file_size_bytes < 1024:
            return f"{obj.file_size_bytes} B"
        elif obj.file_size_bytes < 1024 * 1024:
            return f"{obj.file_size_bytes / 1024:.1f} KB"
        else:
            return f"{obj.file_size_bytes / (1024 * 1024):.1f} MB"


class KnowledgeDocumentDetailSerializer(KnowledgeDocumentListSerializer):
    """Serializer for document detail view with chunks preview."""
    chunks_preview = serializers.SerializerMethodField()

    class Meta(KnowledgeDocumentListSerializer.Meta):
        fields = KnowledgeDocumentListSerializer.Meta.fields + [
            'error_message', 'chunks_preview',
        ]

    def get_chunks_preview(self, obj):
        chunks = obj.chunks.all()[:5]
        return [
            {
                'id': str(c.id),
                'content': c.content[:200] + '...' if len(c.content) > 200 else c.content,
                'chunk_index': c.chunk_index,
                'page_number': c.page_number,
            }
            for c in chunks
        ]


class KnowledgeDocumentUploadSerializer(serializers.Serializer):
    """Serializer for document upload."""
    file = serializers.FileField()
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list
    )


class KnowledgeChunkSerializer(serializers.ModelSerializer):
    """Serializer for individual chunks."""
    document_filename = serializers.CharField(
        source='document.filename',
        read_only=True
    )

    class Meta:
        model = KnowledgeChunk
        fields = [
            'id', 'document', 'document_filename',
            'content', 'chunk_index', 'page_number',
            'token_count', 'created_at',
        ]


class KnowledgeSearchResultSerializer(serializers.Serializer):
    """Serializer for search results with similarity scores."""
    chunk_id = serializers.UUIDField()
    document_id = serializers.UUIDField()
    document_filename = serializers.CharField()
    document_type = serializers.CharField()
    content = serializers.CharField()
    chunk_index = serializers.IntegerField()
    page_number = serializers.IntegerField(allow_null=True)
    similarity_score = serializers.FloatField()
    token_count = serializers.IntegerField()


class KnowledgeQueryRequestSerializer(serializers.Serializer):
    """Serializer for search query requests."""
    query = serializers.CharField(max_length=2000)
    max_results = serializers.IntegerField(
        min_value=1,
        max_value=20,
        default=5
    )
    similarity_threshold = serializers.FloatField(
        min_value=0.0,
        max_value=1.0,
        required=False
    )
    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Filter to specific documents"
    )


class KnowledgeQueryLogSerializer(serializers.ModelSerializer):
    """Serializer for query logs."""
    class Meta:
        model = KnowledgeQueryLog
        fields = [
            'id', 'query_text', 'chunks_searched', 'chunks_returned',
            'top_similarity_score', 'invocation_type',
            'latency_ms', 'embedding_cost_usd', 'created_at',
        ]
