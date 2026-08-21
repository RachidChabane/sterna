"""
Asset Storage Service.

Handles storage of chat attachments (images, videos, documents)
with tiered storage:
- Small assets (<256KB): PostgreSQL inline
- Large assets (>=256KB): Cloudflare R2

R2 Path Structure for assets:
    {user_id}/chats/{chat_id}/assets/{asset_id}
"""
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional


from workspaces.models import Asset
from workspaces.services.workspace_storage import (
    StorageConfig,
    R2PathBuilder,
    get_storage_service,
)

logger = logging.getLogger(__name__)


@dataclass
class AssetStorageResult:
    """Result of an asset storage operation."""
    success: bool
    storage_type: str  # 'inline' or 'r2'
    r2_bucket: Optional[str] = None
    r2_key: Optional[str] = None
    content: Optional[bytes] = None  # Only for inline storage
    sha256_hash: Optional[str] = None
    error: Optional[str] = None


class AssetStorageService:
    """
    Storage service for conversation assets (attachments).

    Uses the same tiered storage approach as workspace files:
    - Small assets → PostgreSQL inline
    - Large assets → Cloudflare R2

    Thread-safe singleton pattern.
    """

    _instance: Optional['AssetStorageService'] = None

    def __new__(cls):
        """Singleton pattern to reuse the service instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the asset storage service."""
        if self._initialized:
            return

        # Reuse config from workspace storage
        self.config = StorageConfig.from_settings()
        # Reuse the workspace storage service for actual R2 operations
        self._workspace_storage = get_storage_service()
        self._initialized = True

        logger.info(
            f"AssetStorageService initialized: "
            f"R2 {'enabled' if self.config.r2_enabled else 'disabled'}"
        )

    def determine_storage_type(self, content_size: int) -> str:
        """
        Determine which storage backend to use based on asset size.

        Args:
            content_size: Size of the content in bytes

        Returns:
            'inline' for PostgreSQL or 'r2' for Cloudflare R2
        """
        if content_size <= self.config.inline_threshold:
            return Asset.STORAGE_INLINE

        # For large assets, only use R2 if configured
        if self.config.r2_enabled:
            return Asset.STORAGE_R2

        logger.warning(
            f"Asset size ({content_size} bytes) exceeds threshold "
            f"but R2 is not configured, storing inline"
        )
        return Asset.STORAGE_INLINE

    def generate_r2_key(
        self,
        user_id: str,
        chat_id: str,
        asset_id: str,
        asset_type: str = "file",
    ) -> str:
        """
        Generate the R2 object key for an asset.

        Args:
            user_id: User UUID (as string)
            chat_id: Chat UUID (as string)
            asset_id: Asset UUID (as string)
            asset_type: 'image', 'video', or 'file' to determine subdirectory

        Returns:
            R2 object key: {user_id}/chats/{chat_id}/{images|videos|files}/{asset_id}
        """
        if asset_type == "image":
            return R2PathBuilder.chat_image(
                user_id=str(user_id),
                chat_id=str(chat_id),
                asset_id=str(asset_id)
            )
        elif asset_type == "video":
            return R2PathBuilder.chat_video(
                user_id=str(user_id),
                chat_id=str(chat_id),
                asset_id=str(asset_id)
            )
        else:
            # Default to files for PDFs, documents, and any other type
            return R2PathBuilder.chat_file(
                user_id=str(user_id),
                chat_id=str(chat_id),
                asset_id=str(asset_id)
            )

    def store_asset(
        self,
        user_id: str,
        chat_id: str,
        asset_id: str,
        content: bytes,
        mime_type: Optional[str] = None,
        asset_type: str = "file",
    ) -> AssetStorageResult:
        """
        Store asset content in the appropriate storage backend.

        Args:
            user_id: User UUID (as string)
            chat_id: Chat UUID (as string)
            asset_id: Asset UUID (as string)
            content: Binary asset content
            mime_type: MIME type of the content
            asset_type: 'image', 'video', or 'file' to determine R2 subdirectory

        Returns:
            AssetStorageResult with storage details
        """
        content_size = len(content)
        sha256_hash = hashlib.sha256(content).hexdigest()
        storage_type = self.determine_storage_type(content_size)

        if storage_type == Asset.STORAGE_INLINE:
            return AssetStorageResult(
                success=True,
                storage_type=Asset.STORAGE_INLINE,
                content=content,
                sha256_hash=sha256_hash,
            )

        # Store in R2
        r2_key = self.generate_r2_key(user_id, chat_id, asset_id, asset_type)
        success = self._upload_to_r2(r2_key, content, mime_type)

        if success:
            logger.info(f"Stored asset in R2: {r2_key} ({content_size} bytes)")
            return AssetStorageResult(
                success=True,
                storage_type=Asset.STORAGE_R2,
                r2_bucket=self.config.bucket_name,
                r2_key=r2_key,
                content=None,
                sha256_hash=sha256_hash,
            )

        # R2 upload failed - fallback to inline
        logger.warning("R2 upload failed for asset, falling back to inline storage")
        return AssetStorageResult(
            success=True,
            storage_type=Asset.STORAGE_INLINE,
            content=content,
            sha256_hash=sha256_hash,
            error="R2 upload failed, stored inline",
        )

    def retrieve_asset(self, asset: Asset) -> Optional[bytes]:
        """
        Retrieve asset content from storage.

        Args:
            asset: Asset model instance

        Returns:
            Binary content or None if retrieval failed
        """
        if asset.storage_type == Asset.STORAGE_INLINE:
            return bytes(asset.content) if asset.content else None

        if asset.storage_type == Asset.STORAGE_R2 and asset.r2_key:
            content = self._download_from_r2(asset.r2_key)
            if content is not None:
                return content

            # R2 download failed - try inline fallback
            logger.warning(
                f"R2 download failed for asset {asset.id}, "
                f"trying inline fallback"
            )
            if asset.content:
                return bytes(asset.content)

            logger.error(f"Failed to retrieve asset {asset.id}: no content available")
            return None

        logger.warning(f"Unknown storage type for asset {asset.id}: {asset.storage_type}")
        return bytes(asset.content) if asset.content else None

    def delete_asset(self, asset: Asset) -> bool:
        """
        Delete asset content from external storage (R2).

        Note: This only deletes from R2, not from PostgreSQL.
        The caller should handle the database deletion.

        Args:
            asset: Asset model instance

        Returns:
            True if deletion successful or not needed
        """
        if asset.storage_type == Asset.STORAGE_R2 and asset.r2_key:
            return self._delete_from_r2(asset.r2_key)

        return True

    def check_duplicate(self, sha256_hash: str, user_id: str, chat_id: str) -> Optional[Asset]:
        """
        Check if an asset with the same content already exists.

        Args:
            sha256_hash: SHA256 hash of the content
            user_id: User UUID
            chat_id: Chat UUID

        Returns:
            Existing Asset if found, None otherwise
        """
        return Asset.objects.filter(
            sha256_hash=sha256_hash,
            user_id=user_id,
            chat_id=chat_id,
        ).first()

    def get_presigned_url(
        self,
        asset: Asset,
        expiration: int = 3600,
    ) -> Optional[str]:
        """
        Generate a presigned URL for direct download of an R2-stored asset.

        This is useful for large assets (especially videos) where streaming
        through the server would be inefficient.

        Args:
            asset: Asset model instance
            expiration: URL expiration in seconds (default 1 hour)

        Returns:
            Presigned URL string or None if asset is not in R2 storage
        """
        if asset.storage_type != Asset.STORAGE_R2 or not asset.r2_key:
            return None

        try:
            client = self._workspace_storage._get_r2_client()
            if not client:
                logger.warning("Cannot generate presigned URL: R2 client not available")
                return None

            url = client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.config.bucket_name,
                    'Key': asset.r2_key,
                    'ResponseContentType': asset.mime_type,
                    'ResponseContentDisposition': f'inline; filename="{asset.filename}"',
                },
                ExpiresIn=expiration,
            )
            logger.debug(f"Generated presigned URL for asset {asset.id}")
            return url

        except Exception as e:
            logger.error(f"Failed to generate presigned URL for asset {asset.id}: {e}")
            return None

    # ─────────────────────────────────────────────────────────
    # Private R2 Operations (delegated to workspace storage)
    # ─────────────────────────────────────────────────────────

    def _upload_to_r2(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None
    ) -> bool:
        """Upload content to R2 storage."""
        return self._workspace_storage._upload_to_r2(key, content, content_type)

    def _download_from_r2(self, key: str) -> Optional[bytes]:
        """Download content from R2 storage."""
        return self._workspace_storage._download_from_r2(key)

    def _delete_from_r2(self, key: str) -> bool:
        """Delete object from R2 storage."""
        return self._workspace_storage._delete_from_r2(key)


# Module-level singleton instance
def get_asset_storage_service() -> AssetStorageService:
    """Get the asset storage service singleton."""
    return AssetStorageService()
