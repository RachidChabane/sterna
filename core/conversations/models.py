"""
Conversation models for storing chat history.

Hierarchy:
- Conversation (formerly ChatGroup): A conversation container
- Chat: An individual chat session within a conversation (has its own model)
- Message: A message within a chat

This replaces the previous localStorage + user-preferences approach.
"""
import uuid
from typing import TYPE_CHECKING

from django.db import models
from django.conf import settings

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from authentication.models import User


class Conversation(models.Model):
    """
    A conversation container (formerly ChatGroup).

    A conversation can contain one or more chats, each with its own model.
    Related models (Workspace, Asset) reference conversations via FK.
    """
    if TYPE_CHECKING:
        chats: RelatedManager["Chat"]

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Owner
    user: "models.ForeignKey[User, User]" = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations'
    )

    # Metadata
    name: models.CharField = models.CharField(max_length=255, blank=True)
    is_custom_name: models.BooleanField = models.BooleanField(default=False)

    # Status
    is_archived: models.BooleanField = models.BooleanField(default=False)
    is_pinned: models.BooleanField = models.BooleanField(default=False)

    # Consigliere integration
    consigliere_session_id: models.CharField = models.CharField(max_length=255, blank=True, null=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)
    last_message_at: models.DateTimeField = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', 'is_archived']),
            models.Index(fields=['user', 'is_pinned']),
            models.Index(fields=['last_message_at']),
        ]

    def __str__(self):
        return f"{self.name or 'Untitled'} ({self.id})"

    @property
    def message_count(self) -> int:
        """Total messages across all chats in this conversation."""
        return Message.objects.filter(chat__conversation=self).count()

    @property
    def chat_count(self) -> int:
        return self.chats.count()

    def generate_name_from_messages(self) -> str:
        """Generate conversation name from first user message."""
        first_message = Message.objects.filter(
            chat__conversation=self,
            role=Message.ROLE_USER
        ).order_by('chat__id', 'sequence').first()

        if first_message and first_message.content:
            text = first_message.content.get('text', '')[:50]
            return text + ('...' if len(text) >= 50 else '') if text else 'New Conversation'
        return 'New Conversation'


class Chat(models.Model):
    """
    An individual chat session within a conversation.

    Each chat can have its own model and parameters.
    A conversation typically has one chat, but can have multiple
    (e.g., comparing responses from different models).
    """
    if TYPE_CHECKING:
        messages: RelatedManager["Message"]

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Parent conversation
    conversation: "models.ForeignKey[Conversation, Conversation]" = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='chats'
    )

    # Model configuration
    model_id: models.CharField = models.CharField(max_length=100, blank=True, null=True)
    model_provider: models.CharField = models.CharField(max_length=50, blank=True, null=True)
    parameters: models.JSONField = models.JSONField(default=dict, blank=True)

    # Position within conversation (for ordering)
    position: models.PositiveIntegerField = models.PositiveIntegerField(default=0)

    # Status
    is_disabled: models.BooleanField = models.BooleanField(default=False)
    is_hidden: models.BooleanField = models.BooleanField(default=False)

    # Chat-specific custom instructions
    # Format: {"content": "...", "mode": "append"|"override"}
    instructions: models.JSONField = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'created_at']
        indexes = [
            models.Index(fields=['conversation']),
            models.Index(fields=['conversation', 'position']),
        ]

    def __str__(self):
        model_str = self.model_id or 'no model'
        return f"Chat {self.id} ({model_str})"

    def save(self, *args, **kwargs):
        # Auto-assign position if not set (new chat)
        if self._state.adding and self.position == 0:
            max_result = Chat.objects.filter(
                conversation=self.conversation
            ).aggregate(models.Max('position'))['position__max']
            # Use -1 only if no chats exist (None), not when max is 0
            max_pos = max_result if max_result is not None else -1
            self.position = max_pos + 1
        super().save(*args, **kwargs)

    @property
    def message_count(self) -> int:
        return self.messages.count()


class Message(models.Model):
    """
    A message within a chat.

    Supports user messages, assistant responses, tool calls, and system messages.
    Messages are ordered by sequence number within a chat.
    """
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_TOOL = 'tool'
    ROLE_SYSTEM = 'system'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
        (ROLE_TOOL, 'Tool'),
        (ROLE_SYSTEM, 'System'),
    ]

    id: models.UUIDField = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Parent chat
    chat: "models.ForeignKey[Chat, Chat]" = models.ForeignKey(
        Chat,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    # Message content
    role: models.CharField = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content: models.JSONField = models.JSONField(default=dict)
    # Content structure: {"text": "...", "images": [...], ...}

    # Ordering within chat
    sequence: models.PositiveIntegerField = models.PositiveIntegerField(default=0)

    # Model info (for assistant messages)
    model_id: models.CharField = models.CharField(max_length=100, blank=True, null=True)
    model_provider: models.CharField = models.CharField(max_length=50, blank=True, null=True)

    # Token usage and cost
    prompt_tokens: models.IntegerField = models.IntegerField(null=True, blank=True)
    completion_tokens: models.IntegerField = models.IntegerField(null=True, blank=True)
    cost: models.DecimalField = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # Tool calls (for assistant messages)
    tool_calls: models.JSONField = models.JSONField(default=list, blank=True)
    # Structure: [{"id": "...", "type": "function", "function": {...}}]

    # Tool response (for tool messages)
    tool_call_id: models.CharField = models.CharField(max_length=255, blank=True, null=True)

    # Execution steps (for complex multi-step responses)
    steps: models.JSONField = models.JSONField(default=list, blank=True)

    # Metadata
    metadata: models.JSONField = models.JSONField(default=dict, blank=True)

    # Stopped flag (user clicked Stop during streaming)
    is_stopped: models.BooleanField = models.BooleanField(default=False)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chat', 'sequence']
        indexes = [
            models.Index(fields=['chat', 'sequence']),
            models.Index(fields=['chat', 'role']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['chat', 'sequence'],
                name='unique_message_sequence_per_chat'
            )
        ]

    def __str__(self):
        preview = str(self.content.get('text', ''))[:50] if self.content else ''
        return f"{self.role}: {preview}"

    def save(self, *args, **kwargs):
        # Auto-assign sequence if not set
        if not self.sequence:
            max_seq = Message.objects.filter(
                chat=self.chat
            ).aggregate(models.Max('sequence'))['sequence__max'] or 0
            self.sequence = max_seq + 1

        super().save(*args, **kwargs)

        # Update conversation's last_message_at
        Conversation.objects.filter(id=self.chat.conversation_id).update(
            last_message_at=self.created_at,
            updated_at=self.created_at
        )
