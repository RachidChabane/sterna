"""
Sandbox Executor Adapter

Provides a unified interface that can use either Docker or Kubernetes
based on the ORCHESTRATOR_MODE environment variable.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_sandbox_executor(
    inactivity_timeout: int = 3600,
    cleanup_interval: int = 60,
):
    """
    Factory function to get the appropriate sandbox executor based on environment.

    Set ORCHESTRATOR_MODE=kubernetes to use Kubernetes pods.
    Otherwise, defaults to Docker containers.

    Returns:
        Either KubernetesSandboxExecutor or Docker-based SandboxExecutor
    """
    mode = os.getenv("ORCHESTRATOR_MODE", "docker").lower()

    if mode == "kubernetes":
        logger.info("Using Kubernetes sandbox executor")
        from .executor import KubernetesSandboxExecutor
        from .config import SandboxConfig

        config = SandboxConfig()
        config.inactivity_timeout = inactivity_timeout
        config.cleanup_interval = cleanup_interval

        return KubernetesSandboxExecutor(
            config=config,
            inactivity_timeout=inactivity_timeout,
            cleanup_interval=cleanup_interval,
        )

    else:
        logger.info("Using Docker sandbox executor")
        # Import the original Docker-based executor
        # This import is conditional to avoid requiring Docker SDK when using K8s
        try:
            import docker
            # Assuming original sandbox_executor is available
            from sandbox_executor import SandboxExecutor

            docker_client = docker.from_env()
            return SandboxExecutor(
                docker_client=docker_client,
                inactivity_timeout=inactivity_timeout,
                cleanup_interval=cleanup_interval,
            )
        except ImportError:
            raise RuntimeError(
                "Docker mode requires docker package and sandbox_executor module. "
                "Set ORCHESTRATOR_MODE=kubernetes to use Kubernetes mode."
            )


class SandboxExecutorInterface:
    """
    Abstract interface for sandbox executors.

    Both Docker and Kubernetes implementations should provide these methods.
    """

    def execute_code(
        self,
        code: str,
        language: str,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        timeout: int = 120,
        execution_id: Optional[str] = None,
    ):
        """Execute code in sandbox."""
        raise NotImplementedError

    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel running execution."""
        raise NotImplementedError

    def list_files(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "/workspace",
        depth: int = 1,
    ):
        """List files in workspace."""
        raise NotImplementedError

    def read_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        **kwargs,
    ):
        """Read file content."""
        raise NotImplementedError

    def write_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        content: str = "",
        **kwargs,
    ):
        """Write file content."""
        raise NotImplementedError

    def edit_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        old_content: str = "",
        new_content: str = "",
    ):
        """Edit file by replacing content."""
        raise NotImplementedError

    def delete_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
    ):
        """Delete file or directory."""
        raise NotImplementedError

    def rename_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        old_path: str = "",
        new_path: str = "",
    ):
        """Rename file or directory."""
        raise NotImplementedError

    def create_directory(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        **kwargs,
    ):
        """Create directory."""
        raise NotImplementedError

    def get_file_metadata(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
    ):
        """Get file metadata."""
        raise NotImplementedError

    def search_code(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        pattern: str = "",
        **kwargs,
    ):
        """Search for pattern in files."""
        raise NotImplementedError

    def delete_chat_workspace(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: str,
        sync_mode: bool = True,
    ):
        """Delete workspace for a chat."""
        raise NotImplementedError

    def delete_conversation_workspaces(
        self,
        user_id: str,
        conversation_id: str,
        sync_mode: bool = True,
    ):
        """Delete all workspaces for a conversation."""
        raise NotImplementedError
