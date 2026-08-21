"""
Centralized configuration for Knowledge Base feature.
All settings are pulled from Django settings with sensible defaults.
"""

from dataclasses import dataclass
from django.conf import settings


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    """Centralized configuration for Knowledge Base feature."""

    # Embedding settings (from Django settings with defaults)
    # Using text-embedding-3-large for highest quality embeddings
    # Keeping 1536 dimensions for compatibility (large model supports dimension reduction)
    embedding_model: str = getattr(
        settings, 'KNOWLEDGE_BASE_EMBEDDING_MODEL',
        'openai/text-embedding-3-large'
    )
    embedding_dimensions: int = getattr(
        settings, 'KNOWLEDGE_BASE_EMBEDDING_DIMENSIONS',
        1536  # text-embedding-3-large with dimension reduction (HNSW limit: 2000)
    )
    embedding_api_url: str = getattr(
        settings, 'KNOWLEDGE_BASE_EMBEDDING_API_URL',
        'https://openrouter.ai/api/v1/embeddings'
    )

    # Chunking settings
    chunk_size: int = getattr(settings, 'KNOWLEDGE_BASE_CHUNK_SIZE', 500)
    chunk_overlap: int = getattr(settings, 'KNOWLEDGE_BASE_CHUNK_OVERLAP', 50)

    # Storage settings
    inline_storage_threshold_bytes: int = getattr(
        settings, 'KNOWLEDGE_BASE_INLINE_THRESHOLD',
        256 * 1024  # 256 KB
    )
    r2_bucket: str = getattr(
        settings, 'KNOWLEDGE_BASE_R2_BUCKET',
        'sternaway-knowledge'
    )

    # Default user limits (can be overridden by subscription plan)
    default_storage_limit_mb: int = getattr(
        settings, 'KNOWLEDGE_BASE_DEFAULT_STORAGE_MB',
        100
    )
    # Cosine scores from text-embedding-3-large rarely exceed ~0.6 even for
    # strong matches, so a 0.7 floor silently filters out every result.
    default_similarity_threshold: float = getattr(
        settings, 'KNOWLEDGE_BASE_DEFAULT_SIMILARITY_THRESHOLD',
        0.4
    )
    default_max_chunks_per_query: int = getattr(
        settings, 'KNOWLEDGE_BASE_DEFAULT_MAX_CHUNKS',
        5
    )

    # Token estimation
    tokens_per_word_estimate: float = getattr(
        settings, 'KNOWLEDGE_BASE_TOKENS_PER_WORD',
        1.3
    )

    # Context injection
    default_max_context_tokens: int = getattr(
        settings, 'KNOWLEDGE_BASE_MAX_CONTEXT_TOKENS',
        2000
    )


# Singleton instance
config = KnowledgeBaseConfig()
