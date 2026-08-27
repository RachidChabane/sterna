"""
Query service for searching the knowledge base.
"""

import time
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from ..models import KnowledgeQueryLog

from django.utils import timezone
from pgvector.django import CosineDistance  # type: ignore[import-untyped]

from ..config import config

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Search result from knowledge base query."""
    chunk_id: str
    document_id: str
    document_filename: str
    document_type: str  # pdf, md, txt, etc.
    content: str
    chunk_index: int
    page_number: Optional[int]
    similarity_score: float
    token_count: int


class KnowledgeQueryService:
    """Handles knowledge base queries with vector similarity search."""

    def __init__(
        self,
        embedding_service=None,
        pricing_service=None,
    ):
        # Lazy imports to avoid circular dependencies
        self._embedding_service = embedding_service
        self._pricing_service = pricing_service

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from .embedding import EmbeddingService
            # Note: this lazy default path has no user context; the caller
            # should inject a user-bound EmbeddingService for BYOK routing.
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    @property
    def pricing_service(self):
        if self._pricing_service is None:
            from .pricing import KnowledgePricingService
            self._pricing_service = KnowledgePricingService()
        return self._pricing_service

    def search(
        self,
        user,
        query: str,
        max_results: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        document_ids: Optional[List[str]] = None,
        conversation_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        invocation_type: str = 'auto',
    ) -> Tuple[List[SearchResult], 'KnowledgeQueryLog']:
        """
        Search knowledge base for relevant chunks.

        Args:
            user: User performing the search
            query: Search query text
            max_results: Maximum number of results to return
            similarity_threshold: Minimum similarity score
            document_ids: Optional filter to specific documents
            conversation_id: ID of the conversation (for logging)
            chat_id: ID of the chat (for logging)
            invocation_type: How the search was triggered ('auto', 'explicit', 'ui')

        Returns:
            Tuple of (search results, query log)
        """
        from ..models import KnowledgeChunk, KnowledgeQueryLog

        # Tier gate: flag check (knowledge_base) before doing any work.
        from decimal import Decimal as _D

        from usage_quota.billing.service import get_billing_service
        from usage_quota.models import FeatureType as _FT, ServiceType as _ST
        get_billing_service().check_quota(
            user=user,
            service=_ST.KNOWLEDGE_BASE_QUERY,
            estimated_cost=_D('0'),
            feature=_FT.KNOWLEDGE_BASE,
            feature_name='kb_query',
        )

        start_time = time.time()

        # Get user settings with defaults from config
        settings = self._get_user_settings(user)

        if max_results is None:
            max_results = settings.max_chunks_per_query
        if similarity_threshold is None:
            similarity_threshold = settings.similarity_threshold

        # Rebuild embedding_service with user binding if the caller didn't
        # inject a user-aware instance — this is what threads BYOK origin
        # through KB queries called from auth-less code paths.
        if (
            self._embedding_service is None
            or getattr(self._embedding_service, '_user', None) is None
        ):
            from .embedding import EmbeddingService
            self._embedding_service = EmbeddingService(user=user)

        # Generate query embedding
        query_embedding = self.embedding_service.generate_embedding(query)

        # Vector similarity search
        queryset = KnowledgeChunk.objects.filter(
            user=user,
            embedding__isnull=False
        )

        if document_ids:
            queryset = queryset.filter(document_id__in=document_ids)

        queryset = queryset.annotate(
            distance=CosineDistance('embedding', query_embedding)
        ).filter(
            distance__lte=(1 - similarity_threshold)
        ).order_by('distance')[:max_results]

        # Build results
        results = []
        chunks_searched = KnowledgeChunk.objects.filter(user=user).count()

        for chunk in queryset.select_related('document'):
            # `distance` is added at query time by the .annotate() call above;
            # it is not part of KnowledgeChunk's declared fields.
            similarity = 1 - chunk.distance  # type: ignore[attr-defined]
            results.append(SearchResult(
                chunk_id=str(chunk.id),
                document_id=str(chunk.document_id),
                document_filename=chunk.document.filename,
                document_type=chunk.document.document_type,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                similarity_score=round(similarity, 4),
                token_count=chunk.token_count,
            ))

        # Calculate cost using pricing service (dynamic, not hardcoded)
        query_tokens = self.embedding_service.estimate_tokens(query)
        embedding_cost = self.pricing_service.get_embedding_cost(
            self.embedding_service.model,
            query_tokens
        )

        # Log query
        latency_ms = int((time.time() - start_time) * 1000)
        log = KnowledgeQueryLog.objects.create(
            user=user,
            query_text=query[:500],  # Truncate for storage
            query_embedding_model=self.embedding_service.model,
            chunks_searched=chunks_searched,
            chunks_returned=len(results),
            top_similarity_score=results[0].similarity_score if results else None,
            conversation_id=conversation_id,
            chat_id=chat_id,
            invocation_type=invocation_type,
            embedding_cost_usd=embedding_cost,
            latency_ms=latency_ms,
        )

        # Log usage for billing (deduct from user's quota)
        if embedding_cost > 0:
            self._log_query_usage(user, query_tokens, embedding_cost)

        # Update last_queried_at for returned documents
        if results:
            from ..models import KnowledgeDocument
            doc_ids = {r.document_id for r in results}
            KnowledgeDocument.objects.filter(id__in=doc_ids).update(
                last_queried_at=timezone.now()
            )

        return results, log

    def _get_user_settings(self, user):
        """Get or create user settings."""
        from ..models import KnowledgeBaseSettings
        settings, _ = KnowledgeBaseSettings.objects.get_or_create(user=user)
        return settings

    def _log_query_usage(self, user, token_count: int, cost_usd):
        """Log query usage via BillingService so quota window-start fires."""
        try:
            from usage_quota.billing.service import get_billing_service
            from usage_quota.billing.operations import BillableOperation
            from usage_quota.models import ServiceType, FeatureType

            op = BillableOperation(
                service=ServiceType.KNOWLEDGE_BASE_QUERY,
                feature=FeatureType.KNOWLEDGE_BASE,
                model_id=self.embedding_service.model,
                prompt_tokens=token_count,
                cost_usd=cost_usd,
                extra_data={'operation': 'query_embedding'},
            )
            get_billing_service().record_usage(
                user, op,
                billing_origin=self.embedding_service.billing_origin,
            )
        except Exception as e:
            logger.warning(f"Failed to log query usage: {e}")

    def format_context_for_llm(
        self,
        results: List[SearchResult],
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Format search results as context for LLM injection.

        Args:
            results: List of search results
            max_tokens: Maximum tokens to include in context

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        if max_tokens is None:
            max_tokens = config.default_max_context_tokens

        # task-29 H2: KB chunk content is user-supplied (uploaded docs)
        # or third-party (web-fetched). Wrap each chunk so a malicious
        # PDF/HTML doc can't override the system prompt.
        from conversations.prompt_protection import wrap_untrusted_content

        context_parts = []
        total_tokens = 0

        for result in results:
            chunk_tokens = result.token_count or len(result.content.split())
            if total_tokens + chunk_tokens > max_tokens:
                break

            source_label = f"KB doc: {result.document_filename}"
            if result.page_number:
                source_label += f" (page {result.page_number})"
            source_label += f" — relevance {result.similarity_score:.0%}"

            wrapped = wrap_untrusted_content(
                result.content,
                wrapper_tag="kb_chunk",
                source_label=source_label,
            )
            context_parts.append(wrapped)
            total_tokens += chunk_tokens

        return "\n\n---\n\n".join(context_parts)
