"""
Models for Voice Rooms module.

Stores voice room configurations, agents, sessions, and conversation history.
"""

import uuid
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from authentication.models import User


class VoiceRoom(models.Model):
    """
    A voice room configuration where users can have multi-AI conversations.

    Each room can have multiple agents with different models, voices, and personas.
    """

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user: "models.ForeignKey[User, User]" = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="voice_rooms"
    )

    # Room configuration
    name: models.CharField = models.CharField(
        max_length=255,
        help_text="Display name for the room"
    )
    description: models.TextField = models.TextField(
        blank=True,
        help_text="Optional description of the room's purpose"
    )
    user_name: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        help_text="User's display name for agents to address them"
    )
    language: models.CharField = models.CharField(
        max_length=10,
        default="auto",
        help_text="Language code or 'auto' for auto-detection"
    )
    max_response_tokens: models.IntegerField = models.IntegerField(
        default=500,
        help_text="Maximum tokens per agent response"
    )

    # Status
    is_active: models.BooleanField = models.BooleanField(default=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class VoiceRoomAgent(models.Model):
    """
    An AI agent within a voice room.

    Each agent has a specific LLM, voice, and persona defined by system prompt.
    """

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room: "models.ForeignKey[VoiceRoom, VoiceRoom]" = models.ForeignKey(
        VoiceRoom,
        on_delete=models.CASCADE,
        related_name="agents"
    )

    # Agent configuration
    display_name: models.CharField = models.CharField(
        max_length=100,
        help_text="Name shown for this agent (e.g., 'The Skeptic', 'The Optimist')"
    )
    model_id: models.CharField = models.CharField(
        max_length=255,
        help_text="OpenRouter model ID (e.g., 'anthropic/claude-3-sonnet')"
    )
    system_prompt: models.TextField = models.TextField(
        help_text="System prompt defining the agent's persona and behavior"
    )

    # Voice configuration (ElevenLabs)
    voice_id: models.CharField = models.CharField(
        max_length=100,
        help_text="ElevenLabs voice ID"
    )
    voice_name: models.CharField = models.CharField(
        max_length=100,
        help_text="Display name for the voice"
    )
    voice_settings: models.JSONField = models.JSONField(
        default=dict,
        blank=True,
        help_text="Voice settings: stability, similarity_boost, style, use_speaker_boost, speed"
    )

    # Speaking order
    order: models.IntegerField = models.IntegerField(
        default=0,
        help_text="Order in which this agent speaks (lower = earlier)"
    )

    # Status
    is_active: models.BooleanField = models.BooleanField(default=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["room", "order"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.model_id})"


class VoiceRoomSession(models.Model):
    """
    A voice conversation session within a room.

    Tracks the state and metadata of an active or completed conversation.
    """

    STATUS_CHOICES = [
        ("idle", "Idle"),
        ("listening", "Listening"),
        ("processing", "Processing"),
        ("speaking", "Speaking"),
        ("paused", "Paused"),
        ("ended", "Ended"),
    ]

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room: "models.ForeignKey[VoiceRoom, VoiceRoom]" = models.ForeignKey(
        VoiceRoom,
        on_delete=models.CASCADE,
        related_name="sessions"
    )

    # Session state
    status: models.CharField = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="idle"
    )
    current_speaker: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ID of current speaker (agent_id or 'user')"
    )
    detected_language: models.CharField = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Detected language from user speech"
    )

    # Metrics
    total_duration_ms: models.IntegerField = models.IntegerField(
        default=0,
        help_text="Total session duration in milliseconds"
    )
    total_user_speaking_ms: models.IntegerField = models.IntegerField(
        default=0,
        help_text="Total user speaking time in milliseconds"
    )
    total_agent_speaking_ms: models.IntegerField = models.IntegerField(
        default=0,
        help_text="Total agent speaking time in milliseconds"
    )

    # Timestamps
    started_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    ended_at: models.DateTimeField = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["room", "-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Session {self.id} - {self.room.name}"


class VoiceRoomMessage(models.Model):
    """
    A message in a voice room session.

    Stores both user and agent messages with associated metadata.
    """

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session: "models.ForeignKey[VoiceRoomSession, VoiceRoomSession]" = models.ForeignKey(
        VoiceRoomSession,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    agent: "models.ForeignKey[Optional[VoiceRoomAgent], Optional[VoiceRoomAgent]]" = models.ForeignKey(
        VoiceRoomAgent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
        help_text="Agent that sent this message (null for user messages)"
    )

    # Message content
    role: models.CharField = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content: models.TextField = models.TextField(help_text="Text content of the message")

    # Speech timing
    audio_duration_ms: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="Duration of the audio in milliseconds"
    )
    stt_latency_ms: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="Speech-to-text processing latency"
    )
    llm_latency_ms: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="LLM response generation latency"
    )
    tts_latency_ms: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="Text-to-speech processing latency"
    )

    # LLM metadata (for assistant messages)
    model_id: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="OpenRouter model ID used"
    )
    prompt_tokens: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of prompt tokens"
    )
    completion_tokens: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of completion tokens"
    )

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.role}: {preview}"
