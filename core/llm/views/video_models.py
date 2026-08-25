"""
Views for video generation model configuration.
"""

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


class VideoModelViewSet(viewsets.ViewSet):
    """
    ViewSet for video generation model configuration.

    Returns available video models and their configuration from constants.py.
    Unlike ImageModelCatalog, this doesn't use a database table since
    video models are centrally configured.
    """

    permission_classes = [AllowAny]  # Models list is public information

    def list(self, request):
        """
        List available video models and configuration.

        Returns:
            - models: List of available video models with pricing
            - supported_aspect_ratios: Available aspect ratios
            - default_aspect_ratio: Default aspect ratio
            - default_duration_seconds: Default video duration
            - default_model: Default model ID
        """
        from ..video_providers import (
            VIDEO_MODELS,
            SUPPORTED_ASPECT_RATIOS,
            DEFAULT_ASPECT_RATIO,
            DEFAULT_DURATION_SECONDS,
            DEFAULT_VIDEO_MODEL,
        )
        from ..serializers import VideoModelConfigSerializer

        # Convert VideoModelConfig dataclasses to dicts
        models_data = []
        for model in VIDEO_MODELS.values():
            models_data.append({
                "model_id": model.model_id,
                "canonical_id": model.canonical_id,
                "display_name": model.display_name,
                "provider": model.provider,
                "price_per_second_usd": model.price_per_second_usd,
                "max_duration_seconds": model.max_duration_seconds,
                "is_pro": model.is_pro,
                "supported_fps": model.supported_fps,
                "description": model.description,
            })

        config_data = {
            "models": models_data,
            "supported_aspect_ratios": list(SUPPORTED_ASPECT_RATIOS),
            "default_aspect_ratio": DEFAULT_ASPECT_RATIO,
            "default_duration_seconds": DEFAULT_DURATION_SECONDS,
            "default_model": DEFAULT_VIDEO_MODEL.model_id,
        }

        serializer = VideoModelConfigSerializer(config_data)
        return Response(serializer.data)


