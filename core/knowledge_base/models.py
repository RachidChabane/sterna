"""
Knowledge Base models for document storage, chunking, and vector search.
"""

import uuid
from typing import TYPE_CHECKING

from django.db import models
from pgvector.django import VectorField, HnswIndex  # type: ignore[import-untyped]

from authentication.models import User
from .config import config

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class KnowledgeBaseSettings(models.Model):
    """Per-user knowledge base configuration."""
    user: "models.OneToOneField[User, User]" = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='knowledge_base_settings'
    )
    is_enabled: models.BooleanField = models.BooleanField(default=True)

    # User-tunable settings (defaults from config)
    similarity_threshold: models.FloatField = models.FloatField(
        default=config.default_similarity_threshold
    )
    max_chunks_per_query: models.PositiveIntegerField = models.PositiveIntegerField(
        default=config.default_max_chunks_per_query
    )
    storage_limit_mb: models.PositiveIntegerField = models.PositiveIntegerField(
        default=config.default_storage_limit_mb
    )

    # Stats (denormalized for performance)
    total_documents: models.PositiveIntegerField = models.PositiveIntegerField(default=0)
    total_chunks: models.PositiveIntegerField = models.PositiveIntegerField(default=0)
    total_storage_bytes: models.BigIntegerField = models.BigIntegerField(default=0)

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Knowledge Base Settings"
        verbose_name_plural = "Knowledge Base Settings"

    def __str__(self):
        return f"KB Settings for {self.user.email}"

    def update_stats(self, documents_delta=0, chunks_delta=0, storage_delta=0):
        """Atomic stats update to avoid race conditions."""
        from django.db.models import F
        KnowledgeBaseSettings.objects.filter(pk=self.pk).update(
            total_documents=F('total_documents') + documents_delta,
            total_chunks=F('total_chunks') + chunks_delta,
            total_storage_bytes=F('total_storage_bytes') + storage_delta,
        )
        self.refresh_from_db()

    @property
    def storage_used_mb(self):
        return round(self.total_storage_bytes / (1024 * 1024), 2)

    @property
    def storage_percentage(self):
        if self.storage_limit_mb == 0:
            return 0
        return round((self.storage_used_mb / self.storage_limit_mb) * 100, 1)


class DocumentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    INDEXING = 'indexing', 'Indexing'
    READY = 'ready', 'Ready'
    FAILED = 'failed', 'Failed'


class DocumentType(models.TextChoices):
    PDF = 'pdf', 'PDF'
    DOCX = 'docx', 'Word Document'
    TXT = 'txt', 'Plain Text'
    MD = 'md', 'Markdown'
    CSV = 'csv', 'CSV'
    HTML = 'html', 'HTML'
    JSON = 'json', 'JSON'


class StorageType(models.TextChoices):
    INLINE = 'inline', 'Inline'
    R2 = 'r2', 'R2'


class KnowledgeDocument(models.Model):
    """Represents an uploaded document in the knowledge base."""
    if TYPE_CHECKING:
        chunks: "RelatedManager[KnowledgeChunk]"

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user: "models.ForeignKey[User, User]" = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='knowledge_documents'
    )

    # Document metadata
    filename: models.CharField = models.CharField(max_length=500)
    original_filename: models.CharField = models.CharField(max_length=500)
    document_type: models.CharField = models.CharField(max_length=20, choices=DocumentType.choices)
    mime_type: models.CharField = models.CharField(max_length=100)
    file_size_bytes: models.BigIntegerField = models.BigIntegerField()

    # Content storage (tiered like workspaces)
    storage_type: models.CharField = models.CharField(
        max_length=20,
        choices=StorageType.choices,
        default=StorageType.INLINE
    )
    content: models.BinaryField = models.BinaryField(blank=True, null=True)
    r2_bucket: models.CharField = models.CharField(max_length=255, blank=True)
    r2_key: models.CharField = models.CharField(max_length=500, blank=True)

    # Processing metadata
    status: models.CharField = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.PENDING
    )
    error_message: models.TextField = models.TextField(blank=True)

    # Parsed content
    extracted_text: models.TextField = models.TextField(blank=True)
    page_count: models.PositiveIntegerField = models.PositiveIntegerField(null=True)
    word_count: models.PositiveIntegerField = models.PositiveIntegerField(null=True)
    chunk_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0)

    # Duplicate detection
    content_hash: models.CharField = models.CharField(max_length=64, db_index=True)

    # Timestamps
    uploaded_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    processed_at: models.DateTimeField = models.DateTimeField(null=True)
    last_queried_at: models.DateTimeField = models.DateTimeField(null=True)

    # Tags for organization
    tags: models.JSONField = models.JSONField(default=list)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'content_hash']),
        ]
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.filename} ({self.status})"


class KnowledgeChunk(models.Model):
    """Individual text chunk with embedding vector."""
    if TYPE_CHECKING:
        document_id: uuid.UUID

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document: "models.ForeignKey[KnowledgeDocument, KnowledgeDocument]" = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name='chunks'
    )
    user: "models.ForeignKey[User, User]" = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='knowledge_chunks'
    )

    # Chunk content
    content: models.TextField = models.TextField()
    chunk_index: models.PositiveIntegerField = models.PositiveIntegerField()

    # Position in source document
    start_char: models.PositiveIntegerField = models.PositiveIntegerField(null=True)
    end_char: models.PositiveIntegerField = models.PositiveIntegerField(null=True)
    page_number: models.PositiveIntegerField = models.PositiveIntegerField(null=True)

    # Embedding vector (dimensions from config)
    embedding = VectorField(dimensions=config.embedding_dimensions, null=True)
    embedding_model: models.CharField = models.CharField(max_length=100)

    # Token count for cost estimation
    token_count: models.PositiveIntegerField = models.PositiveIntegerField(default=0)

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            HnswIndex(
                name='chunk_embedding_hnsw_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
            models.Index(fields=['user', 'document']),
            models.Index(fields=['document', 'chunk_index']),
        ]
        ordering = ['document', 'chunk_index']

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.filename}"


class KnowledgeQueryLog(models.Model):
    """Logs knowledge base queries for analytics and billing."""
    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user: "models.ForeignKey[User, User]" = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='knowledge_query_logs'
    )

    # Query details
    query_text: models.TextField = models.TextField()
    query_embedding_model: models.CharField = models.CharField(max_length=100)

    # Results
    chunks_searched: models.PositiveIntegerField = models.PositiveIntegerField()
    chunks_returned: models.PositiveIntegerField = models.PositiveIntegerField()
    top_similarity_score: models.FloatField = models.FloatField(null=True)

    # Source tracking
    conversation_id: models.UUIDField = models.UUIDField(null=True)
    chat_id: models.UUIDField = models.UUIDField(null=True)
    invocation_type: models.CharField = models.CharField(
        max_length=20,
        choices=[
            ('auto', 'Automatic'),
            ('explicit', 'Explicit (@kb)'),
            ('ui', 'UI Search'),
        ]
    )

    # Cost tracking
    embedding_cost_usd: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0
    )

    # Performance
    latency_ms: models.PositiveIntegerField = models.PositiveIntegerField()

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'invocation_type', '-created_at']),
        ]

    def __str__(self):
        return f"Query by {self.user.email} at {self.created_at}"
