"""
Models for Consigliere AI module.
"""

import uuid
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from authentication.models import User


class ConsiglierSession(models.Model):
    """
    Represents a session where a user interacts with the Consigliere AI.

    A session is created when:
    - User requests analysis of a conversation
    - User starts chatting with Consigliere
    """

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user: "models.ForeignKey[User, User]" = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consigliere_sessions"
    )

    # Context
    chat_group_id: models.CharField = models.CharField(
        max_length=255,
        help_text="ID of the ChatGroup being analyzed (from frontend localStorage)"
    )
    chat_group_data: models.JSONField = models.JSONField(
        help_text="Full ChatGroup data for analysis"
    )
    current_model_at_start: models.CharField = models.CharField(
        max_length=255,
        help_text="Model selected when session started"
    )

    # Status
    is_active: models.BooleanField = models.BooleanField(default=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["chat_group_id"]),
        ]

    def __str__(self):
        return f"Session {self.id} - {self.user.email} - {self.created_at}"


class ConversationAnalysis(models.Model):
    """
    Stores the analysis results for a ChatGroup.

    Contains insights, metrics, and model recommendations.
    """

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session: "models.OneToOneField[ConsiglierSession, ConsiglierSession]" = models.OneToOneField(
        ConsiglierSession,
        on_delete=models.CASCADE,
        related_name="analysis"
    )

    # Analysis results
    conversation_type: models.CharField = models.CharField(
        max_length=100,
        help_text="Detected conversation type (e.g., 'technical_discussion', 'creative_writing')"
    )

    # Metrics
    total_messages: models.IntegerField = models.IntegerField(default=0)
    total_tokens: models.IntegerField = models.IntegerField(default=0)
    avg_cost_per_message: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True
    )
    avg_latency: models.FloatField = models.FloatField(
        null=True,
        blank=True,
        help_text="Average response latency in seconds"
    )
    total_cost: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0
    )

    # Insights
    insights: models.JSONField = models.JSONField(
        default=list,
        help_text="List of key insights about the conversation"
    )

    # Detected needs/preferences
    detected_needs: models.JSONField = models.JSONField(
        default=dict,
        help_text="Detected user needs (e.g., creativity, precision, speed)"
    )

    # User preferences (if provided)
    user_preferences: models.JSONField = models.JSONField(
        default=dict,
        help_text="User-specified preferences (budget, priority)"
    )

    # Recommended model from those used in conversation
    recommended_model_from_conversation: models.JSONField = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text="Best model chosen from those actually used in the conversation"
    )

    # Timestamps
    analyzed_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Conversation analyses"

    def __str__(self):
        return f"Analysis for Session {self.session.id}"


class ModelRecommendation(models.Model):
    """
    A single model recommendation with score and trade-offs.
    """

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis: "models.ForeignKey[ConversationAnalysis, ConversationAnalysis]" = models.ForeignKey(
        ConversationAnalysis,
        on_delete=models.CASCADE,
        related_name="recommendations"
    )

    # Model info
    model_id: models.CharField = models.CharField(max_length=255)
    model_name: models.CharField = models.CharField(max_length=255)
    provider: models.CharField = models.CharField(max_length=100)

    # Scoring
    score: models.FloatField = models.FloatField(
        help_text="Overall recommendation score (0-1)"
    )
    rank: models.IntegerField = models.IntegerField(
        help_text="Rank in the recommendation list (1 = best)"
    )

    # Reasoning
    reasoning: models.TextField = models.TextField(
        help_text="Explanation of why this model is recommended"
    )

    # Trade-offs
    tradeoffs: models.JSONField = models.JSONField(
        default=dict,
        help_text="Trade-offs vs current model (cost_savings, quality_delta, speed_delta)"
    )

    # Estimated metrics with this model
    estimated_cost_per_message: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True
    )
    estimated_quality_score: models.FloatField = models.FloatField(
        null=True,
        blank=True,
        help_text="Estimated quality score (0-1)"
    )

    class Meta:
        ordering = ["rank"]
        indexes = [
            models.Index(fields=["analysis", "rank"]),
        ]

    def __str__(self):
        return f"#{self.rank}: {self.model_name} (score: {self.score})"


class ConsigliereMessage(models.Model):
    """
    A message in the conversation with the Consigliere AI.
    """

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Consigliere"),
    ]

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session: "models.ForeignKey[ConsiglierSession, ConsiglierSession]" = models.ForeignKey(
        ConsiglierSession,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    role: models.CharField = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content: models.TextField = models.TextField()

    # Metadata for assistant messages
    model_used: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Model used to generate this response"
    )
    model_id: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Model ID (extracted from model_used)"
    )
    provider: models.CharField = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Provider name (extracted from model_used)"
    )
    model_icon_slug: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Model icon slug from LobeHub"
    )
    model_icon_url: models.CharField = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        help_text="Full URL to model icon"
    )
    provider_icon_slug: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Provider icon slug from LobeHub"
    )
    provider_icon_url: models.CharField = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        help_text="Full URL to provider icon"
    )
    tokens_used: models.IntegerField = models.IntegerField(
        null=True,
        blank=True
    )
    prompt_tokens: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of tokens in the prompt"
    )
    completion_tokens: models.IntegerField = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of tokens in the completion"
    )
    cost: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Total cost (prompt + completion)"
    )
    prompt_cost: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Cost for prompt tokens"
    )
    completion_cost: models.DecimalField = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Cost for completion tokens"
    )
    latency: models.FloatField = models.FloatField(
        null=True,
        blank=True,
        help_text="Response latency in seconds"
    )

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
