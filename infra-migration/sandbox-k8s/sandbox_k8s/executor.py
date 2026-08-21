"""
Kubernetes Sandbox Executor

Drop-in replacement for the Docker-based SandboxExecutor.
Uses Kubernetes pods instead of Docker containers.
"""

import base64
import logging
import threading
import time
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime

from .pod_manager import PodManager
from .config import SandboxConfig

logger = logging.getLogger(__name__)

# Directory to store artifacts on the host
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/tmp/sterna-artifacts"))


class KubernetesSandboxExecutor:
    """
    Kubernetes-based sandbox executor.

    Maintains API compatibility with Docker-based SandboxExecutor
    but uses Kubernetes pods for execution.
    """

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        inactivity_timeout: int = 3600,
        cleanup_interval: int = 60,
    ):
        self.config = config or SandboxConfig()
        self.config.inactivity_timeout = inactivity_timeout
        self.config.cleanup_interval = cleanup_interval

        self.pod_manager = PodManager(self.config)

        # Track active pods: {sandbox_id: {'last_used': timestamp}}
        self.sandboxes: Dict[str, Dict] = {}
        # Active executions for cancellation
        self.active_executions: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.executions_lock = threading.Lock()

        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        logger.info(
            f"KubernetesSandboxExecutor initialized with timeout={inactivity_timeout}s"
        )

    def _cleanup_loop(self):
        """Background thread to cleanup inactive pods."""
        while True:
            try:
                time.sleep(self.config.cleanup_interval)
                deleted = self.pod_manager.cleanup_inactive_pods(
                    self.config.inactivity_timeout
                )
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} inactive sandbox pods")
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def _generate_sandbox_id(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str],
        sync_mode: bool,
    ) -> str:
        """Generate unique sandbox ID per user."""
        # One pod per user - isolation is done via workspace directories
        return f"sandbox-{user_id}"

    def _get_chat_workspace_path(
        self, chat_id: Optional[str], conversation_id: str
    ) -> str:
        """Get workspace path for a specific chat."""
        effective_id = chat_id if chat_id else conversation_id
        return f"/workspace/chat-{effective_id}"

    def _get_metadata_base_path(
        self, chat_id: Optional[str], conversation_id: str
    ) -> str:
        """Get metadata base path for a specific chat."""
        effective_id = chat_id if chat_id else conversation_id
        return f"/workspace/metadata-{effective_id}"

    def _validate_and_normalize_path(
        self, path: str, chat_workspace: str, user_id: str = None
    ) -> Tuple[bool, str, str]:
        """
        Validate and normalize a file path to prevent path traversal attacks.

        Returns:
            (is_valid, actual_path, relative_path)
        """
        import os as os_module

        # Block path traversal
        if ".." in path:
            logger.error(f"[SECURITY] Path traversal attempt blocked: {path}")
            return (False, "", "")

        # Special handling for /tmp/ paths
        if path.startswith("/tmp/"):
            normalized_tmp = os_module.path.normpath(path)
            if not normalized_tmp.startswith("/tmp/"):
                return (False, "", "")
            return (True, normalized_tmp, normalized_tmp)

        # Regular workspace files
        relative_path = (
            path.replace("/workspace/", "", 1)
            if path.startswith("/workspace/")
            else path.lstrip("/")
        )

        actual_path = os_module.path.normpath(f"{chat_workspace}/{relative_path}")

        if not actual_path.startswith(chat_workspace):
            logger.error(
                f"[SECURITY] Path traversal attempt blocked: {path} → {actual_path}"
            )
            return (False, "", "")

        return (True, actual_path, relative_path)

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
    ) -> Tuple[str, Optional[str], int, float, List[Dict[str, Any]]]:
        """
        Execute code in the sandbox pod.

        Returns:
            Tuple of (stdout, stderr, exit_code, execution_time, artifacts)
        """
        start_time = time.time()
        sandbox_id = self._generate_sandbox_id(
            user_id, conversation_id, chat_id, sync_mode
        )
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        logger.info(
            f"Executing code: user={user_id}, sandbox={sandbox_id}, language={language}"
        )

        # Track execution for cancellation
        if execution_id:
            with self.executions_lock:
                self.active_executions[execution_id] = {
                    "sandbox_id": sandbox_id,
                    "user_id": user_id,
                    "started_at": datetime.utcnow().isoformat(),
                }

        try:
            # Ensure sandbox pod exists
            pod_name, created = self.pod_manager.create_pod(user_id)

            # Ensure workspace directory exists
            self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["mkdir", "-p", chat_workspace],
                timeout=10,
            )

            # Write code to temp file
            if language == "python":
                script_file = f"{chat_workspace}/_exec_script.py"
                exec_cmd = ["python", script_file]
            elif language == "javascript":
                script_file = f"{chat_workspace}/_exec_script.js"
                exec_cmd = ["node", script_file]
            elif language == "bash":
                script_file = f"{chat_workspace}/_exec_script.sh"
                exec_cmd = ["bash", script_file]
            else:
                return (
                    "",
                    f"Unsupported language: {language}",
                    1,
                    time.time() - start_time,
                    [],
                )

            # Write script file. Base64-encode so no byte sequence in the
            # user code (e.g. a heredoc terminator line) can escape into
            # the shell command.
            encoded_code = base64.b64encode(code.encode()).decode()
            write_cmd = ["sh", "-c", f"echo '{encoded_code}' | base64 -d > {script_file}"]
            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=write_cmd,
                timeout=10,
            )

            if exit_code != 0:
                return (
                    stdout,
                    f"Failed to write script: {stderr}",
                    exit_code,
                    time.time() - start_time,
                    [],
                )

            # Execute code
            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=exec_cmd,
                timeout=timeout,
                workdir=chat_workspace,
            )

            execution_time = time.time() - start_time

            # Check for generated artifacts (images, files)
            artifacts = self._collect_artifacts(user_id, chat_workspace, chat_id or conversation_id)

            # Cleanup script file
            self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["rm", "-f", script_file],
                timeout=5,
            )

            return (stdout, stderr if stderr else None, exit_code, execution_time, artifacts)

        except TimeoutError:
            return (
                "",
                f"Execution timed out after {timeout}s",
                124,
                time.time() - start_time,
                [],
            )
        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return ("", str(e), 1, time.time() - start_time, [])
        finally:
            # Remove from active executions
            if execution_id:
                with self.executions_lock:
                    self.active_executions.pop(execution_id, None)

    def _collect_artifacts(
        self, user_id: str, chat_workspace: str, chat_id: str
    ) -> List[Dict[str, Any]]:
        """Collect generated artifacts from workspace."""
        artifacts = []

        try:
            # Look for common artifact patterns
            exit_code, stdout, _ = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=[
                    "find",
                    chat_workspace,
                    "-maxdepth",
                    "2",
                    "-type",
                    "f",
                    "(",
                    "-name",
                    "*.png",
                    "-o",
                    "-name",
                    "*.jpg",
                    "-o",
                    "-name",
                    "*.svg",
                    "-o",
                    "-name",
                    "*.pdf",
                    ")",
                    "-mmin",
                    "-1",  # Modified in last minute
                ],
                timeout=10,
            )

            if exit_code == 0 and stdout.strip():
                for file_path in stdout.strip().split("\n"):
                    if file_path:
                        filename = os.path.basename(file_path)
                        # Create public URL for artifact
                        artifacts.append({
                            "type": "file",
                            "name": filename,
                            "path": file_path,
                            "url": f"/artifact-files/{user_id}/{chat_id}/{filename}",
                        })

        except Exception as e:
            logger.warning(f"Failed to collect artifacts: {e}")

        return artifacts

    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        with self.executions_lock:
            execution = self.active_executions.get(execution_id)
            if not execution:
                return False

            user_id = execution.get("user_id")
            if user_id:
                try:
                    # Kill any running processes in the pod
                    self.pod_manager.exec_in_pod(
                        user_id=user_id,
                        command=["pkill", "-9", "-f", "_exec_script"],
                        timeout=5,
                    )
                    logger.info(f"Cancelled execution {execution_id}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to cancel execution: {e}")

        return False

    def list_files(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "/workspace",
        depth: int = 1,
    ) -> Dict[str, Any]:
        """List files in workspace directory."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        is_valid, actual_path, _ = self._validate_and_normalize_path(
            path, chat_workspace
        )
        if not is_valid:
            return {"success": False, "error": "Invalid path"}

        try:
            # Use find command with depth limit
            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=[
                    "find",
                    actual_path,
                    "-maxdepth",
                    str(depth),
                    "-printf",
                    "%y %s %T@ %p\n",
                ],
                timeout=self.config.directory_operation_timeout,
            )

            if exit_code != 0:
                # Directory might not exist
                return {"success": True, "files": [], "path": path}

            files = []
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(" ", 3)
                if len(parts) >= 4:
                    file_type, size, mtime, filepath = parts
                    files.append({
                        "name": os.path.basename(filepath),
                        "path": filepath.replace(chat_workspace, "/workspace"),
                        "type": "directory" if file_type == "d" else "file",
                        "size": int(size) if file_type == "f" else 0,
                    })

            return {"success": True, "files": files, "path": path}

        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return {"success": False, "error": str(e)}

    def read_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        max_lines: Optional[int] = None,
        from_end: bool = False,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        summary_only: bool = False,
    ) -> Dict[str, Any]:
        """Read file content."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        is_valid, actual_path, _ = self._validate_and_normalize_path(
            path, chat_workspace
        )
        if not is_valid:
            return {"success": False, "error": "Invalid path"}

        try:
            # Build read command based on options
            if summary_only:
                # Use grep to find function/class definitions
                cmd = [
                    "grep",
                    "-n",
                    "-E",
                    "^(def |class |function |const |export )",
                    actual_path,
                ]
            elif max_lines and from_end:
                cmd = ["tail", "-n", str(max_lines), actual_path]
            elif max_lines:
                cmd = ["head", "-n", str(max_lines), actual_path]
            elif start_line and end_line:
                cmd = ["sed", "-n", f"{start_line},{end_line}p", actual_path]
            else:
                cmd = ["cat", actual_path]

            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=cmd,
                timeout=self.config.file_operation_timeout,
            )

            if exit_code != 0:
                return {"success": False, "error": f"Failed to read file: {stderr}"}

            return {
                "success": True,
                "content": stdout,
                "path": path,
                "truncated": bool(max_lines),
            }

        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return {"success": False, "error": str(e)}

    def write_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        content: str = "",
        model_metadata: Optional[Dict] = None,
        is_base64: bool = False,
    ) -> Dict[str, Any]:
        """Write file content."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        is_valid, actual_path, _ = self._validate_and_normalize_path(
            path, chat_workspace
        )
        if not is_valid:
            return {"success": False, "error": "Invalid path"}

        try:
            # Ensure parent directory exists
            parent_dir = os.path.dirname(actual_path)
            self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["mkdir", "-p", parent_dir],
                timeout=10,
            )

            if is_base64:
                # Decode base64 and write binary
                cmd = [
                    "sh",
                    "-c",
                    f"echo '{content}' | base64 -d > {actual_path}",
                ]
            else:
                # Write text content using heredoc
                cmd = [
                    "sh",
                    "-c",
                    f"cat > {actual_path} << 'ENDOFFILE'\n{content}\nENDOFFILE",
                ]

            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=cmd,
                timeout=self.config.file_operation_timeout,
            )

            if exit_code != 0:
                return {"success": False, "error": f"Failed to write file: {stderr}"}

            return {"success": True, "path": path, "size": len(content)}

        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            return {"success": False, "error": str(e)}

    def edit_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        old_content: str = "",
        new_content: str = "",
    ) -> Dict[str, Any]:
        """Edit file by replacing content."""
        # Read current content
        read_result = self.read_file(
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            sync_mode=sync_mode,
            path=path,
        )

        if not read_result.get("success"):
            return read_result

        current_content = read_result.get("content", "")

        # Check if old_content exists
        if old_content not in current_content:
            return {
                "success": False,
                "error": "Old content not found in file",
            }

        # Replace content
        updated_content = current_content.replace(old_content, new_content, 1)

        # Write updated content
        return self.write_file(
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            sync_mode=sync_mode,
            path=path,
            content=updated_content,
        )

    def delete_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
    ) -> Dict[str, Any]:
        """Delete file or directory."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        is_valid, actual_path, _ = self._validate_and_normalize_path(
            path, chat_workspace
        )
        if not is_valid:
            return {"success": False, "error": "Invalid path"}

        try:
            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["rm", "-rf", actual_path],
                timeout=self.config.file_operation_timeout,
            )

            if exit_code != 0:
                return {"success": False, "error": f"Failed to delete: {stderr}"}

            return {"success": True, "path": path}

        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return {"success": False, "error": str(e)}

    def rename_file(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        old_path: str = "",
        new_path: str = "",
    ) -> Dict[str, Any]:
        """Rename file or directory."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        is_valid_old, actual_old, _ = self._validate_and_normalize_path(
            old_path, chat_workspace
        )
        is_valid_new, actual_new, _ = self._validate_and_normalize_path(
            new_path, chat_workspace
        )

        if not is_valid_old or not is_valid_new:
            return {"success": False, "error": "Invalid path"}

        try:
            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["mv", actual_old, actual_new],
                timeout=self.config.file_operation_timeout,
            )

            if exit_code != 0:
                return {"success": False, "error": f"Failed to rename: {stderr}"}

            return {"success": True, "old_path": old_path, "new_path": new_path}

        except Exception as e:
            logger.error(f"Failed to rename file: {e}")
            return {"success": False, "error": str(e)}

    def create_directory(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
        model_metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Create directory."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        is_valid, actual_path, _ = self._validate_and_normalize_path(
            path, chat_workspace
        )
        if not is_valid:
            return {"success": False, "error": "Invalid path"}

        try:
            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["mkdir", "-p", actual_path],
                timeout=self.config.file_operation_timeout,
            )

            if exit_code != 0:
                return {
                    "success": False,
                    "error": f"Failed to create directory: {stderr}",
                }

            return {"success": True, "path": path}

        except Exception as e:
            logger.error(f"Failed to create directory: {e}")
            return {"success": False, "error": str(e)}

    def get_file_metadata(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        path: str = "",
    ) -> Dict[str, Any]:
        """Get file metadata."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        is_valid, actual_path, _ = self._validate_and_normalize_path(
            path, chat_workspace
        )
        if not is_valid:
            return {"success": False, "error": "Invalid path"}

        try:
            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["stat", "-c", "%s %Y %X %W", actual_path],
                timeout=self.config.file_operation_timeout,
            )

            if exit_code != 0:
                return {"success": False, "error": f"File not found: {stderr}"}

            parts = stdout.strip().split()
            if len(parts) >= 4:
                return {
                    "success": True,
                    "path": path,
                    "size": int(parts[0]),
                    "modified_at": datetime.fromtimestamp(int(parts[1])).isoformat(),
                    "accessed_at": datetime.fromtimestamp(int(parts[2])).isoformat(),
                    "created_at": datetime.fromtimestamp(int(parts[3])).isoformat()
                    if int(parts[3]) > 0
                    else None,
                }

            return {"success": False, "error": "Failed to parse metadata"}

        except Exception as e:
            logger.error(f"Failed to get metadata: {e}")
            return {"success": False, "error": str(e)}

    def search_code(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        sync_mode: bool = True,
        pattern: str = "",
        path: str = ".",
        include: Optional[str] = None,
        context_lines: int = 0,
        max_results: int = 50,
        ignore_case: bool = False,
    ) -> Dict[str, Any]:
        """Search for pattern in files."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            # Build grep command
            cmd = ["grep", "-rn"]
            if ignore_case:
                cmd.append("-i")
            if context_lines > 0:
                cmd.extend(["-C", str(context_lines)])
            if include:
                cmd.extend(["--include", include])

            cmd.extend([pattern, chat_workspace])

            exit_code, stdout, stderr = self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=cmd,
                timeout=self.config.directory_operation_timeout,
            )

            matches = []
            if stdout.strip():
                lines = stdout.strip().split("\n")[:max_results]
                for line in lines:
                    if ":" in line:
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            matches.append({
                                "file": parts[0].replace(chat_workspace, "/workspace"),
                                "line": int(parts[1]) if parts[1].isdigit() else 0,
                                "content": parts[2],
                            })

            return {
                "success": True,
                "matches": matches,
                "total": len(matches),
                "pattern": pattern,
            }

        except Exception as e:
            logger.error(f"Failed to search: {e}")
            return {"success": False, "error": str(e)}

    def delete_chat_workspace(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: str,
        sync_mode: bool = True,
    ) -> Dict[str, Any]:
        """Delete workspace for a specific chat."""
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)
        metadata_base = self._get_metadata_base_path(chat_id, conversation_id)

        try:
            # Delete both workspace and metadata
            self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=["rm", "-rf", chat_workspace, metadata_base],
                timeout=self.config.directory_operation_timeout,
            )

            return {"success": True, "deleted": [chat_workspace, metadata_base]}

        except Exception as e:
            logger.error(f"Failed to delete workspace: {e}")
            return {"success": False, "error": str(e)}

    def delete_conversation_workspaces(
        self,
        user_id: str,
        conversation_id: str,
        sync_mode: bool = True,
    ) -> Dict[str, Any]:
        """Delete all workspaces for a conversation."""
        try:
            # Find and delete all chat-* directories for this conversation
            self.pod_manager.exec_in_pod(
                user_id=user_id,
                command=[
                    "sh",
                    "-c",
                    f"rm -rf /workspace/chat-{conversation_id}* /workspace/metadata-{conversation_id}*",
                ],
                timeout=self.config.directory_operation_timeout,
            )

            return {"success": True, "conversation_id": conversation_id}

        except Exception as e:
            logger.error(f"Failed to delete conversation workspaces: {e}")
            return {"success": False, "error": str(e)}

    def destroy_sandbox(self, user_id: str) -> bool:
        """Destroy sandbox pod for user."""
        return self.pod_manager.delete_pod(user_id)

    def get_sandbox_status(self, user_id: str) -> Optional[Dict]:
        """Get status of user's sandbox pod."""
        return self.pod_manager.get_pod_status(user_id)
