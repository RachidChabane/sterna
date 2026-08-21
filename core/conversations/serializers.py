"""
Serializers for conversation models.

Provides serialization for Conversation, Chat, and Message models
with support for nested representations and bulk operations.
"""

from rest_framework import serializers
from .models import Conversation, Chat, Message
from sparks.serializers import MessageSparkSerializer
from .prompt_protection import validate_instructions


def validate_chat_instructions(value):
    """
    Validate chat instructions for prompt injection attempts.
    """
    if not value:
        return value

    content = value.get('content', '')
    if content:
        is_valid, error_message = validate_instructions(content)
        if not is_valid:
            raise serializers.ValidationError(error_message)

    return value


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message model."""
    sparks = MessageSparkSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            'id',
            'chat',
            'role',
            'content',
            'sequence',
            'model_id',
            'model_provider',
            'prompt_tokens',
            'completion_tokens',
            'cost',
            'tool_calls',
            'tool_call_id',
            'steps',
            'metadata',
            'is_stopped',
            'sparks',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'sequence']

    def create(self, validated_data):
        """Create message with auto-assigned sequence."""
        return super().create(validated_data)


class MessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating messages (minimal fields)."""

    class Meta:
        model = Message
        fields = [
            'id',
            'role',
            'content',
            'model_id',
            'model_provider',
            'prompt_tokens',
            'completion_tokens',
            'cost',
            'tool_calls',
            'tool_call_id',
            'steps',
            'metadata',
            'is_stopped',
        ]
        read_only_fields = ['id']


class ChatSerializer(serializers.ModelSerializer):
    """Serializer for Chat model."""

    message_count = serializers.IntegerField(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)
    sparks = MessageSparkSerializer(many=True, read_only=True)
    instructions = serializers.JSONField(
        required=False,
        allow_null=True,
        validators=[validate_chat_instructions]
    )

    class Meta:
        model = Chat
        fields = [
            'id',
            'conversation',
            'model_id',
            'model_provider',
            'parameters',
            'position',
            'is_disabled',
            'is_hidden',
            'instructions',
            'message_count',
            'messages',
            'sparks',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChatListSerializer(serializers.ModelSerializer):
    """Lightweight chat serializer for list views (no messages)."""

    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Chat
        fields = [
            'id',
            'model_id',
            'model_provider',
            'parameters',
            'position',
            'is_disabled',
            'is_hidden',
            'instructions',
            'message_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChatCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chats."""

    instructions = serializers.JSONField(
        required=False,
        allow_null=True,
        validators=[validate_chat_instructions]
    )

    class Meta:
        model = Chat
        fields = [
            'model_id',
            'model_provider',
            'parameters',
            'position',
            'instructions',
        ]


class ConversationSerializer(serializers.ModelSerializer):
    """Full serializer for Conversation model with nested chats."""

    message_count = serializers.IntegerField(read_only=True)
    chat_count = serializers.IntegerField(read_only=True)
    chats = ChatListSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            'id',
            'user',
            'name',
            'is_custom_name',
            'is_archived',
            'is_pinned',
            'consigliere_session_id',
            'message_count',
            'chat_count',
            'chats',
            'created_at',
            'updated_at',
            'last_message_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'last_message_at']


class ConversationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for conversation list views."""

    message_count = serializers.IntegerField(read_only=True)
    chat_count = serializers.IntegerField(read_only=True)
    # Include first chat's model info for display (legacy, kept for compatibility)
    model_id = serializers.SerializerMethodField()
    model_provider = serializers.SerializerMethodField()
    # Include all chat models for hover display
    chat_models = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'name',
            'is_custom_name',
            'is_archived',
            'is_pinned',
            'message_count',
            'chat_count',
            'model_id',
            'model_provider',
            'chat_models',
            'created_at',
            'updated_at',
            'last_message_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at']

    def get_model_id(self, obj):
        """Get model_id from first chat."""
        first_chat = obj.chats.first()
        return first_chat.model_id if first_chat else None

    def get_model_provider(self, obj):
        """Get model_provider from first chat."""
        first_chat = obj.chats.first()
        return first_chat.model_provider if first_chat else None

    def get_chat_models(self, obj):
        """Get all chat models for display on hover."""
        return [
            {'model_id': chat.model_id, 'model_provider': chat.model_provider}
            for chat in obj.chats.all()
            if chat.model_id  # Only include chats with a model set
        ]


class ConversationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating conversations."""

    # Optional: create first chat along with conversation
    model_id = serializers.CharField(required=False, allow_blank=True, write_only=True)
    model_provider = serializers.CharField(required=False, allow_blank=True, write_only=True)
    parameters = serializers.JSONField(required=False, default=dict, write_only=True)

    class Meta:
        model = Conversation
        fields = [
            'id',  # Include ID in response
            'name',
            'is_custom_name',
            'consigliere_session_id',
            'created_at',
            'updated_at',
            # Chat creation fields (write-only)
            'model_id',
            'model_provider',
            'parameters',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        """Create conversation with optional first chat."""
        model_id = validated_data.pop('model_id', None)
        model_provider = validated_data.pop('model_provider', None)
        parameters = validated_data.pop('parameters', {})

        # Add user from context
        validated_data['user'] = self.context['request'].user

        conversation = super().create(validated_data)

        # Create first chat if model info or parameters provided
        if model_id or model_provider or parameters:
            Chat.objects.create(
                conversation=conversation,
                model_id=model_id,
                model_provider=model_provider,
                parameters=parameters,
            )

        return conversation


class ConversationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating conversations."""

    class Meta:
        model = Conversation
        fields = [
            'name',
            'is_custom_name',
            'is_archived',
            'is_pinned',
            'consigliere_session_id',
        ]


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with full chat and message data."""

    message_count = serializers.IntegerField(read_only=True)
    chat_count = serializers.IntegerField(read_only=True)
    chats = ChatSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            'id',
            'user',
            'name',
            'is_custom_name',
            'is_archived',
            'is_pinned',
            'consigliere_session_id',
            'message_count',
            'chat_count',
            'chats',
            'created_at',
            'updated_at',
            'last_message_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'last_message_at']


class BulkMessageCreateSerializer(serializers.Serializer):
    """Serializer for bulk message creation."""

    messages = MessageCreateSerializer(many=True)

    def create(self, validated_data):
        """Create multiple messages in a single transaction."""
        chat = self.context['chat']
        messages_data = validated_data['messages']

        # Get the current max sequence
        from django.db.models import Max
        max_seq = chat.messages.aggregate(Max('sequence'))['sequence__max'] or 0

        messages = []
        for i, msg_data in enumerate(messages_data):
            messages.append(Message(
                chat=chat,
                sequence=max_seq + i + 1,
                **msg_data
            ))

        return Message.objects.bulk_create(messages)
