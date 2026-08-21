"""
URL configuration for Knowledge Base API.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    KnowledgeBaseSettingsViewSet,
    KnowledgeDocumentViewSet,
    KnowledgeSearchViewSet,
    KnowledgeQueryLogViewSet,
    download_document,
)

router = DefaultRouter()
router.register(r'documents', KnowledgeDocumentViewSet, basename='knowledge-documents')
router.register(r'search', KnowledgeSearchViewSet, basename='knowledge-search')
router.register(r'logs', KnowledgeQueryLogViewSet, basename='knowledge-logs')

urlpatterns = [
    path('settings/', KnowledgeBaseSettingsViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'update',
    }), name='knowledge-settings'),
    path('documents/<uuid:document_id>/download/', download_document, name='document-download'),
    path('', include(router.urls)),
]
