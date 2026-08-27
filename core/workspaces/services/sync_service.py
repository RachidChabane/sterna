"""
Workspace sync service for persisting sandbox files.

This service handles:
- SAVE: Container filesystem -> PostgreSQL + R2
- RESTORE: PostgreSQL + R2 -> Container filesystem

Small files (<256KB) are stored inline in PostgreSQL.
Large files (>=256KB) are stored in Cloudflare R2.
"""
import hashlib
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, List, Optional, Set, cast
from uuid import UUID

import aiofiles  # type: ignore[import-untyped]
from pydantic import BaseModel
from django.conf import settings

from .storage.postgres import PostgresStorage
from .storage.r2 import R2Storage

logger = logging.getLogger(__name__)

# Default exclude patterns - common directories/files that shouldn't be synced
DEFAULT_EXCLUDE_PATTERNS: Set[str] = {
    # Python
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
    # Node.js
    "node_modules",
    ".npm",
    # Git
    ".git",
    # IDE/Editor
    ".idea",
    ".vscode",
    "*.swp",
    "*.swo",
    # OS
    ".DS_Store",
    "Thumbs.db",
    # Logs and temp
    "*.log",
    "*.tmp",
    # Environment
    ".env",
    ".env.local",
}


class FileInfo(BaseModel):
    """Information about a file to sync."""
    path: str
    size: int
    sha256: str
    mime_type: Optional[str] = None


class SyncResult(BaseModel):
    """Result of a sync operation."""
    success: bool
    files_synced: int
    bytes_synced: int
    files_deleted: int = 0
    files_skipped: int = 0
    errors: List[str] = []
    duration_ms: int


class WorkspaceSyncService:
    """
    Service for syncing workspace files between containers and persistent storage.

    - Small files (<256KB): stored inline in PostgreSQL
    - Large files (>=256KB): stored in Cloudflare R2
    """

    def __init__(
        self,
        postgres: PostgresStorage,
        r2: R2Storage,
        inline_threshold: Optional[int] = None,
        max_file_size: Optional[int] = None,
        max_workspace_size: Optional[int] = None,
        exclude_patterns: Optional[Set[str]] = None,
    ):
        """
        Initialize sync service.

        Args:
            postgres: PostgreSQL storage backend
            r2: R2 storage backend
            inline_threshold: Max size for inline storage (default 256KB)
            max_file_size: Max size per file (default 50MB)
            max_workspace_size: Max total workspace size (default 500MB)
            exclude_patterns: File patterns to exclude from sync
        """
        self.postgres = postgres
        self.r2 = r2

        # Configuration with defaults from Django settings or hardcoded
        self.inline_threshold: int = cast(int, inline_threshold or getattr(
            settings, 'WORKSPACE_INLINE_THRESHOLD', 256 * 1024
        ))
        self.max_file_size: int = cast(int, max_file_size or getattr(
            settings, 'WORKSPACE_MAX_FILE_SIZE', 50 * 1024 * 1024
        ))
        self.max_workspace_size: int = cast(int, max_workspace_size or getattr(
            settings, 'WORKSPACE_MAX_SIZE', 500 * 1024 * 1024
        ))
        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS

    # ─────────────────────────────────────────────────────────
    # SAVE: Container → Storage
    # ─────────────────────────────────────────────────────────

    async def save_workspace(
        self,
        user_id: UUID,
        chat_id: UUID,
        container_path: Path,
    ) -> SyncResult:
        """
        Save workspace files from container to persistent storage.

        Args:
            user_id: User UUID
            chat_id: Chat/conversation UUID
            container_path: Path to workspace directory in container

        Returns:
            SyncResult with sync statistics
        """
        start = datetime.now()
        errors: List[str] = []
        files_synced = 0
        bytes_synced = 0
        files_deleted = 0
        files_skipped = 0

        # Get or create workspace
        workspace = await self.postgres.get_or_create_workspace(
            user_id=user_id,
            chat_id=chat_id,
        )

        # Update sync state to syncing
        await self.postgres.get_or_create_sync_state(workspace.id)
        await self.postgres.update_sync_state(
            workspace_id=workspace.id,
            status='syncing',
            direction='save',
        )

        try:
            # Get existing files in storage (for diff)
            existing_files = await self.postgres.get_workspace_files(workspace.id)
            existing_by_path = {f.path: f for f in existing_files}

            # Scan container files
            container_files: List[FileInfo] = []
            total_size = 0

            if container_path.exists():
                async for file_info in self._scan_directory(container_path):
                    # Check workspace size limit
                    if total_size + file_info.size > self.max_workspace_size:
                        errors.append(
                            f"Workspace size limit ({self.max_workspace_size} bytes) exceeded"
                        )
                        break

                    container_files.append(file_info)
                    total_size += file_info.size

            container_paths = {f.path for f in container_files}

            # Delete files that no longer exist in container
            for path, existing in existing_by_path.items():
                if path not in container_paths:
                    try:
                        await self._delete_file(existing)
                        files_deleted += 1
                    except Exception as e:
                        errors.append(f"Delete {path}: {str(e)}")

            # Save new/modified files
            for file_info in container_files:
                existing_file = existing_by_path.get(file_info.path)

                # Skip if unchanged (same hash)
                if existing_file and existing_file.sha256_hash == file_info.sha256:
                    files_skipped += 1
                    continue

                try:
                    await self._save_file(
                        workspace_id=workspace.id,
                        container_path=container_path,
                        file_info=file_info,
                    )
                    files_synced += 1
                    bytes_synced += file_info.size
                except Exception as e:
                    errors.append(f"{file_info.path}: {str(e)}")
                    logger.error(f"Failed to save file {file_info.path}: {e}")

            # Update workspace stats
            await self.postgres.update_workspace_stats(workspace.id)

            # Update sync state to idle
            await self.postgres.update_sync_state(
                workspace_id=workspace.id,
                status='idle',
                direction='save',
                files_synced=files_synced,
                bytes_synced=bytes_synced,
            )

        except Exception as e:
            # Update sync state to error
            await self.postgres.update_sync_state(
                workspace_id=workspace.id,
                status='error',
                direction='save',
                error_message=str(e),
            )
            errors.append(str(e))
            logger.error(f"Workspace save failed: {e}")

        duration = int((datetime.now() - start).total_seconds() * 1000)

        result = SyncResult(
            success=len(errors) == 0,
            files_synced=files_synced,
            bytes_synced=bytes_synced,
            files_deleted=files_deleted,
            files_skipped=files_skipped,
            errors=errors,
            duration_ms=duration,
        )

        logger.info(
            f"Save workspace {workspace.id}: "
            f"{files_synced} synced, {files_skipped} skipped, {files_deleted} deleted, "
            f"{bytes_synced} bytes, {len(errors)} errors, {duration}ms"
        )

        return result

    async def _save_file(
        self,
        workspace_id: UUID,
        container_path: Path,
        file_info: FileInfo,
    ) -> None:
        """Save a single file to storage."""
        full_path = container_path / file_info.path

        async with aiofiles.open(full_path, "rb") as f:
            content = await f.read()

        if file_info.size <= self.inline_threshold:
            # Small file → PostgreSQL (inline)
            await self.postgres.upsert_file(
                workspace_id=workspace_id,
                path=file_info.path,
                filename=Path(file_info.path).name,
                mime_type=file_info.mime_type,
                size_bytes=file_info.size,
                sha256_hash=file_info.sha256,
                storage_type="inline",
                content=content,
            )
        else:
            # Large file → R2
            r2_key = f"{workspace_id}/files/{file_info.sha256}"
            await self.r2.upload(
                key=r2_key,
                content=content,
                content_type=file_info.mime_type,
            )
            await self.postgres.upsert_file(
                workspace_id=workspace_id,
                path=file_info.path,
                filename=Path(file_info.path).name,
                mime_type=file_info.mime_type,
                size_bytes=file_info.size,
                sha256_hash=file_info.sha256,
                storage_type="r2",
                r2_bucket=self.r2.bucket,
                r2_key=r2_key,
            )

    # ─────────────────────────────────────────────────────────
    # RESTORE: Storage → Container
    # ─────────────────────────────────────────────────────────

    async def restore_workspace(
        self,
        user_id: UUID,
        chat_id: UUID,
        container_path: Path,
    ) -> SyncResult:
        """
        Restore workspace files from storage to container.

        Args:
            user_id: User UUID
            chat_id: Chat/conversation UUID
            container_path: Path to workspace directory in container

        Returns:
            SyncResult with restore statistics
        """
        start = datetime.now()
        errors: List[str] = []
        files_synced = 0
        bytes_synced = 0

        # Get workspace
        workspace = await self.postgres.get_workspace(
            user_id=user_id,
            chat_id=chat_id,
        )

        if not workspace:
            # No workspace yet - nothing to restore
            return SyncResult(
                success=True,
                files_synced=0,
                bytes_synced=0,
                duration_ms=0,
            )

        # Update sync state
        await self.postgres.get_or_create_sync_state(workspace.id)
        await self.postgres.update_sync_state(
            workspace_id=workspace.id,
            status='syncing',
            direction='restore',
        )

        try:
            # Get all files
            files = await self.postgres.get_workspace_files(workspace.id)

            # Create container directory if needed
            container_path.mkdir(parents=True, exist_ok=True)

            # Restore each file
            for file in files:
                try:
                    await self._restore_file(
                        container_path=container_path,
                        file=file,
                    )
                    files_synced += 1
                    bytes_synced += file.size_bytes
                except Exception as e:
                    errors.append(f"{file.path}: {str(e)}")
                    logger.error(f"Failed to restore file {file.path}: {e}")

            # Update last accessed
            await self.postgres.touch_workspace(workspace.id)

            # Update sync state to idle
            await self.postgres.update_sync_state(
                workspace_id=workspace.id,
                status='idle',
                direction='restore',
                files_synced=files_synced,
                bytes_synced=bytes_synced,
            )

        except Exception as e:
            await self.postgres.update_sync_state(
                workspace_id=workspace.id,
                status='error',
                direction='restore',
                error_message=str(e),
            )
            errors.append(str(e))
            logger.error(f"Workspace restore failed: {e}")

        duration = int((datetime.now() - start).total_seconds() * 1000)

        result = SyncResult(
            success=len(errors) == 0,
            files_synced=files_synced,
            bytes_synced=bytes_synced,
            errors=errors,
            duration_ms=duration,
        )

        logger.info(
            f"Restore workspace {workspace.id}: "
            f"{files_synced} files, {bytes_synced} bytes, "
            f"{len(errors)} errors, {duration}ms"
        )

        return result

    async def _restore_file(
        self,
        container_path: Path,
        file,  # WorkspaceFile model instance
    ) -> None:
        """Restore a single file to container."""
        full_path = container_path / file.path

        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Get content based on storage type
        if file.storage_type == "inline":
            content = file.content
        else:
            content = await self.r2.download(file.r2_key)

        # Write file
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

    # ─────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────

    async def _scan_directory(
        self,
        base_path: Path,
    ) -> AsyncGenerator[FileInfo, None]:
        """Scan directory for files, excluding ignored patterns."""
        if not base_path.exists():
            return

        for path in base_path.rglob("*"):
            if not path.is_file():
                continue

            # Check exclusions
            rel_path = path.relative_to(base_path)
            if self._should_exclude(rel_path):
                continue

            # Check file size
            try:
                size = path.stat().st_size
            except OSError:
                continue

            if size > self.max_file_size:
                logger.warning(f"Skipping oversized file: {rel_path} ({size} bytes)")
                continue

            # Skip empty files
            if size == 0:
                continue

            # Calculate hash
            sha256 = await self._hash_file(path)

            yield FileInfo(
                path=str(rel_path),
                size=size,
                sha256=sha256,
                mime_type=self._guess_mime_type(path),
            )

    def _should_exclude(self, path: Path) -> bool:
        """Check if path matches exclusion patterns."""
        path_str = str(path)
        path_parts = path.parts

        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                # Wildcard suffix: *.pyc
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_parts:
                # Directory name match: node_modules, __pycache__
                return True

        return False

    async def _hash_file(self, path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _guess_mime_type(self, path: Path) -> Optional[str]:
        """Guess MIME type from extension."""
        mime_type, _ = mimetypes.guess_type(str(path))
        return mime_type

    async def _delete_file(self, file) -> None:
        """Delete file from storage."""
        if file.storage_type == "r2" and file.r2_key:
            await self.r2.delete(file.r2_key)
        await self.postgres.delete_file(file.id)

    # ─────────────────────────────────────────────────────────
    # WORKSPACE MANAGEMENT
    # ─────────────────────────────────────────────────────────

    async def delete_workspace(
        self,
        user_id: UUID,
        chat_id: UUID,
    ) -> bool:
        """
        Delete a workspace and all its files.

        Args:
            user_id: User UUID
            chat_id: Chat UUID

        Returns:
            True if workspace was deleted
        """
        workspace = await self.postgres.get_workspace(user_id, chat_id)
        if not workspace:
            return False

        # Get all files to delete from R2
        files = await self.postgres.get_workspace_files(workspace.id)
        for file in files:
            if file.storage_type == "r2" and file.r2_key:
                await self.r2.delete(file.r2_key)

        # Delete workspace (cascades to files and sync state)
        return await self.postgres.delete_workspace(workspace.id)

    async def get_workspace_info(
        self,
        user_id: UUID,
        chat_id: UUID,
    ) -> Optional[dict]:
        """
        Get workspace information.

        Returns:
            Dict with workspace info or None if not found
        """
        workspace = await self.postgres.get_workspace(user_id, chat_id)
        if not workspace:
            return None

        files = await self.postgres.get_workspace_files(workspace.id)
        sync_state = await self.postgres.get_sync_state(workspace.id)

        return {
            "workspace_id": str(workspace.id),
            "user_id": str(workspace.user_id),
            "chat_id": str(workspace.chat_id),
            "file_count": workspace.file_count,
            "total_size_bytes": workspace.total_size_bytes,
            "created_at": workspace.created_at.isoformat(),
            "last_accessed_at": workspace.last_accessed_at.isoformat(),
            "sync_status": sync_state.status if sync_state else "idle",
            "files": [
                {
                    "path": f.path,
                    "size_bytes": f.size_bytes,
                    "storage_type": f.storage_type,
                    "updated_at": f.updated_at.isoformat(),
                }
                for f in files
            ],
        }
