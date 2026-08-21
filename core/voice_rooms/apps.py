"""Voice Rooms app configuration."""

from django.apps import AppConfig


class VoiceRoomsConfig(AppConfig):
    """Configuration for the Voice Rooms application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "voice_rooms"
    verbose_name = "Voice Rooms"
