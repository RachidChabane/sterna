"""
Serializers for Spark API.
"""
import logging
from rest_framework import serializers
from .models import Spark, SparkDeployment, App
from conversations.models import Chat, Message

logger = logging.getLogger(__name__)


class DownloadUrlMixin:
    """Mixin to add download_url computed field to spark serializers."""

    def get_download_url(self, obj):
        """
        Generate download URL for downloadable spark types.
        - Renderable types (react/html/svg/markdown/mermaid): None
        - Direct-download types (csv/ics): URL to download endpoint
        - Generated documents (pdf/docx): URL to download endpoint (serves bytes directly)
        """
        if obj.is_renderable():
            return None
        if obj.is_direct_download() or (obj.is_generated_document() and obj.generated_r2_key):
            return f'/api/sparks/{obj.id}/download/'
        return None


class SparkAssetSerializer(serializers.Serializer):
    """
    Serializer for assets referenced by sparks.

    Uses presigned URLs for assets to allow sandboxed iframes to access them
    without authentication (presigned URLs are time-limited and self-authenticating).
    """
    id = serializers.UUIDField()
    url = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    filename = serializers.CharField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)

    def get_url(self, obj):
        """
        Generate presigned URL for the asset.

        Presigned URLs allow sandboxed iframes to access assets without
        authentication. They expire after 1 hour (3600 seconds).
        Falls back to authenticated URL if presigned URL generation fails.
        """
        # Try to get presigned URL for R2 assets
        if obj.storage_type == 'r2' and obj.r2_key:
            try:
                from workspaces.services import get_asset_storage_service
                storage = get_asset_storage_service()
                presigned_url = storage.get_presigned_url(obj, expiration=3600)
                if presigned_url:
                    return presigned_url
            except Exception as e:
                logger.warning(f"Failed to get presigned URL for asset {obj.id}: {e}")

        # Fallback to authenticated URL (won't work in sandboxed iframes)
        return f'/api/workspaces/assets/{obj.id}/download/'

    def get_type(self, obj):
        """Determine asset type from mime_type."""
        if obj.mime_type and obj.mime_type.startswith('video/'):
            return 'video'
        return 'image'


class SparkDeploymentSerializer(serializers.ModelSerializer):
    """Full serializer for SparkDeployment."""

    class Meta:
        model = SparkDeployment
        fields = [
            'id', 'status', 'preview_url', 'claim_url',
            'deployment_id', 'project_id', 'error_message',
            'cost_usd', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class LatestDeploymentMixin:
    """Mixin to add latest_deployment computed field to spark serializers."""

    def get_latest_deployment(self, obj):
        # Use prefetched deployments if available
        deployments = getattr(obj, '_prefetched_objects_cache', {}).get('deployments')
        if deployments is not None:
            dep = deployments[0] if deployments else None
        else:
            dep = obj.deployments.order_by('-created_at').first()
        if not dep:
            return None
        return {
            'id': str(dep.id),
            'status': dep.status,
            'preview_url': dep.preview_url,
            'claim_url': dep.claim_url,
        }


class SparkSerializer(DownloadUrlMixin, LatestDeploymentMixin, serializers.ModelSerializer):
    """Full spark serializer with code."""
    code = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    latest_deployment = serializers.SerializerMethodField()

    class Meta:
        model = Spark
        fields = [
            'id', 'title', 'description', 'framework',
            'code', 'dependencies', 'assets',
            'version', 'parent', 'preview_url',
            'chat', 'message',
            'download_url', 'latest_deployment', 'is_ignited',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'version', 'created_at', 'updated_at']

    def get_code(self, obj):
        """Retrieve code from storage."""
        return obj.get_code()

    def get_assets(self, obj):
        """Get assets associated with this spark."""
        return SparkAssetSerializer(obj.assets.all(), many=True).data


class SparkListSerializer(DownloadUrlMixin, LatestDeploymentMixin, serializers.ModelSerializer):
    """Serializer for listing sparks with code for rendering."""
    code = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    latest_deployment = serializers.SerializerMethodField()
    chat_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='chat', read_only=True)
    chat_name = serializers.SerializerMethodField()
    conversation_id = serializers.SerializerMethodField()

    class Meta:
        model = Spark
        fields = [
            'id', 'title', 'description', 'framework',
            'code', 'dependencies', 'assets', 'version', 'preview_url',
            'download_url', 'latest_deployment', 'is_ignited',
            'chat_id', 'chat_name', 'conversation_id', 'created_at', 'updated_at'
        ]

    def get_code(self, obj):
        """Retrieve code from storage."""
        return obj.get_code()

    def get_assets(self, obj):
        """Get assets associated with this spark."""
        return SparkAssetSerializer(obj.assets.all(), many=True).data

    def get_chat_name(self, obj):
        """Get the name of the associated chat/conversation."""
        if obj.chat and obj.chat.conversation:
            return obj.chat.conversation.name or 'Untitled Conversation'
        return None

    def get_conversation_id(self, obj):
        """Get the conversation ID for navigation."""
        if obj.chat and obj.chat.conversation:
            return str(obj.chat.conversation.id)
        return None


class SparkCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating sparks."""
    code = serializers.CharField(write_only=True)
    # Accept chat_id and message_id from frontend (maps to ForeignKey fields)
    chat_id = serializers.PrimaryKeyRelatedField(
        queryset=Chat.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        source='chat'
    )
    message_id = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        source='message'
    )

    class Meta:
        model = Spark
        fields = [
            'title', 'description', 'framework',
            'code', 'dependencies',
            'chat_id', 'message_id'
        ]

    def create(self, validated_data):
        code = validated_data.pop('code', '')
        user = self.context['request'].user

        # Create spark instance
        spark = Spark(user=user, **validated_data)

        # Save code (handles storage type selection)
        spark.save_code(code)
        spark.save()

        return spark


class SparkUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating sparks."""
    code = serializers.CharField(required=False, write_only=True)

    class Meta:
        model = Spark
        fields = ['title', 'description', 'code', 'dependencies']

    def update(self, instance, validated_data):
        code = validated_data.pop('code', None)

        # Update simple fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update code if provided
        if code is not None:
            instance.save_code(code)

        instance.save()
        return instance


class SparkReferenceSerializer(serializers.Serializer):
    """Minimal serializer for spark references in messages."""
    id = serializers.UUIDField()
    title = serializers.CharField()
    framework = serializers.CharField()
    version = serializers.IntegerField()


class MessageSparkSerializer(DownloadUrlMixin, LatestDeploymentMixin, serializers.ModelSerializer):
    """Serializer for sparks embedded in messages (includes code for rendering)."""
    code = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    latest_deployment = serializers.SerializerMethodField()
    parent_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='parent', read_only=True)

    class Meta:
        model = Spark
        fields = ['id', 'title', 'framework', 'code', 'dependencies', 'assets', 'download_url', 'latest_deployment', 'is_ignited', 'version', 'parent_id']

    def get_code(self, obj):
        """Retrieve code from storage."""
        return obj.get_code()

    def get_assets(self, obj):
        """Get assets associated with this spark."""
        return SparkAssetSerializer(obj.assets.all(), many=True).data


class AppSerializer(LatestDeploymentMixin, serializers.ModelSerializer):
    """Full serializer for App (detail view)."""

    spark_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='spark', read_only=True)
    spark_title = serializers.SerializerMethodField()
    spark_framework = serializers.SerializerMethodField()
    chat_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='chat', read_only=True)
    conversation_id = serializers.SerializerMethodField()
    latest_deployment = serializers.SerializerMethodField()

    class Meta:
        model = App
        fields = [
            'id', 'title', 'version',
            'spark_id', 'spark_title', 'spark_framework',
            'chat_id', 'conversation_id',
            'project_path', 'preview_command',
            'latest_deployment',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_spark_title(self, obj):
        return obj.spark.title if obj.spark else None

    def get_spark_framework(self, obj):
        return obj.spark.framework if obj.spark else None

    def get_conversation_id(self, obj):
        if obj.chat and obj.chat.conversation:
            return str(obj.chat.conversation.id)
        return None

    def get_latest_deployment(self, obj):
        dep = obj.spark.deployments.order_by('-created_at').first() if obj.spark else None
        if not dep:
            return None
        return {
            'id': str(dep.id),
            'status': dep.status,
            'preview_url': dep.preview_url,
            'claim_url': dep.claim_url,
        }


class AppListSerializer(serializers.ModelSerializer):
    """Lighter serializer for listing apps."""

    spark_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='spark', read_only=True)
    spark_title = serializers.SerializerMethodField()
    spark_framework = serializers.SerializerMethodField()
    chat_id: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(source='chat', read_only=True)
    conversation_id = serializers.SerializerMethodField()

    class Meta:
        model = App
        fields = [
            'id', 'title', 'version',
            'spark_id', 'spark_title', 'spark_framework',
            'chat_id', 'conversation_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_spark_title(self, obj):
        return obj.spark.title if obj.spark else None

    def get_spark_framework(self, obj):
        return obj.spark.framework if obj.spark else None

    def get_conversation_id(self, obj):
        if obj.chat and obj.chat.conversation:
            return str(obj.chat.conversation.id)
        return None
