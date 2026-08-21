"""
Workspace sync client for the orchestrator.

Communicates with the Django API to save/restore workspace files
during container lifecycle events.
"""
import base64
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

import httpx

logger = logging.getLogger(__name__)

# Django API base URL (web service in docker-compose)
DJANGO_API_URL = os.environ.get("DJANGO_API_URL", "http://web:8000")

# Internal service token for authenticating with Django backend
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")

# Exclude patterns - directories and files to skip
EXCLUDE_PATTERNS: Set[str] = {
    # Python
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    # Node.js
    "node_modules",
    ".npm",
    # Git
    ".git",
    # IDE
    ".idea",
    ".vscode",
    # OS
    ".DS_Store",
    "Thumbs.db",
    # Logs
    "*.log",
    "*.pyc",
    "*.pyo",
}

# Max file size to sync (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    files_synced: int
    bytes_synced: int
    files_deleted: int = 0
    errors: List[str] = None
    duration_ms: int = 0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class WorkspaceClient:
    """Client for workspace persistence API."""

    def __init__(self, base_url: str = None, timeout: float = 60.0, service_token: str = None):
        """
        Initialize workspace client.

        Args:
            base_url: Django API base URL
            timeout: Request timeout in seconds
            service_token: Internal service authentication token
        """
        self.base_url = base_url or DJANGO_API_URL
        self.timeout = timeout
        self.service_token = service_token or INTERNAL_SERVICE_TOKEN

        # Configure headers with service authentication
        headers = {}
        if self.service_token:
            headers["X-Service-Token"] = self.service_token

        self.client = httpx.Client(timeout=timeout, headers=headers)

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded from sync."""
        path_str = str(path)
        path_parts = path.parts

        for pattern in EXCLUDE_PATTERNS:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_parts:
                return True

        return False

    def save_workspace(
        self,
        container,  # Docker container
        user_id: str,
        chat_id: str,
        workspace_path: str = "/workspace",
    ) -> SyncResult:
        """
        Save workspace files from container to persistent storage.

        Args:
            container: Docker container to extract files from
            user_id: User UUID
            chat_id: Chat UUID
            workspace_path: Path to workspace in container

        Returns:
            SyncResult with sync statistics
        """
        import time
        start = time.time()
        errors = []
        files_to_save = []
        total_bytes = 0

        try:
            # List all files in workspace using find
            result = container.exec_run(
                ["find", workspace_path, "-type", "f", "-not", "-path", "*/__pycache__/*",
                 "-not", "-path", "*/node_modules/*", "-not", "-path", "*/.git/*",
                 "-not", "-name", "*.pyc", "-not", "-name", ".DS_Store"],
                workdir=workspace_path
            )

            if result.exit_code != 0:
                logger.warning(f"find command failed: {result.output.decode()}")
                return SyncResult(
                    success=False,
                    files_synced=0,
                    bytes_synced=0,
                    errors=[f"Failed to list files: {result.output.decode()}"]
                )

            file_paths = result.output.decode().strip().split('\n')
            file_paths = [p for p in file_paths if p and p != workspace_path]

            logger.info(f"Found {len(file_paths)} files to sync in {workspace_path}")

            # Read each file
            for file_path in file_paths:
                try:
                    # Get file size first
                    stat_result = container.exec_run(
                        ["stat", "-c", "%s", file_path]
                    )
                    if stat_result.exit_code != 0:
                        continue

                    file_size = int(stat_result.output.decode().strip())

                    # Skip large files
                    if file_size > MAX_FILE_SIZE:
                        logger.warning(f"Skipping large file: {file_path} ({file_size} bytes)")
                        continue

                    # Skip empty files
                    if file_size == 0:
                        continue

                    # Read file content
                    cat_result = container.exec_run(
                        ["cat", file_path]
                    )
                    if cat_result.exit_code != 0:
                        errors.append(f"Failed to read {file_path}")
                        continue

                    content = cat_result.output
                    sha256 = hashlib.sha256(content).hexdigest()

                    # Get relative path
                    relative_path = file_path.replace(workspace_path + "/", "", 1)

                    # Get mime type (optional)
                    mime_result = container.exec_run(
                        ["file", "--mime-type", "-b", file_path]
                    )
                    mime_type = mime_result.output.decode().strip() if mime_result.exit_code == 0 else None

                    files_to_save.append({
                        "path": relative_path,
                        "content_base64": base64.b64encode(content).decode('utf-8'),
                        "size": file_size,
                        "sha256": sha256,
                        "mime_type": mime_type,
                    })
                    total_bytes += file_size

                except Exception as e:
                    errors.append(f"Error processing {file_path}: {str(e)}")
                    logger.error(f"Error processing file {file_path}: {e}")

            if not files_to_save:
                logger.info(f"No files to save for user={user_id}, chat={chat_id}")
                return SyncResult(
                    success=True,
                    files_synced=0,
                    bytes_synced=0,
                    duration_ms=int((time.time() - start) * 1000)
                )

            # Send to Django API
            response = self.client.post(
                f"{self.base_url}/api/workspaces/save/",
                json={
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "files": files_to_save,
                }
            )

            if response.status_code != 200:
                errors.append(f"API error: {response.status_code} - {response.text}")
                return SyncResult(
                    success=False,
                    files_synced=0,
                    bytes_synced=0,
                    errors=errors,
                    duration_ms=int((time.time() - start) * 1000)
                )

            result_data = response.json()

            return SyncResult(
                success=result_data.get('success', False),
                files_synced=result_data.get('files_synced', 0),
                bytes_synced=result_data.get('bytes_synced', 0),
                files_deleted=result_data.get('files_deleted', 0),
                errors=result_data.get('errors', []) + errors,
                duration_ms=result_data.get('duration_ms', int((time.time() - start) * 1000))
            )

        except Exception as e:
            logger.error(f"Workspace save failed: {e}")
            return SyncResult(
                success=False,
                files_synced=0,
                bytes_synced=0,
                errors=[str(e)] + errors,
                duration_ms=int((time.time() - start) * 1000)
            )

    def restore_workspace(
        self,
        container,  # Docker container
        user_id: str,
        chat_id: str,
        workspace_path: str = "/workspace",
    ) -> SyncResult:
        """
        Restore workspace files from persistent storage to container.

        Args:
            container: Docker container to restore files to
            user_id: User UUID
            chat_id: Chat UUID
            workspace_path: Path to workspace in container

        Returns:
            SyncResult with restore statistics
        """
        import time
        start = time.time()
        errors = []
        files_restored = 0
        bytes_restored = 0

        try:
            # Get files from Django API
            response = self.client.get(
                f"{self.base_url}/api/workspaces/restore/{user_id}/{chat_id}/"
            )

            if response.status_code != 200:
                return SyncResult(
                    success=False,
                    files_synced=0,
                    bytes_synced=0,
                    errors=[f"API error: {response.status_code} - {response.text}"],
                    duration_ms=int((time.time() - start) * 1000)
                )

            result_data = response.json()

            if not result_data.get('success'):
                return SyncResult(
                    success=False,
                    files_synced=0,
                    bytes_synced=0,
                    errors=[result_data.get('error', 'Unknown error')],
                    duration_ms=int((time.time() - start) * 1000)
                )

            files = result_data.get('files', [])

            if not files:
                logger.info(f"No files to restore for user={user_id}, chat={chat_id}")
                return SyncResult(
                    success=True,
                    files_synced=0,
                    bytes_synced=0,
                    duration_ms=int((time.time() - start) * 1000)
                )

            logger.info(f"Restoring {len(files)} files to {workspace_path}")

            # Ensure workspace directory exists
            container.exec_run(["mkdir", "-p", workspace_path])

            # Restore each file
            for file_data in files:
                try:
                    path = file_data.get('path')
                    content_b64 = file_data.get('content_base64')

                    if not path or not content_b64:
                        continue

                    # Decode content
                    content = base64.b64decode(content_b64)

                    # Create full path
                    full_path = f"{workspace_path}/{path}"

                    # Create parent directories
                    parent_dir = '/'.join(full_path.split('/')[:-1])
                    container.exec_run(["mkdir", "-p", parent_dir])

                    # Write file using base64 decode in container
                    # This avoids issues with binary data in exec_run
                    result = container.exec_run(
                        ["sh", "-c", f"echo '{content_b64}' | base64 -d > '{full_path}'"]
                    )

                    if result.exit_code != 0:
                        errors.append(f"Failed to write {path}: {result.output.decode()}")
                        continue

                    files_restored += 1
                    bytes_restored += len(content)

                except Exception as e:
                    errors.append(f"Error restoring {file_data.get('path', 'unknown')}: {str(e)}")
                    logger.error(f"Error restoring file: {e}")

            return SyncResult(
                success=len(errors) == 0,
                files_synced=files_restored,
                bytes_synced=bytes_restored,
                errors=errors,
                duration_ms=int((time.time() - start) * 1000)
            )

        except Exception as e:
            logger.error(f"Workspace restore failed: {e}")
            return SyncResult(
                success=False,
                files_synced=0,
                bytes_synced=0,
                errors=[str(e)] + errors,
                duration_ms=int((time.time() - start) * 1000)
            )

    def get_workspace_info(self, user_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get workspace information."""
        try:
            response = self.client.get(
                f"{self.base_url}/api/workspaces/info/{user_id}/{chat_id}/"
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get workspace info: {e}")
            return None

    def delete_workspace(self, user_id: str, chat_id: str) -> bool:
        """Delete a workspace."""
        try:
            response = self.client.delete(
                f"{self.base_url}/api/workspaces/delete/{user_id}/{chat_id}/"
            )
            if response.status_code == 200:
                return response.json().get('deleted', False)
            return False
        except Exception as e:
            logger.error(f"Failed to delete workspace: {e}")
            return False

    def create_version(
        self,
        user_id: str,
        chat_id: str,
        path: str,
        content: bytes,
        source_type: str = 'file_tool',
        source_message_id: Optional[str] = None,
        source_job_id: Optional[str] = None,
        source_tool_name: Optional[str] = None,
        is_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a file version for tracking changes.

        Args:
            user_id: User UUID
            chat_id: Chat UUID
            path: Relative file path
            content: File content as bytes
            source_type: What created this version (file_tool, coding_agent, user_edit)
            source_message_id: Optional message ID
            source_job_id: Optional Coding Agent job ID
            source_tool_name: Optional tool name (Write, Edit, etc.)
            is_deleted: Whether this is a deletion marker

        Returns:
            Version info dict or None on error
        """
        try:
            payload = {
                'user_id': user_id,
                'chat_id': chat_id,
                'path': path,
                'content_base64': base64.b64encode(content).decode('utf-8'),
                'source_type': source_type,
                'is_deleted': is_deleted,
            }

            if source_message_id:
                payload['source_message_id'] = source_message_id
            if source_job_id:
                payload['source_job_id'] = source_job_id
            if source_tool_name:
                payload['source_tool_name'] = source_tool_name

            response = self.client.post(
                f"{self.base_url}/api/workspaces/versions/create/",
                json=payload,
            )

            if response.status_code in (200, 201):
                result = response.json()
                if result.get('success'):
                    logger.debug(f"Created version for {path}: v{result.get('version', {}).get('version_number')}")
                    return result.get('version')
                else:
                    logger.warning(f"Version creation failed for {path}: {result.get('error')}")
            else:
                logger.warning(f"Version API error: {response.status_code} - {response.text[:200]}")

            return None

        except Exception as e:
            logger.error(f"Failed to create version for {path}: {e}")
            return None

    def create_versions_batch(
        self,
        user_id: str,
        chat_id: str,
        files: List[Dict[str, Any]],
        source_type: str = 'file_tool',
        source_job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create multiple file versions in a batch.

        Args:
            user_id: User UUID
            chat_id: Chat UUID
            files: List of file dicts with 'path', 'content_base64', etc.
            source_type: Source type for all files
            source_job_id: Optional job ID for all files

        Returns:
            Result dict with versions_created count
        """
        try:
            payload = {
                'user_id': user_id,
                'chat_id': chat_id,
                'source_type': source_type,
                'files': files,
            }

            if source_job_id:
                payload['source_job_id'] = source_job_id

            response = self.client.post(
                f"{self.base_url}/api/workspaces/versions/create-batch/",
                json=payload,
            )

            if response.status_code in (200, 201):
                result = response.json()
                logger.info(f"Batch created {result.get('versions_created', 0)} versions")
                return result
            else:
                logger.warning(f"Batch version API error: {response.status_code}")
                return {'success': False, 'versions_created': 0}

        except Exception as e:
            logger.error(f"Failed to create batch versions: {e}")
            return {'success': False, 'versions_created': 0, 'error': str(e)}

    def close(self):
        """Close the HTTP client."""
        self.client.close()


# Global client instance
_workspace_client: Optional[WorkspaceClient] = None


def get_workspace_client() -> WorkspaceClient:
    """Get or create the global workspace client."""
    global _workspace_client
    if _workspace_client is None:
        _workspace_client = WorkspaceClient()
    return _workspace_client
