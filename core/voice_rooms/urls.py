"""URL configuration for Voice Rooms API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VoiceRoomViewSet,
    VoiceRoomSessionViewSet,
    list_voices,
    recommended_voices,
    tts_models,
    tts_providers,
    text_to_speech,
    voice_preview,
    generate_room,
    eligible_models,
)

router = DefaultRouter()
router.register(r"rooms", VoiceRoomViewSet, basename="voice-room")
router.register(r"sessions", VoiceRoomSessionViewSet, basename="voice-room-session")

urlpatterns = [
    path("", include(router.urls)),
    # TTS providers
    path("tts-providers/", tts_providers, name="tts-providers"),
    # Voices (supports ?provider= query param)
    path("voices/", list_voices, name="voice-list"),
    path("voices/recommended/", recommended_voices, name="voice-recommended"),
    # Models (supports ?provider= query param)
    path("tts-models/", tts_models, name="tts-models"),
    # Text-to-speech endpoints
    path("tts/", text_to_speech, name="text-to-speech"),
    path("voice-preview/", voice_preview, name="voice-preview"),
    # AI-powered room generation
    path("generate-room/", generate_room, name="generate-room"),
    # Eligible LLM models for voice rooms
    path("eligible-models/", eligible_models, name="eligible-models"),
]
