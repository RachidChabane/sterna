"""
Celery tasks for asynchronous document processing.
"""

import logging
from decimal import Decimal
from celery import shared_task  # type: ignore[import-untyped]
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _log_indexing_usage(
    user,
    document_id: str,
    token_count: int,
    cost_usd: Decimal,
    chunk_count: int,
    model_id: str,
    billing_origin: str = 'platform',
):
    """Log document indexing usage via BillingService so quota window-start fires."""
    try:
        from usage_quota.billing.service import get_billing_service
        from usage_quota.billing.operations import BillableOperation
        from usage_quota.models import ServiceType, FeatureType

        op = BillableOperation(
            service=ServiceType.KNOWLEDGE_BASE_EMBEDDING,
            feature=FeatureType.KNOWLEDGE_BASE,
            model_id=model_id,
            prompt_tokens=token_count,
            cost_usd=cost_usd,
            extra_data={
                'operation': 'document_indexing',
                'document_id': document_id,
                'chunk_count': chunk_count,
            },
        )
        get_billing_service().record_usage(user, op, billing_origin=billing_origin)
        logger.info(f"Logged indexing usage: {token_count} tokens, ${cost_usd}")
    except Exception as e:
        logger.warning(f"Failed to log indexing usage: {e}")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def process_document_task(self, document_id: str):
    """
    Process uploaded document:
    1. Extract text
    2. Chunk text
    3. Generate embeddings
    4. Store in vector database
    """
    from .models import KnowledgeDocument, KnowledgeChunk, DocumentStatus
    from .services import DocumentProcessor, EmbeddingService
    from .config import config

    try:
        document = KnowledgeDocument.objects.get(id=document_id)

        # Update status
        document.status = DocumentStatus.PROCESSING
        document.save(update_fields=['status'])

        # Extract text
        processor = DocumentProcessor()
        extracted_text, metadata = processor.extract_text(document)

        document.extracted_text = extracted_text
        document.page_count = metadata.get('page_count')
        document.word_count = len(extracted_text.split())
        document.save(update_fields=['extracted_text', 'page_count', 'word_count'])

        # Chunk text (uses config defaults)
        chunks = processor.chunk_text(text=extracted_text)

        # Update status to indexing
        document.status = DocumentStatus.INDEXING
        document.save(update_fields=['status'])

        # Generate embeddings and store chunks (pass user so BYOK keys are used)
        embedding_service = EmbeddingService(user=document.user)
        from .services.pricing import KnowledgePricingService
        pricing_service = KnowledgePricingService()

        total_tokens = 0
        with transaction.atomic():
            chunk_objects = []
            for i, chunk_data in enumerate(chunks):
                embedding = embedding_service.generate_embedding(chunk_data['text'])
                total_tokens += chunk_data.get('token_count', 0)

                # Estimate page number if document has pages
                page_number = None
                if document.page_count and document.page_count > 1:
                    page_number = processor.estimate_page_number(
                        document, chunk_data.get('start_char', 0)
                    )

                chunk = KnowledgeChunk(
                    document=document,
                    user=document.user,
                    content=chunk_data['text'],
                    chunk_index=i,
                    start_char=chunk_data.get('start_char'),
                    end_char=chunk_data.get('end_char'),
                    page_number=page_number,
                    embedding=embedding,
                    embedding_model=config.embedding_model,
                    token_count=chunk_data.get('token_count', 0),
                )
                chunk_objects.append(chunk)

            # Bulk create chunks
            KnowledgeChunk.objects.bulk_create(chunk_objects)

            # Update document stats
            document.chunk_count = len(chunk_objects)
            document.status = DocumentStatus.READY
            document.processed_at = timezone.now()
            document.save(update_fields=['chunk_count', 'status', 'processed_at'])

            # Update user stats. `knowledge_base_settings` is the reverse
            # OneToOne accessor Django adds to User at runtime from
            # KnowledgeBaseSettings.user (declared in this app); the
            # authentication.User stub has no static knowledge of it.
            settings = document.user.knowledge_base_settings  # type: ignore[attr-defined]
            settings.update_stats(chunks_delta=len(chunk_objects))

        # Log embedding usage for billing (outside transaction for reliability)
        if total_tokens > 0:
            embedding_cost = pricing_service.get_embedding_cost(
                config.embedding_model, total_tokens
            )
            _log_indexing_usage(
                document.user,
                document_id,
                total_tokens,
                embedding_cost,
                len(chunk_objects),
                config.embedding_model,
                billing_origin=embedding_service.billing_origin,
            )

        logger.info(
            f"Processed document {document_id}: "
            f"{len(chunk_objects)} chunks created"
        )

    except KnowledgeDocument.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        raise

    except Exception as e:
        logger.exception(f"Error processing document {document_id}: {e}")

        # Update document status to failed
        try:
            document = KnowledgeDocument.objects.get(id=document_id)
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            document.save(update_fields=['status', 'error_message'])
        except Exception:
            pass

        raise


@shared_task
def cleanup_orphaned_chunks():
    """
    Periodic task to clean up any orphaned chunks.
    Runs daily via Celery Beat.
    """
    from .models import KnowledgeChunk

    # Delete chunks without a document (shouldn't happen, but just in case)
    deleted, _ = KnowledgeChunk.objects.filter(document__isnull=True).delete()
    if deleted:
        logger.info(f"Cleaned up {deleted} orphaned chunks")


@shared_task
def reindex_document(document_id: str):
    """
    Re-index a single document with new embeddings.
    Useful when embedding model changes.
    """
    from .models import KnowledgeDocument, DocumentStatus

    try:
        document = KnowledgeDocument.objects.get(id=document_id)

        # Delete existing chunks
        old_count = document.chunks.count()
        document.chunks.all().delete()
        document.chunk_count = 0
        document.status = DocumentStatus.PENDING
        document.save(update_fields=['chunk_count', 'status'])

        # Update user stats
        if hasattr(document.user, 'knowledge_base_settings'):
            document.user.knowledge_base_settings.update_stats(chunks_delta=-old_count)

        # Trigger reprocessing
        process_document_task.delay(document_id)

        logger.info(f"Triggered reindex for document {document_id}")

    except KnowledgeDocument.DoesNotExist:
        logger.error(f"Document {document_id} not found for reindex")
