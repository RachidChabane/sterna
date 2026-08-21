"""
Storage providers for Knowledge Base documents.
Follows DRY by delegating to WorkspaceStorageService.
"""

import logging
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class StorageProvider(Protocol):
    """Protocol for storage backends (DIP - depend on abstraction)."""

    def download(self, bucket: str, key: str) -> bytes:
        """Download content from storage."""
        ...

    def upload(self, bucket: str, key: str, content: bytes) -> None:
        """Upload content to storage."""
        ...

    def delete(self, bucket: str, key: str) -> None:
        """Delete content from storage."""
        ...


class R2StorageProvider:
    """
    Cloudflare R2 storage - delegates to WorkspaceStorageService.

    DRY: Reuses existing boto3 singleton instead of creating new client.
    Pattern follows AssetStorageService (workspaces/services/asset_storage.py).
    """

    _instance: Optional['R2StorageProvider'] = None
    _initialized: bool = False

    def __new__(cls):
        """Singleton pattern to match WorkspaceStorageService."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # DRY: Reuse existing storage service (has boto3 client)
        from workspaces.services import get_storage_service
        self._workspace_storage = get_storage_service()
        self._initialized = True
        logger.info("R2StorageProvider initialized (delegating to WorkspaceStorageService)")

    def download(self, bucket: str, key: str) -> bytes:
        """Download content from R2 via WorkspaceStorageService."""
        # Note: WorkspaceStorageService uses configured bucket, but key is what matters
        content = self._workspace_storage._download_from_r2(key)
        if content is None:
            raise FileNotFoundError(f"Object not found: {key}")
        return content

    def upload(self, bucket: str, key: str, content: bytes) -> None:
        """Upload content to R2 via WorkspaceStorageService."""
        success = self._workspace_storage._upload_to_r2(key, content)
        if not success:
            raise IOError(f"Failed to upload to R2: {key}")

    def delete(self, bucket: str, key: str) -> None:
        """Delete content from R2 via WorkspaceStorageService."""
        self._workspace_storage._delete_from_r2(key)


def get_knowledge_storage() -> R2StorageProvider:
    """Factory function (DIP - allows mocking in tests)."""
    return R2StorageProvider()
