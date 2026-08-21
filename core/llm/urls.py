"""
URL configuration for LLM module.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ModelCatalogViewSet, CompletionViewSet, ImageModelCatalogViewSet, VideoModelViewSet, stream_complete_langchain, google_maps_place_photo, get_generation_usage
from .transcription import transcribe_audio, get_stt_languages

router = DefaultRouter()
router.register(r"models", ModelCatalogViewSet, basename="model-catalog")
router.register(r"image-models", ImageModelCatalogViewSet, basename="image-model-catalog")
router.register(r"video-models", VideoModelViewSet, basename="video-model-catalog")
router.register(r"completions", CompletionViewSet, basename="completions")

app_name = "llm"

urlpatterns = [
    path("", include(router.urls)),
    # LangChain-based streaming (V2)
    path("completions/stream-complete-v2/", stream_complete_langchain, name="stream-complete-v2"),
    # Google Maps proxy (for frontend display, not sent to models)
    path("google-maps/places/search-photo/", google_maps_place_photo, name="google-maps-place-photo"),
    # OpenRouter generation usage lookup (for precise billing after abort)
    path("generation/<str:generation_id>/usage/", get_generation_usage, name="generation-usage"),
    # Speech-to-text transcription
    path("transcribe/", transcribe_audio, name="transcribe-audio"),
    path("stt-languages/", get_stt_languages, name="stt-languages"),
]
