"""Serializers for Voice Rooms API."""

import logging
from rest_framework import serializers
from .models import VoiceRoom, VoiceRoomAgent, VoiceRoomSession, VoiceRoomMessage
from .voice_utils import (
    get_provider_from_model,
    validate_and_fix_agent_voice,
)

logger = logging.getLogger(__name__)


class VoiceRoomAgentSerializer(serializers.ModelSerializer):
    """Serializer for VoiceRoomAgent model."""

    class Meta:
        model = VoiceRoomAgent
        fields = [
            "id",
            "display_name",
            "model_id",
            "system_prompt",
            "voice_id",
            "voice_name",
            "voice_settings",
            "order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class VoiceRoomSerializer(serializers.ModelSerializer):
    """Serializer for VoiceRoom model."""

    agents = VoiceRoomAgentSerializer(many=True, read_only=True)

    class Meta:
        model = VoiceRoom
        fields = [
            "id",
            "name",
            "description",
            "user_name",
            "language",
            "max_response_tokens",
            "is_active",
            "agents",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class VoiceRoomCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a VoiceRoom with agents."""

    agents = VoiceRoomAgentSerializer(many=True)

    class Meta:
        model = VoiceRoom
        fields = [
            "name",
            "description",
            "user_name",
            "language",
            "max_response_tokens",
            "agents",
        ]

    def validate_agents(self, agents):
        """Validate that there are no duplicate display names among agents."""
        display_names = [agent.get("display_name", "").strip().lower() for agent in agents]
        duplicates = [name for name in display_names if display_names.count(name) > 1]
        if duplicates:
            raise serializers.ValidationError(
                f"Duplicate agent display names are not allowed: {', '.join(set(duplicates))}"
            )
        return agents

    def create(self, validated_data):
        agents_data = validated_data.pop("agents", [])
        room = VoiceRoom.objects.create(**validated_data)

        for i, agent_data in enumerate(agents_data):
            # Detect provider from voice settings and validate voice
            voice_settings = agent_data.get("voice_settings", {})
            tts_model = voice_settings.get("tts_model", "") if voice_settings else ""
            provider = voice_settings.get("tts_provider", "") if voice_settings else ""

            # If provider not explicitly set, detect from model
            if not provider:
                provider = get_provider_from_model(tts_model)

            # Validate and fix voice if needed
            agent_data = validate_and_fix_agent_voice(agent_data, provider, index=i)

            VoiceRoomAgent.objects.create(room=room, **agent_data)

        return room


class VoiceRoomUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a VoiceRoom."""

    agents = VoiceRoomAgentSerializer(many=True, required=False)

    class Meta:
        model = VoiceRoom
        fields = [
            "name",
            "description",
            "user_name",
            "language",
            "max_response_tokens",
            "agents",
        ]

    def validate_agents(self, agents):
        """Validate that there are no duplicate display names among agents."""
        if agents is None:
            return agents
        display_names = [agent.get("display_name", "").strip().lower() for agent in agents]
        duplicates = [name for name in display_names if display_names.count(name) > 1]
        if duplicates:
            raise serializers.ValidationError(
                f"Duplicate agent display names are not allowed: {', '.join(set(duplicates))}"
            )
        return agents

    def update(self, instance, validated_data):
        agents_data = validated_data.pop("agents", None)

        # Update room fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update agents if provided - update in place to preserve agent IDs
        # This is important because messages have foreign keys to agents
        if agents_data is not None:
            # Build lookup maps for existing agents
            existing_agents_by_id = {str(agent.id): agent for agent in instance.agents.all()}
            existing_agents_by_order = {agent.order: agent for agent in instance.agents.all()}
            updated_agent_ids = set()

            for i, agent_data in enumerate(agents_data):
                # Detect provider from voice settings and validate voice
                voice_settings = agent_data.get("voice_settings", {})
                tts_model = voice_settings.get("tts_model", "") if voice_settings else ""
                provider = voice_settings.get("tts_provider", "") if voice_settings else ""

                # If provider not explicitly set, detect from model
                if not provider:
                    provider = get_provider_from_model(tts_model)

                # Validate and fix voice if needed
                agent_data = validate_and_fix_agent_voice(agent_data, provider, index=i)

                # Try to match existing agent by ID first, then by order
                agent_id = agent_data.pop("id", None)
                order = agent_data.get("order", i)
                existing_agent = None

                if agent_id and str(agent_id) in existing_agents_by_id:
                    existing_agent = existing_agents_by_id[str(agent_id)]
                elif order in existing_agents_by_order:
                    existing_agent = existing_agents_by_order[order]

                if existing_agent:
                    # Update existing agent in place (preserves ID for message references)
                    updated_agent_ids.add(str(existing_agent.id))
                    for attr, value in agent_data.items():
                        setattr(existing_agent, attr, value)
                    existing_agent.save()
                else:
                    # Create new agent
                    new_agent = VoiceRoomAgent.objects.create(room=instance, **agent_data)
                    updated_agent_ids.add(str(new_agent.id))

            # Delete agents that are no longer in the list
            for agent_id, agent in existing_agents_by_id.items():
                if agent_id not in updated_agent_ids:
                    agent.delete()

        return instance


class VoiceRoomMessageSerializer(serializers.ModelSerializer):
    """Serializer for VoiceRoomMessage model."""

    agent_id = serializers.SerializerMethodField()
    agent_name = serializers.SerializerMethodField()

    class Meta:
        model = VoiceRoomMessage
        fields = [
            "id",
            "role",
            "content",
            "agent_id",
            "agent_name",
            "audio_duration_ms",
            "stt_latency_ms",
            "llm_latency_ms",
            "tts_latency_ms",
            "model_id",
            "prompt_tokens",
            "completion_tokens",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_agent_id(self, obj):
        return str(obj.agent.id) if obj.agent else None

    def get_agent_name(self, obj):
        return obj.agent.display_name if obj.agent else None


class VoiceRoomSessionSerializer(serializers.ModelSerializer):
    """Serializer for VoiceRoomSession model."""

    messages = VoiceRoomMessageSerializer(many=True, read_only=True)

    class Meta:
        model = VoiceRoomSession
        fields = [
            "id",
            "room",
            "status",
            "current_speaker",
            "detected_language",
            "total_duration_ms",
            "total_user_speaking_ms",
            "total_agent_speaking_ms",
            "started_at",
            "ended_at",
            "messages",
        ]
        read_only_fields = ["id", "started_at"]


class VoiceRoomListSerializer(serializers.ModelSerializer):
    """Serializer for listing rooms with agents."""

    agents = VoiceRoomAgentSerializer(many=True, read_only=True)

    class Meta:
        model = VoiceRoom
        fields = [
            "id",
            "name",
            "description",
            "user_name",
            "language",
            "agents",
            "is_active",
            "created_at",
            "updated_at",
        ]
