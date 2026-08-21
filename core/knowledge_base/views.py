"""
API views for Knowledge Base.
"""

import logging
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from .models import (
    KnowledgeBaseSettings,
    KnowledgeDocument,
    KnowledgeQueryLog,
    DocumentStatus,
    StorageType,
)
from .serializers import (
    KnowledgeBaseSettingsSerializer,
    KnowledgeDocumentListSerializer,
    KnowledgeDocumentDetailSerializer,
    KnowledgeDocumentUploadSerializer,
    KnowledgeSearchResultSerializer,
    KnowledgeQueryRequestSerializer,
    KnowledgeQueryLogSerializer,
)
from .tasks import process_document_task
from .services import KnowledgeQueryService, DocumentUploadService

logger = logging.getLogger(__name__)


class KnowledgeBaseSettingsViewSet(viewsets.ViewSet):
    """User's knowledge base settings."""
    permission_classes = [IsAuthenticated]

    def retrieve(self, request):
        """GET /api/knowledge/settings/"""
        settings, created = KnowledgeBaseSettings.objects.get_or_create(
            user=request.user,
            defaults={'storage_limit_mb': 100}
        )
        serializer = KnowledgeBaseSettingsSerializer(settings)
        return Response(serializer.data)

    def update(self, request):
        """PUT/PATCH /api/knowledge/settings/"""
        settings, _ = KnowledgeBaseSettings.objects.get_or_create(
            user=request.user
        )
        serializer = KnowledgeBaseSettingsSerializer(
            settings,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class KnowledgeDocumentViewSet(viewsets.ModelViewSet):
    """CRUD for knowledge base documents."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = None  # Disable pagination - frontend expects plain array

    def get_queryset(self):
        return KnowledgeDocument.objects.filter(
            user=self.request.user
        ).select_related('user')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return KnowledgeDocumentDetailSerializer
        elif self.action == 'create':
            return KnowledgeDocumentUploadSerializer
        return KnowledgeDocumentListSerializer

    def create(self, request):
        """POST /api/knowledge/documents/ - Upload new document."""
        from decimal import Decimal

        from usage_quota.billing.service import get_billing_service
        from usage_quota.models import FeatureType, ServiceType

        serializer = KnowledgeDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data['file']
        size_mb_delta = max(1, int(getattr(file_obj, 'size', 0)) // (1024 * 1024))

        billing = get_billing_service()
        billing.check_quota(
            user=request.user,
            service=ServiceType.KNOWLEDGE_BASE_EMBEDDING,
            estimated_cost=Decimal('0'),
            feature=FeatureType.KNOWLEDGE_BASE,
            feature_name='kb_upload',
            request_units=1,
        )
        billing.check_quota(
            user=request.user,
            service=ServiceType.KNOWLEDGE_BASE_EMBEDDING,
            estimated_cost=Decimal('0'),
            feature=FeatureType.KNOWLEDGE_BASE,
            feature_name='kb_storage_mb',
            request_units=size_mb_delta,
        )

        upload_service = DocumentUploadService()

        try:
            document = upload_service.upload(
                user=request.user,
                file=file_obj,
                tags=serializer.validated_data.get('tags', []),
            )
        except upload_service.StorageLimitExceeded:
            return Response(
                {'error': 'Storage limit exceeded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except upload_service.UnsupportedFileType as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except upload_service.DuplicateDocument as e:
            return Response(
                {
                    'error': 'Duplicate document',
                    'existing_document_id': str(e.existing_id),
                    'existing_filename': e.existing_filename,
                },
                status=status.HTTP_409_CONFLICT
            )

        return Response(
            KnowledgeDocumentDetailSerializer(document).data,
            status=status.HTTP_201_CREATED
        )

    def destroy(self, request, pk=None):
        """DELETE /api/knowledge/documents/{id}/ - Delete document and chunks."""
        document = self.get_object()

        with transaction.atomic():
            chunk_count = document.chunk_count
            file_size = document.file_size_bytes
            document.delete()

            # Use model method for atomic stats update (DRY)
            settings = self._get_or_create_settings(request.user)
            settings.update_stats(
                documents_delta=-1,
                chunks_delta=-chunk_count,
                storage_delta=-file_size,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """POST /api/knowledge/documents/bulk_delete/ - Delete multiple documents."""
        document_ids = request.data.get('document_ids', [])

        documents = KnowledgeDocument.objects.filter(
            user=request.user,
            id__in=document_ids
        )

        with transaction.atomic():
            # Aggregate stats before deletion
            stats = documents.aggregate(
                total_chunks=Sum('chunk_count'),
                total_size=Sum('file_size_bytes'),
            )
            doc_count = documents.count()
            documents.delete()

            settings = self._get_or_create_settings(request.user)
            settings.update_stats(
                documents_delta=-doc_count,
                chunks_delta=-(stats['total_chunks'] or 0),
                storage_delta=-(stats['total_size'] or 0),
            )

        return Response({'deleted': doc_count})

    @action(detail=True, methods=['post'])
    def reprocess(self, request, pk=None):
        """POST /api/knowledge/documents/{id}/reprocess/ - Re-index document."""
        document = self.get_object()

        with transaction.atomic():
            old_chunk_count = document.chunk_count
            document.chunks.all().delete()
            document.status = DocumentStatus.PENDING
            document.chunk_count = 0
            document.save(update_fields=['status', 'chunk_count'])

            settings = self._get_or_create_settings(request.user)
            settings.update_stats(chunks_delta=-old_chunk_count)

        process_document_task.delay(str(document.id))
        return Response({'status': 'reprocessing'})

    @action(detail=True, methods=['patch'])
    def tags(self, request, pk=None):
        """PATCH /api/knowledge/documents/{id}/tags/ - Update document tags."""
        document = self.get_object()
        tags = request.data.get('tags', [])
        document.tags = tags
        document.save(update_fields=['tags'])
        return Response({'tags': document.tags})

    def _get_or_create_settings(self, user):
        settings, _ = KnowledgeBaseSettings.objects.get_or_create(user=user)
        return settings


class KnowledgeSearchViewSet(viewsets.ViewSet):
    """Search/query the knowledge base."""
    permission_classes = [IsAuthenticated]

    def create(self, request):
        """POST /api/knowledge/search/ - Query knowledge base."""
        serializer = KnowledgeQueryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query_service = KnowledgeQueryService()
        results, log = query_service.search(
            user=request.user,
            query=serializer.validated_data['query'],
            max_results=serializer.validated_data.get('max_results', 5),
            similarity_threshold=serializer.validated_data.get('similarity_threshold'),
            document_ids=serializer.validated_data.get('document_ids'),
            invocation_type='ui',
        )

        return Response({
            'results': KnowledgeSearchResultSerializer(results, many=True).data,
            'query_id': str(log.id),
            'latency_ms': log.latency_ms,
            'chunks_searched': log.chunks_searched,
        })


class KnowledgeQueryLogViewSet(viewsets.ReadOnlyModelViewSet):
    """View query history."""
    permission_classes = [IsAuthenticated]
    serializer_class = KnowledgeQueryLogSerializer

    def get_queryset(self):
        return KnowledgeQueryLog.objects.filter(
            user=self.request.user
        ).order_by('-created_at')[:100]


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_document(request, document_id):
    """
    Download knowledge base document.

    Pattern follows workspaces/api/views.py download_asset.
    """
    try:
        document = KnowledgeDocument.objects.get(
            id=document_id,
            user=request.user
        )
    except KnowledgeDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Get content based on storage type
    if document.storage_type == StorageType.INLINE:
        content = document.content
        if content is None:
            return Response(
                {'error': 'Document content not available'},
                status=status.HTTP_404_NOT_FOUND
            )
    elif document.storage_type == StorageType.R2:
        try:
            from .services.storage import get_knowledge_storage
            storage = get_knowledge_storage()
            content = storage.download(document.r2_bucket, document.r2_key)
        except FileNotFoundError:
            return Response(
                {'error': 'File not found in storage'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Failed to download document {document_id}: {e}")
            return Response(
                {'error': 'Failed to retrieve file from storage'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    else:
        return Response(
            {'error': 'Unknown storage type'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    response = HttpResponse(content, content_type=document.mime_type)
    response['Content-Disposition'] = f'inline; filename="{document.filename}"'
    return response
