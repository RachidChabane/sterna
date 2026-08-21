"""
File Version Service

Manages file version lifecycle including creation, retrieval, comparison, and cleanup.
Uses content-addressable storage for deduplication with the same tiered storage
pattern as WorkspaceFile (inline for small files, R2 for large files).
"""

import hashlib
import logging
import mimetypes
import os
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)


# Binary file detection by extension
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp', '.svg',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.rar', '.7z',
    '.exe', '.dll', '.so', '.dylib',
    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.webm',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.pyc', '.pyo', '.class', '.o',
}


@dataclass
class VersionInfo:
    """Version metadata for API responses."""
    id: str
    version_number: int
    path: str
    source_type: str
    source_type_display: str
    source_message_id: Optional[str]
    source_job_id: Optional[str]
    source_tool_name: Optional[str]
    size_bytes: int
    is_deleted: bool
    is_binary: bool
    mime_type: str
    created_at: str
    created_by_id: Optional[str]
    created_by_username: Optional[str]


@dataclass
class ComparisonResult:
    """Result of comparing two versions."""
    version_a: VersionInfo
    version_b: VersionInfo
    original_content: Optional[bytes]
    modified_content: Optional[bytes]
    is_binary: bool


class FileVersionService:
    """
    Service for managing file versions.

    Provides content-addressable storage with automatic deduplication.
    Integrates with existing tiered storage (PostgreSQL + R2).

    Usage:
        service = get_file_version_service()
        version = service.create_version(
            workspace=workspace,
            path="src/main.py",
            content=b"print('hello')",
            source_type="user_edit",
        )
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._inline_threshold = getattr(settings, 'WORKSPACE_INLINE_THRESHOLD', 256 * 1024)
        self._initialized = True

    def _get_storage_service(self):
        """Lazy load storage service to avoid circular imports."""
        from workspaces.services.workspace_storage import get_workspace_storage_service
        return get_workspace_storage_service()

    def _is_binary_file(self, path: str, content: bytes) -> bool:
        """Detect if file is binary based on extension and content."""
        ext = os.path.splitext(path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            return True
        # Check for null bytes in first 8KB (heuristic for binary)
        sample = content[:8192]
        return b'\x00' in sample

    def _get_mime_type(self, path: str) -> str:
        """Get MIME type for file."""
        mime_type, _ = mimetypes.guess_type(path)
        return mime_type or 'application/octet-stream'

    @transaction.atomic
    def create_version(
        self,
        workspace,
        path: str,
        content: bytes,
        source_type: str,
        source_message=None,
        source_job_id: Optional[str] = None,
        source_tool_name: Optional[str] = None,
        user=None,
        is_deleted: bool = False,
    ):
        """
        Create a new version of a file.

        Automatically deduplicates content using SHA256 hash.
        Uses tiered storage (inline for small, R2 for large files).

        Args:
            workspace: The workspace containing the file
            path: Relative file path
            content: File content as bytes
            source_type: What caused this version (user_edit, file_tool, etc.)
            source_message: Optional message that triggered this version
            source_job_id: Optional Coding Agent job ID
            source_tool_name: Optional tool name (Write, Edit, etc.)
            user: User who created this version
            is_deleted: Whether this is a deletion tombstone

        Returns:
            The created FileVersion instance
        """
        from workspaces.models import FileVersion, FileVersionContent

        # Compute content hash
        sha256_hash = hashlib.sha256(content).hexdigest()
        size_bytes = len(content)
        is_binary = self._is_binary_file(path, content)
        mime_type = self._get_mime_type(path)

        # Get or create content record (deduplication)
        content_record, created = FileVersionContent.objects.get_or_create(
            sha256_hash=sha256_hash,
            defaults={
                'size_bytes': size_bytes,
                'storage_type': FileVersionContent.STORAGE_INLINE,
            }
        )

        if created:
            # Store content using tiered storage
            if size_bytes <= self._inline_threshold:
                content_record.storage_type = FileVersionContent.STORAGE_INLINE
                content_record.content = content
            else:
                # Upload to R2
                r2_key = self._build_r2_key(
                    str(workspace.user_id),
                    str(workspace.chat_id),
                    sha256_hash
                )
                storage = self._get_storage_service()
                try:
                    success = storage._upload_to_r2(r2_key, content, mime_type)
                    if success:
                        content_record.storage_type = FileVersionContent.STORAGE_R2
                        content_record.r2_key = r2_key
                    else:
                        # Fallback to inline
                        logger.warning(f"R2 upload failed, falling back to inline for {path}")
                        content_record.storage_type = FileVersionContent.STORAGE_INLINE
                        content_record.content = content
                except Exception as e:
                    logger.error(f"R2 upload error for {path}: {e}")
                    content_record.storage_type = FileVersionContent.STORAGE_INLINE
                    content_record.content = content
            content_record.save()
        else:
            # Increment reference count for existing content
            FileVersionContent.objects.filter(sha256_hash=sha256_hash).update(
                reference_count=F('reference_count') + 1
            )

        # Create version record
        version = FileVersion.objects.create(
            workspace=workspace,
            path=path,
            version_number=FileVersion.get_next_version_number(workspace, path),
            source_type=source_type,
            source_message=source_message,
            source_job_id=source_job_id or '',
            source_tool_name=source_tool_name or '',
            content_ref=content_record,
            size_bytes=size_bytes,
            is_deleted=is_deleted,
            is_binary=is_binary,
            mime_type=mime_type,
            created_by=user,
        )

        logger.info(
            f"[FileVersion] Created v{version.version_number} for {path} "
            f"({source_type}, {size_bytes} bytes, hash={sha256_hash[:8]})"
        )

        return version

    def _build_r2_key(self, user_id: str, chat_id: str, sha256_hash: str) -> str:
        """Build R2 key for version content."""
        return f"{user_id}/chats/{chat_id}/versions/{sha256_hash}"

    def get_file_history(
        self,
        workspace,
        path: str,
        limit: int = 50,
    ) -> List:
        """Get version history for a specific file, newest first."""
        from workspaces.models import FileVersion

        return list(
            FileVersion.objects.filter(workspace=workspace, path=path)
            .select_related('source_message', 'created_by')
            .order_by('-version_number')[:limit]
        )

    def get_version(self, version_id: str):
        """Get a specific version by ID."""
        from workspaces.models import FileVersion

        try:
            return FileVersion.objects.select_related('content_ref').get(id=version_id)
        except FileVersion.DoesNotExist:
            return None

    def get_version_content(self, version) -> bytes:
        """Retrieve content for a specific version."""
        from workspaces.models import FileVersionContent

        content_record = version.content_ref

        if content_record.storage_type == FileVersionContent.STORAGE_INLINE:
            return bytes(content_record.content) if content_record.content else b''
        else:
            # Download from R2
            storage = self._get_storage_service()
            try:
                content = storage._download_from_r2(content_record.r2_key)
                if content is None:
                    # Fallback to inline if available
                    if content_record.content:
                        logger.warning(f"R2 download failed, using inline fallback for {version.path}")
                        return bytes(content_record.content)
                    raise RuntimeError(f"Failed to retrieve content for version {version.id}")
                return content
            except Exception as e:
                logger.error(f"Error retrieving version content: {e}")
                if content_record.content:
                    return bytes(content_record.content)
                raise

    def get_latest_version(self, workspace, path: str):
        """Get the latest version of a file."""
        from workspaces.models import FileVersion

        return FileVersion.objects.filter(
            workspace=workspace,
            path=path
        ).order_by('-version_number').first()

    def compare_versions(self, version_a, version_b) -> ComparisonResult:
        """
        Compare two versions of a file.

        Returns content of both versions for diff display.
        For binary files, content is None.
        """
        is_binary = version_a.is_binary or version_b.is_binary

        if is_binary:
            original_content = None
            modified_content = None
        else:
            original_content = self.get_version_content(version_a)
            modified_content = self.get_version_content(version_b)

        return ComparisonResult(
            version_a=self._to_version_info(version_a),
            version_b=self._to_version_info(version_b),
            original_content=original_content,
            modified_content=modified_content,
            is_binary=is_binary,
        )

    def get_workspace_timeline(
        self,
        workspace,
        since: Optional[datetime] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
    ) -> List:
        """Get timeline of all changes in workspace."""
        from workspaces.models import FileVersion

        qs = FileVersion.objects.filter(workspace=workspace)

        if since:
            qs = qs.filter(created_at__gte=since)
        if source_type:
            qs = qs.filter(source_type=source_type)

        return list(
            qs.select_related('source_message', 'created_by')
            .order_by('-created_at')[:limit]
        )

    def get_message_file_changes(self, message) -> List:
        """Get all file versions created by a specific message."""
        from workspaces.models import FileVersion

        return list(
            FileVersion.objects.filter(source_message=message)
            .select_related('content_ref')
            .order_by('path', 'version_number')
        )

    def get_job_file_changes(self, job_id: str) -> List:
        """Get all file versions created by a Coding Agent job."""
        from workspaces.models import FileVersion

        return list(
            FileVersion.objects.filter(source_job_id=job_id)
            .select_related('content_ref')
            .order_by('path', 'version_number')
        )

    def _to_version_info(self, version) -> VersionInfo:
        """Convert FileVersion to VersionInfo dataclass."""
        return VersionInfo(
            id=str(version.id),
            version_number=version.version_number,
            path=version.path,
            source_type=version.source_type,
            source_type_display=version.get_source_type_display(),
            source_message_id=str(version.source_message_id) if version.source_message_id else None,
            source_job_id=version.source_job_id or None,
            source_tool_name=version.source_tool_name or None,
            size_bytes=version.size_bytes,
            is_deleted=version.is_deleted,
            is_binary=version.is_binary,
            mime_type=version.mime_type,
            created_at=version.created_at.isoformat(),
            created_by_id=str(version.created_by_id) if version.created_by_id else None,
            created_by_username=version.created_by.username if version.created_by else None,
        )

    @transaction.atomic
    def cleanup_old_versions(
        self,
        workspace,
        keep_versions: int = 50,
        older_than_days: int = 30,
    ) -> int:
        """
        Cleanup old versions to manage storage.

        Keeps at least `keep_versions` per file.
        Only deletes versions older than `older_than_days`.

        Returns number of versions deleted.
        """
        from workspaces.models import FileVersion, FileVersionContent
        from django.db.models import Count

        cutoff = datetime.now() - timedelta(days=older_than_days)
        deleted_count = 0

        # Get files with many versions
        files_with_versions = (
            FileVersion.objects.filter(workspace=workspace)
            .values('path')
            .annotate(count=Count('id'))
            .filter(count__gt=keep_versions)
        )

        for file_info in files_with_versions:
            path = file_info['path']
            excess_count = file_info['count'] - keep_versions

            # Get oldest versions beyond the keep limit
            old_versions = list(
                FileVersion.objects.filter(
                    workspace=workspace,
                    path=path,
                    created_at__lt=cutoff,
                )
                .order_by('version_number')[:excess_count]
            )

            for version in old_versions:
                # Decrement reference count
                FileVersionContent.objects.filter(
                    sha256_hash=version.content_ref_id
                ).update(reference_count=F('reference_count') - 1)
                version.delete()
                deleted_count += 1

        # Cleanup orphaned content (reference_count = 0)
        orphaned = FileVersionContent.objects.filter(reference_count=0)
        storage = self._get_storage_service()
        for content in orphaned:
            if content.storage_type == FileVersionContent.STORAGE_R2 and content.r2_key:
                try:
                    storage._delete_from_r2(content.r2_key)
                except Exception as e:
                    logger.error(f"Failed to delete R2 object {content.r2_key}: {e}")
            content.delete()

        if deleted_count > 0:
            logger.info(f"[FileVersion] Cleaned up {deleted_count} old versions for workspace {workspace.id}")

        return deleted_count

    def create_deletion_tombstone(
        self,
        workspace,
        path: str,
        source_type: str,
        source_message=None,
        source_job_id: Optional[str] = None,
        user=None,
    ):
        """
        Create a version marking file deletion.

        Stores empty content with is_deleted=True.
        """
        return self.create_version(
            workspace=workspace,
            path=path,
            content=b'',  # Empty content for deletion marker
            source_type=source_type,
            source_message=source_message,
            source_job_id=source_job_id,
            user=user,
            is_deleted=True,
        )


# Singleton accessor
_service: Optional[FileVersionService] = None


def get_file_version_service() -> FileVersionService:
    """Get the FileVersionService singleton."""
    global _service
    if _service is None:
        _service = FileVersionService()
    return _service
