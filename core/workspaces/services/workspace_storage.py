"""
Unified Workspace Storage Service.

Provides a clean interface for storing workspace files with automatic
tiered storage:
- Small files (<256KB): PostgreSQL (inline)
- Large files (>=256KB): Cloudflare R2

This service is used by the workspace API views and handles all storage
operations including uploads, downloads, and deletions.

R2 Path Structure:
    {user_id}/chats/{chat_id}/ide-files/{sha256_hash}

    Hierarchy rationale:
    - user_id first: Clear user isolation (GDPR deletion, browsability)
    - chats/: Context type (future: projects/, etc.)
    - chat_id: Context unit identifier
    - ide-files/: Resource type (future: assets/ for images/videos)
    - sha256_hash: Content-addressable for deduplication within chat

Environment Configuration:
- Dev: Can use MinIO via R2_ENDPOINT_URL=http://minio:9000
- Staging/Production: Uses Cloudflare R2 via R2_ACCOUNT_ID

Required settings (from Django settings, populated via environment):
- R2_ACCOUNT_ID: Cloudflare account ID
- R2_ACCESS_KEY_ID: R2 access key
- R2_SECRET_ACCESS_KEY: R2 secret key
- R2_BUCKET_NAME: R2 bucket name (default: sterna-workspaces)
- R2_ENDPOINT_URL: Custom endpoint for MinIO in dev (optional)
- WORKSPACE_INLINE_THRESHOLD: Max size for inline storage (default: 256KB)
"""
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from django.conf import settings

from workspaces.models import WorkspaceFile

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Storage configuration loaded from Django settings."""
    # R2/S3 settings
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    endpoint_url: str

    # Thresholds
    inline_threshold: int  # Max bytes for inline PostgreSQL storage

    @classmethod
    def from_settings(cls) -> 'StorageConfig':
        """Load configuration from Django settings."""
        return cls(
            account_id=getattr(settings, 'R2_ACCOUNT_ID', ''),
            access_key_id=getattr(settings, 'R2_ACCESS_KEY_ID', ''),
            secret_access_key=getattr(settings, 'R2_SECRET_ACCESS_KEY', ''),
            bucket_name=getattr(settings, 'R2_BUCKET_NAME', 'sterna-workspaces'),
            endpoint_url=getattr(settings, 'R2_ENDPOINT_URL', ''),
            inline_threshold=getattr(settings, 'WORKSPACE_INLINE_THRESHOLD', 256 * 1024),
        )

    @property
    def r2_enabled(self) -> bool:
        """Check if R2 storage is properly configured."""
        return bool(self.access_key_id and self.secret_access_key and
                    (self.endpoint_url or self.account_id))

    @property
    def effective_endpoint_url(self) -> Optional[str]:
        """Get the effective endpoint URL for R2/S3."""
        if self.endpoint_url:
            return self.endpoint_url
        if self.account_id:
            return f"https://{self.account_id}.r2.cloudflarestorage.com"
        return None


@dataclass
class StorageResult:
    """Result of a storage operation."""
    success: bool
    storage_type: str  # 'inline' or 'r2'
    r2_bucket: Optional[str] = None
    r2_key: Optional[str] = None
    content: Optional[bytes] = None  # Only for inline storage
    error: Optional[str] = None


class R2PathBuilder:
    """
    Centralized R2 path construction.

    Path structure:
        {user_id}/{context_type}/{context_id}/{resource_type}/{identifier}

    Examples:
        - IDE files: {user_id}/chats/{chat_id}/ide-files/{sha256_hash}
        - Images: {user_id}/chats/{chat_id}/assets/images/{asset_id}
        - Videos: {user_id}/chats/{chat_id}/assets/videos/{asset_id}
        - Files: {user_id}/chats/{chat_id}/assets/files/{asset_id}
        - Future: {user_id}/projects/{project_id}/ide-files/{sha256_hash}
    """

    # Context types
    CONTEXT_CHATS = "chats"
    CONTEXT_PROFILE = "profile"
    # Future: CONTEXT_PROJECTS = "projects"

    # Resource types
    RESOURCE_IDE_FILES = "ide-files"
    RESOURCE_ASSETS = "assets"
    # Asset subtypes (under assets/)
    RESOURCE_IMAGES = "assets/images"
    RESOURCE_VIDEOS = "assets/videos"
    RESOURCE_FILES = "assets/files"
    # Profile resources
    RESOURCE_AVATAR = "avatar"

    @classmethod
    def chat_ide_file(cls, user_id: str, chat_id: str, sha256_hash: str) -> str:
        """
        Build R2 key for an IDE file in a chat context.

        Args:
            user_id: User UUID (string)
            chat_id: Chat UUID (string)
            sha256_hash: SHA256 hash of file content

        Returns:
            R2 object key: {user_id}/chats/{chat_id}/ide-files/{sha256_hash}
        """
        return f"{user_id}/{cls.CONTEXT_CHATS}/{chat_id}/{cls.RESOURCE_IDE_FILES}/{sha256_hash}"

    @classmethod
    def chat_asset(cls, user_id: str, chat_id: str, asset_id: str) -> str:
        """
        Build R2 key for a media asset in a chat context (legacy, use chat_image/chat_video).

        Args:
            user_id: User UUID (string)
            chat_id: Chat UUID (string)
            asset_id: Asset UUID (string)

        Returns:
            R2 object key: {user_id}/chats/{chat_id}/assets/{asset_id}
        """
        return f"{user_id}/{cls.CONTEXT_CHATS}/{chat_id}/{cls.RESOURCE_ASSETS}/{asset_id}"

    @classmethod
    def chat_image(cls, user_id: str, chat_id: str, asset_id: str) -> str:
        """
        Build R2 key for an image asset in a chat context.

        Args:
            user_id: User UUID (string)
            chat_id: Chat UUID (string)
            asset_id: Asset UUID (string)

        Returns:
            R2 object key: {user_id}/chats/{chat_id}/assets/images/{asset_id}
        """
        return f"{user_id}/{cls.CONTEXT_CHATS}/{chat_id}/{cls.RESOURCE_IMAGES}/{asset_id}"

    @classmethod
    def chat_video(cls, user_id: str, chat_id: str, asset_id: str) -> str:
        """
        Build R2 key for a video asset in a chat context.

        Args:
            user_id: User UUID (string)
            chat_id: Chat UUID (string)
            asset_id: Asset UUID (string)

        Returns:
            R2 object key: {user_id}/chats/{chat_id}/assets/videos/{asset_id}
        """
        return f"{user_id}/{cls.CONTEXT_CHATS}/{chat_id}/{cls.RESOURCE_VIDEOS}/{asset_id}"

    @classmethod
    def chat_file(cls, user_id: str, chat_id: str, asset_id: str) -> str:
        """
        Build R2 key for a general file asset (PDFs, documents, etc.) in a chat context.

        Args:
            user_id: User UUID (string)
            chat_id: Chat UUID (string)
            asset_id: Asset UUID (string)

        Returns:
            R2 object key: {user_id}/chats/{chat_id}/assets/files/{asset_id}
        """
        return f"{user_id}/{cls.CONTEXT_CHATS}/{chat_id}/{cls.RESOURCE_FILES}/{asset_id}"

    @classmethod
    def user_avatar(cls, user_id: str) -> str:
        """
        Build R2 key for a user's profile avatar.

        Args:
            user_id: User UUID (string)

        Returns:
            R2 object key: {user_id}/profile/avatar
        """
        return f"{user_id}/{cls.CONTEXT_PROFILE}/{cls.RESOURCE_AVATAR}"

    @classmethod
    def parse_key(cls, key: str) -> Optional[dict]:
        """
        Parse an R2 key back into its components.

        Args:
            key: R2 object key

        Returns:
            Dict with user_id, context_type, context_id, resource_type, identifier
            or None if parsing fails
        """
        parts = key.split("/")
        if len(parts) != 5:
            return None

        return {
            "user_id": parts[0],
            "context_type": parts[1],
            "context_id": parts[2],
            "resource_type": parts[3],
            "identifier": parts[4],
        }

    @classmethod
    def user_prefix(cls, user_id: str) -> str:
        """Get prefix for all user data (useful for GDPR deletion)."""
        return f"{user_id}/"

    @classmethod
    def chat_prefix(cls, user_id: str, chat_id: str) -> str:
        """Get prefix for all data in a chat."""
        return f"{user_id}/{cls.CONTEXT_CHATS}/{chat_id}/"


class WorkspaceStorageService:
    """
    Unified storage service for workspace files.

    Automatically routes files to appropriate storage:
    - Small files → PostgreSQL inline
    - Large files → Cloudflare R2

    Thread-safe singleton pattern for the boto3 client.
    """

    _instance: Optional['WorkspaceStorageService'] = None
    _r2_client = None

    def __new__(cls):
        """Singleton pattern to reuse the service instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the storage service."""
        if self._initialized:
            return

        self.config = StorageConfig.from_settings()
        self._initialized = True

        # Log configuration status
        if self.config.r2_enabled:
            logger.info(
                f"WorkspaceStorageService initialized: R2 enabled "
                f"(bucket={self.config.bucket_name}, "
                f"endpoint={self.config.effective_endpoint_url})"
            )
        else:
            logger.warning(
                "WorkspaceStorageService initialized: R2 disabled "
                "(missing credentials), large files will be stored inline"
            )

    def _get_r2_client(self):
        """Get or create the R2/S3 client (lazy initialization)."""
        if self._r2_client is not None:
            return self._r2_client

        if not self.config.r2_enabled:
            return None

        try:
            self._r2_client = boto3.client(
                's3',
                endpoint_url=self.config.effective_endpoint_url,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
                config=Config(
                    signature_version='s3v4',
                    retries={'max_attempts': 3, 'mode': 'adaptive'},
                ),
            )
            logger.debug(f"R2 client created: {self.config.effective_endpoint_url}")
            return self._r2_client
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"Failed to create R2 client: {e}")
            return None

    def determine_storage_type(self, content_size: int) -> str:
        """
        Determine which storage backend to use based on file size.

        Args:
            content_size: Size of the content in bytes

        Returns:
            'inline' for PostgreSQL or 'r2' for Cloudflare R2
        """
        if content_size <= self.config.inline_threshold:
            return WorkspaceFile.STORAGE_INLINE

        # For large files, only use R2 if it's configured
        if self.config.r2_enabled:
            return WorkspaceFile.STORAGE_R2

        # Fallback to inline if R2 is not configured
        logger.warning(
            f"File size ({content_size} bytes) exceeds threshold "
            f"but R2 is not configured, storing inline"
        )
        return WorkspaceFile.STORAGE_INLINE

    def generate_r2_key(
        self,
        user_id: str,
        chat_id: str,
        sha256_hash: str
    ) -> str:
        """
        Generate the R2 object key for an IDE file.

        Uses R2PathBuilder for centralized path construction.

        Args:
            user_id: User UUID (as string)
            chat_id: Chat UUID (as string)
            sha256_hash: SHA256 hash of the file content

        Returns:
            R2 object key: {user_id}/chats/{chat_id}/ide-files/{sha256_hash}
        """
        return R2PathBuilder.chat_ide_file(
            user_id=str(user_id),
            chat_id=str(chat_id),
            sha256_hash=sha256_hash
        )

    def store_file(
        self,
        user_id: str,
        chat_id: str,
        content: bytes,
        content_hash: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> StorageResult:
        """
        Store file content in the appropriate storage backend.

        Args:
            user_id: User UUID (as string)
            chat_id: Chat UUID (as string)
            content: Binary file content
            content_hash: Pre-computed SHA256 hash (computed if not provided)
            mime_type: MIME type of the content

        Returns:
            StorageResult with storage details
        """
        # Compute hash if not provided
        if not content_hash:
            content_hash = hashlib.sha256(content).hexdigest()

        content_size = len(content)
        storage_type = self.determine_storage_type(content_size)

        if storage_type == WorkspaceFile.STORAGE_INLINE:
            # Store inline in PostgreSQL
            return StorageResult(
                success=True,
                storage_type=WorkspaceFile.STORAGE_INLINE,
                content=content,
            )

        # Store in R2
        r2_key = self.generate_r2_key(user_id, chat_id, content_hash)
        success = self._upload_to_r2(r2_key, content, mime_type)

        if success:
            return StorageResult(
                success=True,
                storage_type=WorkspaceFile.STORAGE_R2,
                r2_bucket=self.config.bucket_name,
                r2_key=r2_key,
                content=None,  # Don't store content inline when using R2
            )

        # R2 upload failed - fallback to inline
        logger.warning("R2 upload failed, falling back to inline storage")
        return StorageResult(
            success=True,  # Still successful, just using different storage
            storage_type=WorkspaceFile.STORAGE_INLINE,
            content=content,
            error="R2 upload failed, stored inline",
        )

    def retrieve_file(self, file: WorkspaceFile) -> Optional[bytes]:
        """
        Retrieve file content from storage.

        Args:
            file: WorkspaceFile model instance

        Returns:
            Binary content or None if retrieval failed
        """
        if file.storage_type == WorkspaceFile.STORAGE_INLINE:
            return file.content

        if file.storage_type == WorkspaceFile.STORAGE_R2 and file.r2_key:
            content = self._download_from_r2(file.r2_key)
            if content is not None:
                return content

            # R2 download failed - try inline fallback
            logger.warning(
                f"R2 download failed for {file.path}, "
                f"trying inline fallback"
            )
            if file.content:
                return file.content

            logger.error(f"Failed to retrieve file {file.path}: no content available")
            return None

        # Unknown storage type or missing R2 key
        logger.warning(f"Unknown storage type for {file.path}: {file.storage_type}")
        return file.content

    def delete_file(self, file: WorkspaceFile) -> bool:
        """
        Delete file content from external storage (R2).

        Note: This only deletes from R2, not from PostgreSQL.
        The caller should handle the database deletion.

        Args:
            file: WorkspaceFile model instance

        Returns:
            True if deletion successful or not needed
        """
        if file.storage_type == WorkspaceFile.STORAGE_R2 and file.r2_key:
            return self._delete_from_r2(file.r2_key)

        # Nothing to delete from external storage
        return True

    # ─────────────────────────────────────────────────────────
    # Private R2 Operations
    # ─────────────────────────────────────────────────────────

    def _upload_to_r2(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None
    ) -> bool:
        """Upload content to R2 storage."""
        client = self._get_r2_client()
        if not client:
            return False

        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            client.put_object(
                Bucket=self.config.bucket_name,
                Key=key,
                Body=content,
                **extra_args,
            )
            logger.info(f"Uploaded to R2: {key} ({len(content)} bytes)")
            return True
        except ClientError as e:
            logger.error(f"R2 upload failed: {key} - {e}")
            return False

    def _download_from_r2(self, key: str) -> Optional[bytes]:
        """Download content from R2 storage."""
        client = self._get_r2_client()
        if not client:
            return None

        try:
            response = client.get_object(
                Bucket=self.config.bucket_name,
                Key=key
            )
            content = response['Body'].read()
            logger.debug(f"Downloaded from R2: {key} ({len(content)} bytes)")
            return content
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                logger.warning(f"R2 object not found: {key}")
            else:
                logger.error(f"R2 download failed: {key} - {e}")
            return None

    def _delete_from_r2(self, key: str) -> bool:
        """Delete object from R2 storage."""
        client = self._get_r2_client()
        if not client:
            return False

        try:
            client.delete_object(
                Bucket=self.config.bucket_name,
                Key=key
            )
            logger.debug(f"Deleted from R2: {key}")
            return True
        except ClientError as e:
            logger.error(f"R2 delete failed: {key} - {e}")
            return False

    def check_r2_connection(self) -> Tuple[bool, str]:
        """
        Check if R2 connection is working.

        Returns:
            Tuple of (success, message)
        """
        if not self.config.r2_enabled:
            return False, "R2 not configured (missing credentials)"

        client = self._get_r2_client()
        if not client:
            return False, "Failed to create R2 client"

        try:
            # Try to list objects (with limit 1) to verify connection
            client.list_objects_v2(
                Bucket=self.config.bucket_name,
                MaxKeys=1
            )
            return True, f"R2 connection successful (bucket: {self.config.bucket_name})"
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            return False, f"R2 connection failed: {error_code}"


# Module-level singleton instance for easy import
def get_storage_service() -> WorkspaceStorageService:
    """Get the workspace storage service singleton."""
    return WorkspaceStorageService()
