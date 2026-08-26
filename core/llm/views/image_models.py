"""
Views for the image generation model catalog.
"""

import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.core.cache import cache

from ..models import ImageModelCatalog
from ..serializers import ImageModelCatalogSerializer, ImageModelFilterSerializer
from ..services.image_catalog_service import (
    build_image_model_list_response,
    populate_from_service,
)

logger = logging.getLogger(__name__)


class ImageModelCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for image generation model catalog.

    Provides endpoints for:
    - Listing available image models
    - Getting image model details
    - Refreshing catalog from image-generation service
    """

    queryset = ImageModelCatalog.objects.filter(is_available=True)
    serializer_class = ImageModelCatalogSerializer
    permission_classes = [AllowAny]  # Models list is public information

    def list(self, request):
        """
        List available image models with optional filtering.

        Performance: Results are cached in Redis for 5 minutes.
        """
        filter_serializer = ImageModelFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        response_data = build_image_model_list_response(
            filters, request.query_params, self.get_queryset()
        )
        return Response(response_data)

    @action(detail=False, methods=["post"], url_path="refresh")
    def refresh_catalog(self, request):
        """Refresh image model catalog from service."""
        try:
            # Clear cache
            cache.delete_pattern("image_models:*")

            # Repopulate from service
            populate_from_service()

            return Response({
                "success": True,
                "message": "Image model catalog refreshed"
            })
        except Exception as e:
            logger.error(f"[ImageModels] Refresh failed: {e}")
            return Response({
                "success": False,
                "error": "Failed to refresh model catalog. Please try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
