"""Serializers for workspace API."""
from django.conf import settings
from rest_framework import serializers
from workspaces.models import Workspace, WorkspaceFile, SyncState, Asset, AssetShareLink


class WorkspaceFileSerializer(serializers.ModelSerializer):
    """Serializer for workspace file info (without content)."""

    class Meta:
        model = WorkspaceFile
        fields = [
            'id', 'path', 'filename', 'mime_type', 'size_bytes',
            'storage_type', 'sha256_hash', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class SyncStateSerializer(serializers.ModelSerializer):
    """Serializer for sync state."""
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = SyncState
        fields = [
            'id', 'status', 'direction', 'files_total', 'files_synced',
            'bytes_total', 'bytes_synced', 'started_at', 'completed_at',
            'error_message', 'retry_count', 'progress_percent'
        ]
        read_only_fields = fields


class WorkspaceSerializer(serializers.ModelSerializer):
    """Serializer for workspace info."""
    files = WorkspaceFileSerializer(many=True, read_only=True)
    sync_state = SyncStateSerializer(read_only=True)
    chat_id = serializers.UUIDField(source='chat_id', read_only=True)

    class Meta:
        model = Workspace
        fields = [
            'id', 'user_id', 'chat_id', 'name', 'total_size_bytes',
            'file_count', 'created_at', 'updated_at', 'last_accessed_at',
            'files', 'sync_state'
        ]
        read_only_fields = fields


class WorkspaceSaveRequestSerializer(serializers.Serializer):
    """Request serializer for saving workspace files."""
    user_id = serializers.UUIDField()
    chat_id = serializers.UUIDField()
    files = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of files: [{'path': str, 'content_base64': str, 'size': int, 'sha256': str}]"
    )


class WorkspaceRestoreResponseSerializer(serializers.Serializer):
    """Response serializer for restore operation."""
    success = serializers.BooleanField()
    files = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of files with content: [{'path': str, 'content_base64': str}]"
    )
    duration_ms = serializers.IntegerField()
    error = serializers.CharField(required=False, allow_null=True)


class SyncResultSerializer(serializers.Serializer):
    """Serializer for sync operation result."""
    success = serializers.BooleanField()
    files_synced = serializers.IntegerField()
    bytes_synced = serializers.IntegerField()
    files_deleted = serializers.IntegerField(required=False, default=0)
    files_skipped = serializers.IntegerField(required=False, default=0)
    # Field name shadows Serializer.errors (a ReturnDict property on the base
    # class); DRF's metaclass extracts declared fields out of the class body
    # before that property resolves, so this works correctly at runtime.
    errors = serializers.ListField(child=serializers.CharField(), required=False, default=[])  # type: ignore[assignment]
    duration_ms = serializers.IntegerField()


# ─────────────────────────────────────────────────────────
# Asset Serializers (for conversation attachments)
# ─────────────────────────────────────────────────────────

class AssetSerializer(serializers.ModelSerializer):
    """Serializer for asset metadata (without binary content)."""
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            'id', 'asset_type', 'filename', 'mime_type', 'size_bytes',
            'storage_type', 'width', 'height', 'duration_seconds',
            'sha256_hash', 'created_at', 'download_url',
            'generation_prompt', 'generation_model',
        ]
        read_only_fields = fields

    def get_download_url(self, obj: Asset) -> str:
        """Generate download URL for the asset."""
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/api/workspaces/assets/{obj.id}/download/')
        return f'/api/workspaces/assets/{obj.id}/download/'


class AssetUploadSerializer(serializers.Serializer):
    """
    Serializer for asset upload request.

    Includes validation for:
    - File size limits (configurable per asset type)
    - Filename sanitization
    - Base64 content format
    """
    # Maximum file sizes in bytes
    MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB for images
    MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500MB for videos
    MAX_FILE_SIZE = 100 * 1024 * 1024   # 100MB for other files

    chat_id = serializers.UUIDField()
    message_id = serializers.UUIDField(required=False, allow_null=True)
    filename = serializers.CharField(max_length=255)
    mime_type = serializers.CharField(max_length=127)
    asset_type = serializers.ChoiceField(
        choices=Asset.TYPE_CHOICES,
        default=Asset.TYPE_IMAGE
    )
    content_base64 = serializers.CharField(
        help_text="Base64-encoded file content"
    )
    # Optional media metadata
    width = serializers.IntegerField(required=False, allow_null=True)
    height = serializers.IntegerField(required=False, allow_null=True)
    duration_seconds = serializers.FloatField(required=False, allow_null=True)
    # For AI-generated assets
    generation_prompt = serializers.CharField(required=False, allow_null=True)
    generation_model = serializers.CharField(required=False, allow_null=True, max_length=255)

    def validate_filename(self, value):
        """Sanitize filename to prevent security issues."""
        from security import sanitize_filename
        return sanitize_filename(value)

    def validate_content_base64(self, value):
        """
        Validate base64 content and check size limits.

        This pre-validates the base64 string and checks estimated size
        before full decoding to prevent memory exhaustion attacks.
        """
        import base64

        # Estimate decoded size (base64 is ~4/3 of original)
        # Add some margin for padding
        estimated_size = len(value) * 3 // 4

        # Quick size check before decoding
        # Use the largest limit + margin for initial check
        max_estimated = self.MAX_VIDEO_SIZE + 1024 * 1024  # Add 1MB margin
        if estimated_size > max_estimated:
            raise serializers.ValidationError(
                f"File too large. Maximum size is {self.MAX_VIDEO_SIZE // (1024*1024)}MB for videos."
            )

        # Validate base64 format
        try:
            # Check for valid base64 characters
            if not value.replace('+', '').replace('/', '').replace('=', '').isalnum():
                # Try to decode anyway in case of data URL format
                if ',' in value:
                    value = value.split(',', 1)[1]  # Strip data URL prefix

            # Try partial decode to validate format
            base64.b64decode(value[:1000] if len(value) > 1000 else value)
        except Exception:
            raise serializers.ValidationError("Invalid base64 encoding")

        return value

    def validate(self, attrs):
        """Cross-field validation including size limits based on asset type."""
        import base64

        content_b64 = attrs.get('content_base64', '')
        asset_type = attrs.get('asset_type', Asset.TYPE_IMAGE)

        # Determine size limit based on asset type
        if asset_type == Asset.TYPE_VIDEO:
            max_size = self.MAX_VIDEO_SIZE
            size_desc = f"{self.MAX_VIDEO_SIZE // (1024*1024)}MB"
        elif asset_type in (Asset.TYPE_IMAGE, Asset.TYPE_GENERATED):
            max_size = self.MAX_IMAGE_SIZE
            size_desc = f"{self.MAX_IMAGE_SIZE // (1024*1024)}MB"
        else:
            max_size = self.MAX_FILE_SIZE
            size_desc = f"{self.MAX_FILE_SIZE // (1024*1024)}MB"

        # Calculate actual decoded size
        try:
            # Handle data URL format if present
            if ',' in content_b64:
                content_b64 = content_b64.split(',', 1)[1]
                attrs['content_base64'] = content_b64

            decoded_size = len(base64.b64decode(content_b64))
            if decoded_size > max_size:
                raise serializers.ValidationError({
                    'content_base64': f"File too large ({decoded_size // (1024*1024)}MB). "
                                      f"Maximum size for {asset_type} is {size_desc}."
                })
        except serializers.ValidationError:
            raise
        except Exception:
            raise serializers.ValidationError({
                'content_base64': "Invalid base64 content"
            })

        return attrs


class AssetUploadResponseSerializer(serializers.Serializer):
    """Response serializer for asset upload."""
    success = serializers.BooleanField()
    asset = AssetSerializer(required=False)
    error = serializers.CharField(required=False, allow_null=True)


class GalleryAssetSerializer(AssetSerializer):
    """Asset serializer with chat context for gallery display."""
    chat_id = serializers.UUIDField(source='chat.id', read_only=True)
    chat_name = serializers.SerializerMethodField()
    conversation_id = serializers.SerializerMethodField()
    generation_model_display_name = serializers.SerializerMethodField()

    class Meta(AssetSerializer.Meta):
        fields = AssetSerializer.Meta.fields + [
            'chat_id', 'chat_name', 'conversation_id', 'generation_model_display_name'
        ]

    def get_chat_name(self, obj: Asset) -> str | None:
        """Get a display name for the chat (from conversation or model)."""
        if obj.chat and obj.chat.conversation:
            return obj.chat.conversation.name
        return None

    def get_conversation_id(self, obj: Asset) -> str | None:
        """Get the parent conversation ID for navigation."""
        # conversation_id is Chat's runtime shadow attribute for its
        # conversation FK (conversations.models.Chat, outside this app).
        if obj.chat and obj.chat.conversation_id:  # type: ignore[attr-defined]
            return str(obj.chat.conversation_id)  # type: ignore[attr-defined]
        return None

    def get_generation_model_display_name(self, obj: Asset) -> str | None:
        """
        Look up the display name for the generation model from the database catalogs.
        Uses VideoModelCatalog for videos and ImageModelCatalog for images.
        Falls back to formatting the model ID if not found.
        """
        if not obj.generation_model:
            return None

        model_id = obj.generation_model

        # Normalize model ID: strip "openrouter/" prefix if present
        # (legacy assets may have this prefix from old code)
        canonical_id = model_id
        if model_id.startswith("openrouter/"):
            canonical_id = model_id[len("openrouter/"):]

        # Check if it's a video asset - look in VideoModelCatalog
        if obj.asset_type == Asset.TYPE_VIDEO or (
            obj.mime_type and obj.mime_type.startswith('video/')
        ):
            from llm.models import VideoModelCatalog
            try:
                # Try both original and normalized ID
                video_model = VideoModelCatalog.objects.filter(
                    canonical_id__in=[model_id, canonical_id]
                ).first()
                if video_model:
                    return video_model.display_name
            except Exception:
                pass

        # Check ImageModelCatalog for images
        if obj.asset_type in (Asset.TYPE_IMAGE, Asset.TYPE_GENERATED) or (
            obj.mime_type and obj.mime_type.startswith('image/')
        ):
            from llm.models import ImageModelCatalog
            try:
                # Try both original and normalized ID
                image_model = ImageModelCatalog.objects.filter(
                    model_id__in=[model_id, canonical_id]
                ).first()
                if image_model:
                    return image_model.name
            except Exception:
                pass

        # Fallback: format the model ID nicely
        name = canonical_id.split('/')[-1] if '/' in canonical_id else canonical_id
        return name.replace('-', ' ').replace('_', ' ').title()


# ─────────────────────────────────────────────────────────
# Share Link Serializers
# ─────────────────────────────────────────────────────────

class AssetShareLinkSerializer(serializers.ModelSerializer):
    """Serializer for share link metadata."""

    share_url = serializers.SerializerMethodField()
    asset_type = serializers.CharField(source='asset.asset_type', read_only=True)
    asset_filename = serializers.CharField(source='asset.filename', read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)
    # Field name shadows BaseSerializer.is_valid() (a method on the base
    # class); DRF's metaclass extracts declared fields out of the class body
    # before that method resolves, so this works correctly at runtime.
    is_valid = serializers.BooleanField(read_only=True)  # type: ignore[assignment]

    class Meta:
        model = AssetShareLink
        fields = [
            'id',
            'token',
            'share_url',
            'asset_id',
            'asset_type',
            'asset_filename',
            'thumbnail_url',
            'is_active',
            'expires_at',
            'view_count',
            'last_viewed_at',
            'custom_title',
            'created_at',
            'is_expired',
            'is_valid',
        ]
        read_only_fields = [
            'id', 'token', 'share_url', 'view_count',
            'last_viewed_at', 'created_at', 'is_expired', 'is_valid'
        ]

    def get_share_url(self, obj: AssetShareLink) -> str:
        """Generate the full share URL."""
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
        return f"{base_url}/share/{obj.token}/"

    def get_thumbnail_url(self, obj: AssetShareLink) -> str | None:
        """Get thumbnail URL for the asset."""
        request = self.context.get('request')
        if obj.asset.thumbnail_id:
            if request:
                return request.build_absolute_uri(
                    f'/api/workspaces/assets/{obj.asset.thumbnail_id}/download/'
                )
            return f'/api/workspaces/assets/{obj.asset.thumbnail_id}/download/'
        return None


class CreateShareLinkSerializer(serializers.Serializer):
    """Request serializer for creating a share link."""

    expires_in_hours = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=8760,  # 1 year max
        help_text="Hours until link expires (optional)"
    )
    custom_title = serializers.CharField(
        required=False,
        max_length=255,
        allow_blank=True,
        help_text="Custom title for social media previews"
    )
    watermark_enabled = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Whether to apply watermark to shared images"
    )
    watermark_position = serializers.ChoiceField(
        required=False,
        choices=['bottom-right', 'bottom-left', 'top-right', 'top-left'],
        default='bottom-right',
        help_text="Position of watermark on image"
    )


class ShareLinkListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing share links."""

    share_url = serializers.SerializerMethodField()
    asset_preview = serializers.SerializerMethodField()

    class Meta:
        model = AssetShareLink
        fields = [
            'id',
            'token',
            'share_url',
            'asset_id',
            'asset_preview',
            'view_count',
            'expires_at',
            'is_active',
            'created_at',
        ]

    def get_share_url(self, obj: AssetShareLink) -> str:
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
        return f"{base_url}/share/{obj.token}/"

    def get_asset_preview(self, obj: AssetShareLink) -> dict:
        return {
            'type': obj.asset.asset_type,
            'filename': obj.asset.filename,
            'prompt': (obj.asset.generation_prompt or '')[:100],
            'model': obj.asset.generation_model,
        }
