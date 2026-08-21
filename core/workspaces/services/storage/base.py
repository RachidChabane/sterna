"""Abstract base class for storage backends."""
from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """Abstract base class for file storage backends."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload content to storage.

        Args:
            key: Storage key/path for the content
            content: Binary content to upload
            content_type: Optional MIME type

        Returns:
            The storage key where content was stored
        """
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """
        Download content from storage.

        Args:
            key: Storage key/path to download

        Returns:
            Binary content
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete content from storage.

        Args:
            key: Storage key/path to delete

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if content exists at key.

        Args:
            key: Storage key/path to check

        Returns:
            True if content exists
        """
        pass
