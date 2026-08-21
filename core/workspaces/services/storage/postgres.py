"""PostgreSQL storage operations for workspaces."""
import logging
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from asgiref.sync import sync_to_async
from django.db import models

from workspaces.models import Workspace, WorkspaceFile, SyncState

logger = logging.getLogger(__name__)


class PostgresStorage:
    """PostgreSQL storage operations for workspaces."""

    @sync_to_async
    def get_or_create_workspace(
        self,
        user_id: UUID,
        chat_id: UUID,
        name: str = ""
    ) -> Workspace:
        """Get or create a workspace for user+chat."""
        workspace, created = Workspace.objects.get_or_create(
            user_id=user_id,
            chat_id=chat_id,
            defaults={"name": name}
        )
        if created:
            logger.info(f"Created workspace: {workspace.id}")
        return workspace

    @sync_to_async
    def get_workspace(
        self,
        user_id: UUID,
        chat_id: UUID
    ) -> Optional[Workspace]:
        """Get workspace by user+chat."""
        try:
            return Workspace.objects.get(user_id=user_id, chat_id=chat_id)
        except Workspace.DoesNotExist:
            return None

    @sync_to_async
    def get_workspace_by_id(self, workspace_id: UUID) -> Optional[Workspace]:
        """Get workspace by ID."""
        try:
            return Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return None

    @sync_to_async
    def get_workspace_files(self, workspace_id: UUID) -> List[WorkspaceFile]:
        """Get all files in a workspace."""
        return list(WorkspaceFile.objects.filter(workspace_id=workspace_id))

    @sync_to_async
    def get_file_by_path(
        self,
        workspace_id: UUID,
        path: str
    ) -> Optional[WorkspaceFile]:
        """Get a specific file by path."""
        try:
            return WorkspaceFile.objects.get(workspace_id=workspace_id, path=path)
        except WorkspaceFile.DoesNotExist:
            return None

    @sync_to_async
    def upsert_file(
        self,
        workspace_id: UUID,
        path: str,
        filename: str,
        size_bytes: int,
        sha256_hash: str,
        storage_type: str,
        mime_type: Optional[str] = None,
        content: Optional[bytes] = None,
        r2_bucket: Optional[str] = None,
        r2_key: Optional[str] = None,
    ) -> WorkspaceFile:
        """Create or update a file in workspace."""
        file, created = WorkspaceFile.objects.update_or_create(
            workspace_id=workspace_id,
            path=path,
            defaults={
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "sha256_hash": sha256_hash,
                "storage_type": storage_type,
                "content": content,
                "r2_bucket": r2_bucket,
                "r2_key": r2_key,
            }
        )
        action = "Created" if created else "Updated"
        logger.debug(f"{action} file: {path} ({size_bytes} bytes)")
        return file

    @sync_to_async
    def delete_file(self, file_id: UUID) -> bool:
        """Delete a file by ID."""
        try:
            deleted, _ = WorkspaceFile.objects.filter(id=file_id).delete()
            return deleted > 0
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False

    @sync_to_async
    def delete_files_by_paths(
        self,
        workspace_id: UUID,
        paths: List[str]
    ) -> int:
        """Delete multiple files by paths."""
        count, _ = WorkspaceFile.objects.filter(
            workspace_id=workspace_id,
            path__in=paths
        ).delete()
        return count

    @sync_to_async
    def update_workspace_stats(self, workspace_id: UUID) -> None:
        """Update workspace statistics."""
        try:
            workspace = Workspace.objects.get(id=workspace_id)
            workspace.update_stats()
        except Workspace.DoesNotExist:
            logger.warning(f"Workspace {workspace_id} not found for stats update")

    @sync_to_async
    def touch_workspace(self, workspace_id: UUID) -> None:
        """Update last_accessed_at timestamp."""
        Workspace.objects.filter(id=workspace_id).update(
            last_accessed_at=datetime.now()
        )

    @sync_to_async
    def delete_workspace(self, workspace_id: UUID) -> bool:
        """Delete a workspace and all its files."""
        try:
            deleted, _ = Workspace.objects.filter(id=workspace_id).delete()
            return deleted > 0
        except Exception as e:
            logger.error(f"Failed to delete workspace {workspace_id}: {e}")
            return False

    # Sync state methods

    @sync_to_async
    def get_or_create_sync_state(self, workspace_id: UUID) -> SyncState:
        """Get or create sync state for workspace."""
        state, _ = SyncState.objects.get_or_create(workspace_id=workspace_id)
        return state

    @sync_to_async
    def get_sync_state(self, workspace_id: UUID) -> Optional[SyncState]:
        """Get sync state for workspace."""
        try:
            return SyncState.objects.get(workspace_id=workspace_id)
        except SyncState.DoesNotExist:
            return None

    @sync_to_async
    def update_sync_state(
        self,
        workspace_id: UUID,
        status: str,
        direction: Optional[str] = None,
        files_total: int = 0,
        files_synced: int = 0,
        bytes_total: int = 0,
        bytes_synced: int = 0,
        error_message: Optional[str] = None,
    ) -> Optional[SyncState]:
        """Update sync state."""
        try:
            state = SyncState.objects.get(workspace_id=workspace_id)
        except SyncState.DoesNotExist:
            # Create if doesn't exist
            state = SyncState(workspace_id=workspace_id)

        state.status = status
        state.direction = direction
        state.files_total = files_total
        state.files_synced = files_synced
        state.bytes_total = bytes_total
        state.bytes_synced = bytes_synced
        state.error_message = error_message

        if status == SyncState.STATUS_SYNCING:
            state.started_at = datetime.now()
            state.completed_at = None
        elif status in (SyncState.STATUS_IDLE, SyncState.STATUS_ERROR):
            state.completed_at = datetime.now()

        state.save()
        return state

    @sync_to_async
    def increment_sync_progress(
        self,
        workspace_id: UUID,
        files_synced: int = 0,
        bytes_synced: int = 0,
    ) -> None:
        """Increment sync progress counters."""
        SyncState.objects.filter(workspace_id=workspace_id).update(
            files_synced=models.F('files_synced') + files_synced,
            bytes_synced=models.F('bytes_synced') + bytes_synced,
        )

    # Utility methods

    @sync_to_async
    def get_user_workspaces(self, user_id: UUID) -> List[Workspace]:
        """Get all workspaces for a user."""
        return list(Workspace.objects.filter(user_id=user_id))

    @sync_to_async
    def get_workspaces_older_than(self, days: int) -> List[Workspace]:
        """Get workspaces not accessed in N days (for cleanup)."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        return list(Workspace.objects.filter(last_accessed_at__lt=cutoff))

    @sync_to_async
    def get_total_storage_for_user(self, user_id: UUID) -> int:
        """Get total storage used by a user across all workspaces."""
        from django.db.models import Sum
        result = Workspace.objects.filter(user_id=user_id).aggregate(
            total=Sum('total_size_bytes')
        )
        return result['total'] or 0
