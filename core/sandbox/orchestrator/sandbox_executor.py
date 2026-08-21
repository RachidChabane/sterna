"""
Sandbox Executor

Manages ephemeral sandbox containers for code execution with intelligent lifecycle:
- Creates sandbox on first execution
- Reuses sandbox for same context (user + conversation/chat)
- Destroys sandbox after inactivity timeout (default 5 minutes)
"""

import docker
import os
import time
import threading
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging

import excel_handler

if TYPE_CHECKING:
    from docker import DockerClient
    from docker.models.containers import Container

logger = logging.getLogger(__name__)

# Directory to store artifacts on the host
ARTIFACTS_DIR = Path("/tmp/sterna-artifacts")

# Sandbox resource configuration from environment
SANDBOX_MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "1g")  # Bumped from 512m for npm install
SANDBOX_WORKSPACE_SIZE = os.getenv("SANDBOX_WORKSPACE_SIZE", "1024M")  # 1GB workspace

# SECURITY: File size limits to prevent resource exhaustion (CWE-400)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB max file size
MAX_CODE_EXECUTION_SIZE = 1 * 1024 * 1024  # 1MB max for code execution

# SECURITY: Operation timeouts to prevent hanging (CWE-400)
FILE_OPERATION_TIMEOUT = 30  # 30 seconds for file operations
DIRECTORY_OPERATION_TIMEOUT = 60  # 60 seconds for directory operations (may involve recursion)

class SandboxExecutor:
    """Manages ephemeral sandbox containers for code execution."""

    def __init__(self,
                 docker_client: "DockerClient",
                 inactivity_timeout: int = 3600,  # 1 hour (increased from 5 min)
                 cleanup_interval: int = 60):     # Check every minute
        self.docker = docker_client
        self.inactivity_timeout = inactivity_timeout
        self.cleanup_interval = cleanup_interval

        # Cache: {sandbox_id: {'container': container, 'last_used': timestamp}}
        self.sandboxes: Dict[str, Dict] = {}
        # Active executions: {execution_id: {'future': future, 'sandbox_id': sandbox_id, 'executor': executor}}
        self.active_executions: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.executions_lock = threading.Lock()

        # Cleanup orphaned sandbox containers from previous runs
        self._cleanup_orphaned_containers()

        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        logger.info("SandboxExecutor initialized with timeout=%ds", inactivity_timeout)

    def _cleanup_orphaned_containers(self):
        """Remove orphaned sandbox containers from previous runs."""
        try:
            # List all containers with names starting with "sandbox-exec-"
            containers = self.docker.containers.list(
                all=True,
                filters={"name": "sandbox-exec-"}
            )

            if containers:
                logger.info(f"Found {len(containers)} orphaned sandbox containers, cleaning up...")
                for container in containers:
                    try:
                        logger.info(f"Removing orphaned container: {container.name}")
                        container.remove(force=True)
                    except Exception as e:
                        logger.warning(f"Failed to remove orphaned container {container.name}: {e}")
                logger.info("Orphaned containers cleanup completed")
            else:
                logger.info("No orphaned sandbox containers found")
        except Exception as e:
            logger.error(f"Error during orphaned containers cleanup: {e}")

    def _generate_sandbox_id(self, user_id: str, conversation_id: str,
                            chat_id: Optional[str], sync_mode: bool) -> str:
        """Generate unique sandbox ID per user (not per chat)."""
        # One container per user - isolation is done via chat folders
        return f"sandbox-exec-{user_id}"

    def _get_chat_workspace_path(self, chat_id: Optional[str], conversation_id: str) -> str:
        """Get workspace path for a specific chat."""
        # Use chat_id for isolation, fallback to conversation_id
        effective_id = chat_id if chat_id else conversation_id
        if not chat_id:
            logger.warning(f"chat_id not provided, falling back to conversation_id: {conversation_id}")
        return f"/workspace/chat-{effective_id}"

    def _get_metadata_base_path(self, chat_id: Optional[str], conversation_id: str) -> str:
        """Get metadata base path for a specific chat."""
        # Use chat_id for isolation, fallback to conversation_id
        effective_id = chat_id if chat_id else conversation_id
        if not chat_id:
            logger.warning(f"chat_id not provided for metadata, falling back to conversation_id: {conversation_id}")
        return f"/workspace/metadata-{effective_id}"

    def _get_safe_metadata_path(self, file_path: str, metadata_base: str) -> tuple[bool, str, str]:
        """
        Safely construct metadata path for a file, preventing path traversal (CWE-22).

        Returns:
            (is_valid, meta_dir, meta_path)
        """
        import os as os_module

        # SECURITY: Block path traversal attempts
        if ".." in file_path:
            logger.error(f"[SECURITY] Metadata path traversal blocked: {file_path}")
            return (False, "", "")

        # Get clean relative path (strip /workspace prefix)
        relative_path = file_path.lstrip("/").replace("workspace/", "", 1) if file_path.startswith("/workspace") else file_path.lstrip("/")

        # SECURITY: Use basename to prevent directory traversal in filename
        directory = os_module.path.dirname(relative_path)
        filename = os_module.path.basename(relative_path)

        # SECURITY: Validate directory doesn't contain traversal
        if directory and (".." in directory or directory.startswith("/")):
            logger.error(f"[SECURITY] Metadata directory traversal blocked: {directory}")
            return (False, "", "")

        # Build metadata path
        meta_dir = os_module.path.join(metadata_base, directory) if directory else metadata_base
        meta_filename = f"{filename}.meta.json"
        meta_path = os_module.path.join(meta_dir, meta_filename)

        # SECURITY: Verify the final path is within metadata_base
        normalized_meta_path = os_module.path.normpath(meta_path)
        normalized_metadata_base = os_module.path.normpath(metadata_base)
        if not normalized_meta_path.startswith(normalized_metadata_base):
            logger.error(f"[SECURITY] Metadata path escape blocked: {meta_path}")
            return (False, "", "")

        return (True, meta_dir, meta_path)

    def _validate_and_normalize_path(self, path: str, chat_workspace: str, container=None) -> tuple[bool, str, str]:
        """
        Validate and normalize a file path to prevent path traversal attacks (CWE-22).
        Also prevents symlink-based escapes (CWE-59).

        Returns:
            (is_valid, actual_path, relative_path)
            - is_valid: True if path is safe, False otherwise
            - actual_path: Normalized absolute path within container
            - relative_path: Relative path for metadata/logging
        """
        import os as os_module

        # SECURITY: Block any path containing ".." to prevent directory traversal
        if ".." in path:
            logger.error(f"[SECURITY] Path traversal attempt blocked: {path}")
            return (False, "", "")

        # SECURITY: Block any writes outside /workspace - no exceptions
        if path.startswith("/tmp/") or path.startswith("/etc/") or path.startswith("/home/") or path.startswith("/root/"):
            logger.error(f"[SECURITY] Write outside workspace blocked: {path}")
            return (False, "", "")

        # Regular workspace files - scope to chat workspace
        relative_path = path.replace("/workspace/", "", 1) if path.startswith("/workspace/") else path.lstrip("/")

        # Normalize the path and ensure it doesn't escape workspace
        actual_path = os_module.path.normpath(f"{chat_workspace}/{relative_path}")

        # CRITICAL SECURITY CHECK: Verify the resolved path is still within chat workspace
        if not actual_path.startswith(chat_workspace):
            logger.error(f"[SECURITY] Path traversal attempt blocked: {path} → {actual_path} (expected under {chat_workspace})")
            return (False, "", "")

        # SECURITY: Check for symlink-based escapes (CWE-59)
        # Resolve symlinks inside container and verify target is still within workspace
        if container:
            try:
                # Check if path exists and is a symlink
                check_result = container.exec_run(
                    ["test", "-L", actual_path],
                    workdir=chat_workspace
                )
                if check_result.exit_code == 0:
                    # Path is a symlink - resolve it and check target
                    resolve_result = container.exec_run(
                        ["readlink", "-f", actual_path],
                        workdir=chat_workspace
                    )
                    if resolve_result.exit_code == 0:
                        resolved_path = resolve_result.output.decode('utf-8').strip()
                        # Check if resolved path escapes workspace
                        if not resolved_path.startswith(chat_workspace):
                            logger.error(f"[SECURITY] Symlink escape attempt blocked: {path} -> {resolved_path}")
                            return (False, "", "")
            except Exception as e:
                logger.warning(f"[SECURITY] Symlink check failed (allowing): {e}")

        return (True, actual_path, relative_path)

    def _exec_with_timeout(self, container, cmd: list, timeout: int = FILE_OPERATION_TIMEOUT, **kwargs) -> tuple:
        """
        Execute a command in container with timeout protection (CWE-400).

        Returns:
            (exit_code, output) tuple - raises TimeoutError if timeout exceeded
        """
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(container.exec_run, cmd, **kwargs)
            result = future.result(timeout=timeout)
            return result
        except FuturesTimeoutError:
            logger.error(f"[SECURITY] Operation timeout ({timeout}s) for command: {cmd}")
            raise TimeoutError(f"Operation timed out after {timeout} seconds")
        finally:
            executor.shutdown(wait=False)

    def _extract_user_id_from_sandbox_id(self, sandbox_id: str) -> str:
        """Extract user_id from sandbox_id."""
        # Format: sandbox-exec-{user_id}
        parts = sandbox_id.split('-', 2)  # Split into max 3 parts: ['sandbox', 'exec', '{user_id}']
        if len(parts) >= 3:
            return parts[2]  # user_id is the 3rd part (index 2)
        raise ValueError(f"Invalid sandbox_id format: {sandbox_id}")

    def _create_sandbox(self, sandbox_id: str) -> "Container":
        """Create a new sandbox container with gVisor runtime."""
        logger.info(f"Creating sandbox container: {sandbox_id}")

        container_name = sandbox_id

        # Check if container already exists in Docker
        try:
            existing_container = self.docker.containers.get(container_name)
            logger.info(f"Found existing container: {sandbox_id}, checking status...")

            # If container exists but is stopped, remove it and create new one
            if existing_container.status != 'running':
                logger.info(f"Container {sandbox_id} is {existing_container.status}, removing...")
                existing_container.remove(force=True)
            else:
                # Container is running, reuse it
                logger.info(f"Reusing running container: {sandbox_id}")
                return existing_container
        except docker.errors.NotFound:
            # Container doesn't exist, proceed with creation
            pass
        except Exception as e:
            logger.warning(f"Error checking existing container: {e}")

        try:
            # Create sandbox container with security hardening
            container = self.docker.containers.run(
                image="sandbox-datascience:latest",  # Full data science stack (numpy, pandas, matplotlib, etc.)
                name=container_name,
                detach=True,
                remove=False,  # We'll remove manually

                # gVisor runtime for security (if available)
                runtime="runsc",

                # Security options
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],

                # SECURITY: Read-only root filesystem - only /workspace is writable
                # This is OS-level protection that blocks ALL writes outside /workspace
                read_only=True,

                # Resource limits (configurable via env)
                mem_limit=SANDBOX_MEMORY_LIMIT,
                cpu_period=100000,
                cpu_quota=100000,  # 1 CPU core
                pids_limit=100,
                # Raise file descriptor limit for dev servers (Vite/webpack watch many files)
                ulimits=[docker.types.Ulimit(name='nofile', soft=65536, hard=65536)],

                # Network - Use sandbox_sandbox-isolated with egress proxy for filtered internet
                network="sandbox_sandbox-isolated",

                # Volumes - proxy CA for TLS
                volumes={
                    "sandbox_proxy-ca": {"bind": "/etc/ssl/proxy-ca", "mode": "ro"},
                },

                # SECURITY: Only /workspace is writable - all other paths are read-only
                # Programs needing temp files should use TMPDIR=/workspace/tmp
                # NOTE: exec is required on /workspace so npm/npx can invoke binaries
                # from node_modules/.bin/ (e.g. next, tsc). Docker defaults tmpfs to noexec.
                tmpfs={
                    '/workspace': f'size={SANDBOX_WORKSPACE_SIZE},mode=1777,exec',
                    # /tmp hosts the ephemeral HOME for Claude CLI (config, settings, plans).
                    # Needs enough room for CLI state but not package installs (those go to /workspace).
                    '/tmp': 'size=200M,mode=1777',
                    # /var/tmp and /run may be needed by some system processes
                    '/var/tmp': 'size=10M,mode=1777',
                    '/run': 'size=10M,mode=755',
                },

                # Environment - Configure proxy and redirect temp files to workspace
                environment={
                    'PYTHONUNBUFFERED': '1',
                    'DEBIAN_FRONTEND': 'noninteractive',
                    'HTTP_PROXY': 'http://egress-proxy:8888',
                    'HTTPS_PROXY': 'http://egress-proxy:8888',
                    'http_proxy': 'http://egress-proxy:8888',
                    'https_proxy': 'http://egress-proxy:8888',
                    'NO_PROXY': 'localhost,127.0.0.1',
                    'no_proxy': 'localhost,127.0.0.1',
                    # Use runtime proxy CA cert (volume-mounted) instead of baked-in cert.
                    # GnuTLS (used by git) needs CAPATH override to avoid stale system store.
                    'GIT_SSL_CAINFO': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                    'GIT_SSL_CAPATH': '/etc/ssl/proxy-ca',
                    'SSL_CERT_FILE': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                    'REQUESTS_CA_BUNDLE': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                    # Node.js needs explicit CA cert for mitmproxy (doesn't use system certs)
                    'NODE_EXTRA_CA_CERTS': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                    # SECURITY: Redirect temp file creation to workspace
                    'TMPDIR': '/workspace/tmp',
                    'TEMP': '/workspace/tmp',
                    'TMP': '/workspace/tmp',
                    # Package install support: root filesystem is read-only, so redirect
                    # pip user-installs and npm cache to /workspace where there's room.
                    'PIP_USER': '1',
                    'PYTHONUSERBASE': '/workspace/.pip-packages',
                    'PIP_NO_WARN_SCRIPT_LOCATION': '1',
                    'PIP_CACHE_DIR': '/workspace/.pip-cache',
                    'PIP_NO_INPUT': '1',  # Never prompt for input
                    'PIP_DISABLE_PIP_VERSION_CHECK': '1',  # Hide "new pip version available" notices
                    'NPM_CONFIG_IGNORE_SCRIPTS': 'true',
                    'NPM_CONFIG_CACHE': '/workspace/.npm-cache',
                    'NPM_CONFIG_LOGLEVEL': 'error',  # Suppress verbose npm output
                    'NPM_CONFIG_UPDATE_NOTIFIER': 'false',  # Hide "new npm version available" notices
                    'NEXT_TELEMETRY_DISABLED': '1',  # Prevent next build from spawning background telemetry (causes hangs)
                    'PATH': '/workspace/.pip-packages/bin:/workspace/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin',
                },

                # Keep container running
                command=["tail", "-f", "/dev/null"],

                # Working directory
                working_dir="/workspace"
            )

            logger.info(f"Sandbox created successfully: {sandbox_id}")
            return container

        except docker.errors.APIError as e:
            # If gVisor runtime not available, fall back to default runtime
            if "unknown or invalid runtime name" in str(e):
                logger.warning("gVisor runtime not available, falling back to default runtime")
                container = self.docker.containers.run(
                    image="sandbox-datascience:latest",  # Full data science stack (numpy, pandas, matplotlib, etc.)
                    name=container_name,
                    detach=True,
                    remove=False,
                    security_opt=["no-new-privileges:true"],
                    cap_drop=["ALL"],

                    # SECURITY: Read-only root filesystem - only /workspace is writable
                    read_only=True,

                    mem_limit=SANDBOX_MEMORY_LIMIT,
                    cpu_period=100000,
                    cpu_quota=100000,
                    pids_limit=100,
                    ulimits=[docker.types.Ulimit(name='nofile', soft=65536, hard=65536)],
                    network="sandbox_sandbox-isolated",  # Same network as main path
                    volumes={
                        "sandbox_proxy-ca": {"bind": "/etc/ssl/proxy-ca", "mode": "ro"},
                    },

                    # SECURITY: Only /workspace is writable
                    # NOTE: exec on /workspace allows npm binaries in node_modules/.bin/
                    tmpfs={
                        '/workspace': f'size={SANDBOX_WORKSPACE_SIZE},mode=1777,exec',
                        '/tmp': 'size=200M,mode=1777',
                        '/var/tmp': 'size=10M,mode=1777',
                        '/run': 'size=10M,mode=755',
                    },
                    environment={
                        'PYTHONUNBUFFERED': '1',
                        'HTTP_PROXY': 'http://egress-proxy:8888',
                        'HTTPS_PROXY': 'http://egress-proxy:8888',
                        'http_proxy': 'http://egress-proxy:8888',
                        'https_proxy': 'http://egress-proxy:8888',
                        'NO_PROXY': 'localhost,127.0.0.1',
                        'no_proxy': 'localhost,127.0.0.1',
                        # Use runtime proxy CA cert (volume-mounted) instead of baked-in cert.
                        # GnuTLS (used by git) needs CAPATH override to avoid stale system store.
                        'GIT_SSL_CAINFO': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                        'GIT_SSL_CAPATH': '/etc/ssl/proxy-ca',
                        'SSL_CERT_FILE': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                        'REQUESTS_CA_BUNDLE': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                        # Node.js needs explicit CA cert for mitmproxy (doesn't use system certs)
                        'NODE_EXTRA_CA_CERTS': '/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem',
                        # SECURITY: Redirect temp file creation to workspace
                        'TMPDIR': '/workspace/tmp',
                        'TEMP': '/workspace/tmp',
                        'TMP': '/workspace/tmp',
                        # Package install support (see primary path above)
                        'PIP_USER': '1',
                        'PYTHONUSERBASE': '/workspace/.pip-packages',
                        'PIP_NO_WARN_SCRIPT_LOCATION': '1',
                        'PIP_CACHE_DIR': '/workspace/.pip-cache',
                        'PIP_NO_INPUT': '1',
                        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
                        'NPM_CONFIG_IGNORE_SCRIPTS': 'true',
                        'NPM_CONFIG_CACHE': '/workspace/.npm-cache',
                        'NPM_CONFIG_LOGLEVEL': 'error',
                        'NPM_CONFIG_UPDATE_NOTIFIER': 'false',
                        'NEXT_TELEMETRY_DISABLED': '1',
                        'PATH': '/workspace/.pip-packages/bin:/workspace/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin',
                    },
                    command=["tail", "-f", "/dev/null"],
                    working_dir="/workspace"
                )

                return container
            else:
                raise

    def _get_or_create_sandbox(self, sandbox_id: str) -> "Container":
        """Get existing sandbox or create new one."""
        with self.lock:
            if sandbox_id in self.sandboxes:
                # Sandbox exists in cache - verify it still exists in Docker
                entry = self.sandboxes[sandbox_id]
                container = entry['container']

                try:
                    # Check if container still exists by reloading its state
                    container.reload()
                    # Container exists, update last_used time
                    entry['last_used'] = time.time()
                    logger.info(f"Reusing cached sandbox: {sandbox_id}")
                    return container
                except Exception as e:
                    # Container no longer exists, remove from cache
                    logger.warning(f"Cached sandbox {sandbox_id} no longer exists in Docker: {e}")
                    logger.info("Removing stale cache entry and creating new sandbox")
                    del self.sandboxes[sandbox_id]
                    # Fall through to create new sandbox

            # Create new sandbox (will check Docker for existing container)
            container = self._create_sandbox(sandbox_id)
            # Add to cache
            self.sandboxes[sandbox_id] = {
                'container': container,
                'last_used': time.time()
            }
            return container

    def _run_exec(self, container, cmd, code, workdir="/workspace"):
        """Helper to run exec_run in a thread."""
        # For Python code, prepend os.chdir() to ensure code runs in correct directory
        # This prevents code from using absolute paths to escape the chat workspace
        if cmd == ['python3', '-c']:
            # Wrap code to enforce working directory
            wrapped_code = f"""import os
os.chdir({repr(workdir)})
# User code below:
{code}"""
            code = wrapped_code

        return container.exec_run(
            cmd + [code],
            workdir=workdir,
            demux=True,
            environment={
                'PYTHONUNBUFFERED': '1',
                'PYTHONPATH': workdir  # Set PYTHONPATH to chat workspace for imports
            }
        )

    def _collect_artifacts(self, container, user_id: str, chat_id: Optional[str],
                          conversation_id: str, chat_workspace: str, marker_file: Optional[str] = None) -> List[dict]:
        """
        Collect artifact files (images, plots) generated during code execution.

        Args:
            marker_file: Optional path to marker file - only collect files newer than this

        Returns: List of artifact dicts with url, filename, type
        """
        try:
            # Image extensions to look for
            IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.svg', '.pdf', '.gif']

            # List files in workspace - only files newer than marker if provided
            if marker_file:
                # Find files created/modified after the marker file
                exec_result = container.exec_run(
                    ['find', chat_workspace, '-type', 'f', '-newer', marker_file],
                    workdir=chat_workspace
                )
            else:
                # Fallback: list all files (old behavior)
                exec_result = container.exec_run(
                    ['find', chat_workspace, '-type', 'f'],
                    workdir=chat_workspace
                )

            if exec_result.exit_code != 0:
                logger.warning(f"Failed to list files in {chat_workspace}")
                return []

            files_output = exec_result.output.decode('utf-8').strip()
            if not files_output:
                return []

            files = files_output.split('\n')

            # Filter for image files
            image_files = [
                f for f in files
                if any(f.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)
            ]

            logger.info(f"[Artifacts] Scanned {len(files)} files in {chat_workspace}, found {len(image_files)} images")

            if not image_files:
                logger.info(f"[Artifacts] No artifacts found (searched for: {IMAGE_EXTENSIONS})")
                return []

            logger.info(f"[Artifacts] Found {len(image_files)} artifact(s): {image_files}")

            # Create artifacts directory for this user/chat
            chat_artifacts_dir = ARTIFACTS_DIR / user_id / chat_id
            chat_artifacts_dir.mkdir(parents=True, exist_ok=True)

            artifact_urls = []

            # Copy each artifact from container to host
            for file_path in image_files:
                try:
                    # Get just the filename
                    filename = Path(file_path).name
                    dest_path = chat_artifacts_dir / filename

                    # Read file content from container using cat (get_archive doesn't work with tmpfs)
                    cat_result = container.exec_run(['cat', file_path])

                    if cat_result.exit_code != 0:
                        logger.error(f"Failed to read artifact {file_path}: cat exit code {cat_result.exit_code}")
                        continue

                    file_content = cat_result.output

                    # Write to destination
                    with open(dest_path, 'wb') as f:
                        f.write(file_content)

                    # Generate URL (will be served by FastAPI static files)
                    artifact_url = f"/artifact-files/{user_id}/{chat_id}/{filename}"

                    # Get file extension for type
                    file_ext = Path(filename).suffix.lower()

                    artifact_urls.append({
                        "url": artifact_url,
                        "filename": filename,
                        "type": file_ext[1:] if file_ext else "unknown"  # Remove leading dot
                    })

                    logger.info(f"Copied artifact: {file_path} -> {dest_path}")

                except Exception as e:
                    logger.error(f"Failed to copy artifact {file_path}: {e}")
                    continue

            return artifact_urls

        except Exception as e:
            logger.error(f"Failed to collect artifacts: {e}")
            return []

    def execute_code(self, code: str, language: str, user_id: str,
                    conversation_id: str, chat_id: Optional[str],
                    sync_mode: bool, timeout: int = 30, execution_id: Optional[str] = None) -> Tuple[str, Optional[str], int, float, List[dict]]:
        """
        Execute code in sandbox container with timeout and cancellation support.

        Returns: (output, error, exit_code, execution_time, artifacts)
        """
        logger.info(f"[EXEC] execute_code called with execution_id={execution_id}")

        # SECURITY: Enforce code size limits to prevent resource exhaustion (CWE-400)
        code_size = len(code.encode('utf-8'))
        if code_size > MAX_CODE_EXECUTION_SIZE:
            logger.error(f"[SECURITY] Code size limit exceeded: {code_size} bytes > {MAX_CODE_EXECUTION_SIZE} bytes")
            return "", f"Code too large: {code_size / 1024:.1f}KB exceeds limit of {MAX_CODE_EXECUTION_SIZE / 1024:.0f}KB", 1, 0.0, []

        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Ensure chat workspace directory exists
            container.exec_run(["mkdir", "-p", chat_workspace, "/workspace/tmp",
                                "/workspace/.pip-packages", "/workspace/.pip-cache",
                                "/workspace/.npm-cache", "/workspace/.npm-global"])

            # Create a marker file to track files created AFTER this point
            marker_file = f"{chat_workspace}/.exec_marker_{execution_id or 'default'}"
            container.exec_run(["touch", marker_file], workdir=chat_workspace)

            # Map language to command
            lang_commands = {
                'python': ['python3', '-c'],
                'javascript': ['node', '-e'],
                'bash': ['bash', '-c']
            }

            if language not in lang_commands:
                return "", f"Unsupported language: {language}", 1, 0.0

            cmd = lang_commands[language]

            # Execute code in container with timeout
            start_time = time.time()

            # Use ThreadPoolExecutor to enforce timeout
            executor_pool = ThreadPoolExecutor(max_workers=1)
            # Pass chat_workspace to _run_exec
            future = executor_pool.submit(self._run_exec, container, cmd, code, chat_workspace)

            # Register execution if execution_id is provided
            if execution_id:
                with self.executions_lock:
                    self.active_executions[execution_id] = {
                        'future': future,
                        'sandbox_id': sandbox_id,
                        'executor': executor_pool,
                        'start_time': start_time
                    }
                logger.info(f"[EXEC] Registered execution {execution_id} in active_executions (total: {len(self.active_executions)})")
            else:
                logger.warning("[EXEC] No execution_id provided, cannot track for cancellation")

            try:
                exec_result = future.result(timeout=timeout)
            except FuturesTimeoutError:
                logger.warning(f"Execution timeout ({timeout}s) in {sandbox_id}, destroying container")
                # Timeout occurred - destroy the container and remove from cache
                # so it's recreated fresh on next execution
                self._destroy_sandbox(sandbox_id)
                # Don't remove from active_executions immediately - let cancel requests arrive
                # The finally block will clean it up
                return "", f"Execution timeout after {timeout} seconds", 124, timeout, []
            finally:
                # Short delay to allow any in-flight cancel requests to arrive
                # This prevents 404s when user clicks Stop just as execution completes
                time.sleep(0.1)  # 100ms grace period

                # Remove from active executions
                if execution_id:
                    with self.executions_lock:
                        self.active_executions.pop(execution_id, None)
                        logger.info(f"[EXEC] Removed execution {execution_id} from active_executions")
                executor_pool.shutdown(wait=False)

            execution_time = time.time() - start_time

            # Parse output
            stdout, stderr = exec_result.output if exec_result.output else (b'', b'')

            output = stdout.decode('utf-8') if stdout else ''
            error = stderr.decode('utf-8') if stderr else None

            logger.info(f"Code executed in {sandbox_id}: exit_code={exec_result.exit_code}, time={execution_time:.3f}s")

            # Collect artifacts (images, plots) if execution succeeded
            artifacts = []
            if exec_result.exit_code == 0:
                artifacts = self._collect_artifacts(
                    container, user_id, chat_id, conversation_id, chat_workspace, marker_file
                )

            # Clean up marker file
            try:
                container.exec_run(["rm", "-f", marker_file], workdir=chat_workspace)
            except Exception as e:
                logger.debug(f"Failed to clean up marker file: {e}")

            return output, error, exec_result.exit_code, execution_time, artifacts

        except Exception as e:
            logger.error(f"Execution failed in {sandbox_id}: {e}")
            # Clean up execution tracking
            if execution_id:
                with self.executions_lock:
                    self.active_executions.pop(execution_id, None)

            # Clean up marker file on exception (if container exists)
            try:
                marker_file = f"{chat_workspace}/.exec_marker_{execution_id or 'default'}"
                if 'container' in locals():
                    container.exec_run(["rm", "-f", marker_file], workdir=chat_workspace)
            except Exception:
                pass  # Ignore cleanup errors in exception handler

            return "", str(e), 1, 0.0, []

    def cancel_execution(self, execution_id: str) -> bool:
        """
        Cancel a running code execution.

        Returns: True if execution was found and cancelled, False otherwise
        """
        logger.info(f"[CANCEL] Attempting to cancel {execution_id}")
        logger.info(f"[CANCEL] Active executions: {list(self.active_executions.keys())}")

        with self.executions_lock:
            execution = self.active_executions.get(execution_id)
            if not execution:
                logger.warning(f"[CANCEL] Execution {execution_id} not found in active_executions (total: {len(self.active_executions)})")
                return False

            future = execution['future']
            sandbox_id = execution['sandbox_id']
            executor_pool = execution['executor']

            logger.info(f"Cancelling execution {execution_id} in {sandbox_id}")

            # Cancel the future (won't stop already running code, but marks it as cancelled)
            future.cancel()

            # Remove from active executions immediately
            self.active_executions.pop(execution_id, None)

        # Destroy sandbox in background thread (container.stop can take up to 5 seconds)
        # This allows us to return immediately to the user
        def cleanup_background():
            try:
                self._destroy_sandbox(sandbox_id)
                logger.info(f"Destroyed sandbox {sandbox_id} due to cancellation")
            except Exception as e:
                logger.error(f"Failed to destroy sandbox {sandbox_id}: {e}")

            # Shutdown the executor
            try:
                executor_pool.shutdown(wait=False)
            except Exception as e:
                logger.error(f"Failed to shutdown executor: {e}")

        cleanup_thread = threading.Thread(target=cleanup_background, daemon=True)
        cleanup_thread.start()

        return True

    def _cleanup_loop(self):
        """Background thread to cleanup inactive sandboxes."""
        while True:
            try:
                time.sleep(self.cleanup_interval)
                self._cleanup_inactive_sandboxes()
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    def _cleanup_inactive_sandboxes(self):
        """Remove sandboxes that haven't been used for timeout period."""
        current_time = time.time()
        to_remove = []

        with self.lock:
            for sandbox_id, entry in self.sandboxes.items():
                last_used = entry['last_used']
                inactive_time = current_time - last_used

                if inactive_time > self.inactivity_timeout:
                    to_remove.append(sandbox_id)

        # Remove outside the lock to avoid blocking
        for sandbox_id in to_remove:
            self._destroy_sandbox(sandbox_id)

    def _destroy_sandbox(self, sandbox_id: str):
        """Destroy a sandbox container."""
        with self.lock:
            if sandbox_id not in self.sandboxes:
                return

            entry = self.sandboxes.pop(sandbox_id)
            container = entry['container']

        try:
            logger.info(f"Destroying inactive sandbox: {sandbox_id}")
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info(f"Sandbox destroyed: {sandbox_id}")
        except Exception as e:
            logger.error(f"Failed to destroy sandbox {sandbox_id}: {e}")

    def cleanup_all(self):
        """Cleanup all sandboxes (called on shutdown)."""
        logger.info("Cleaning up all sandboxes...")
        sandbox_ids = list(self.sandboxes.keys())

        for sandbox_id in sandbox_ids:
            self._destroy_sandbox(sandbox_id)

        logger.info(f"Cleaned up {len(sandbox_ids)} sandboxes")

    def list_files(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                  sync_mode: bool, path: str = "/workspace", depth: int = 1) -> dict:
        """List files in workspace directory with optional recursive depth."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        # Clamp depth to safe range
        depth = max(1, min(5, depth))

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Ensure chat workspace directory exists
            container.exec_run(["mkdir", "-p", chat_workspace, "/workspace/tmp",
                                "/workspace/.pip-packages", "/workspace/.pip-cache",
                                "/workspace/.npm-cache", "/workspace/.npm-global"])

            # SECURITY: Validate path to prevent traversal and symlink attacks (CWE-22, CWE-59)
            # Special handling for /tmp/ paths (attachments folder - outside workspace)
            if path.startswith("/tmp/"):
                actual_path = path  # Use absolute path as-is
                # Ensure the directory exists (e.g. /tmp/attachments_{chat_id} may not exist yet)
                container.exec_run(["mkdir", "-p", actual_path])
            elif path == "/workspace":
                actual_path = chat_workspace
            else:
                # Use secure path validation
                is_valid, actual_path, _ = self._validate_and_normalize_path(path, chat_workspace, container)
                if not is_valid:
                    return {"success": False, "error": "Invalid path: access denied"}

            logger.info(f"list_files: requested_path={path}, chat_workspace={chat_workspace}, actual_path={actual_path}, depth={depth}")

            # Use find for recursive listing with depth control
            exec_kwargs = {} if path.startswith("/tmp/") else {"workdir": chat_workspace}
            result = container.exec_run(
                ["find", actual_path, "-maxdepth", str(depth), "-printf", "%y %P\\n"],
                **exec_kwargs
            )

            if result.exit_code != 0:
                error_msg = result.output.decode('utf-8')
                logger.error(f"list_files failed: path={path}, actual_path={actual_path}, error={error_msg}")
                return {"success": False, "error": error_msg}

            # Parse find output to create file tree
            lines = result.output.decode('utf-8').strip().split('\n')
            files = []

            for line in lines:
                if not line.strip():
                    continue
                parts = line.split(' ', 1)
                if len(parts) < 2:
                    continue

                file_type = parts[0]  # 'd' for directory, 'f' for file
                name = parts[1]

                if not name or name in ['.', '..']:
                    continue

                # Filter out internal/system files that shouldn't be exposed
                if name.startswith('.exec_marker') or name.startswith('.coding-agent-'):
                    continue

                # Return paths relative to /workspace for frontend compatibility
                display_path = path if path != "/workspace" else "/workspace"
                files.append({
                    "name": name,
                    "type": "directory" if file_type == 'd' else "file",
                    "path": f"{display_path}/{name}".replace('//', '/')
                })

            # Sort: directories first, then by name
            files.sort(key=lambda f: (0 if f["type"] == "directory" else 1, f["name"].lower()))

            return {"success": True, "files": files, "path": path, "depth": depth}

        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return {"success": False, "error": str(e)}

    def read_file(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                 sync_mode: bool, path: str, max_lines: Optional[int] = None,
                 from_end: bool = False, start_line: Optional[int] = None,
                 end_line: Optional[int] = None, summary_only: bool = False) -> dict:
        """Read file content with optional partial reading.

        Args:
            max_lines: Maximum lines to return (from start or end)
            from_end: If True with max_lines, read last N lines
            start_line: Start line number (1-indexed)
            end_line: End line number (1-indexed, inclusive)
            summary_only: Return only file structure (functions, classes)
        """
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # SECURITY: Validate path to prevent traversal and symlink attacks (CWE-22, CWE-59)
            is_valid, actual_path, _ = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {"success": False, "error": "Invalid path: access denied"}

            # Detect binary files by extension
            binary_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.pdf',
                               '.zip', '.tar', '.gz', '.bin', '.exe', '.dll', '.so', '.dylib',
                               '.xlsx', '.xls', '.xlsm', '.xlsb', '.doc', '.docx', '.ppt', '.pptx']
            is_binary = any(path.lower().endswith(ext) for ext in binary_extensions)

            # Binary files don't support partial reading
            if is_binary:
                result = container.exec_run(["cat", actual_path], workdir=chat_workspace)
                if result.exit_code != 0:
                    return {"success": False, "error": result.output.decode('utf-8')}
                import base64
                content = base64.b64encode(result.output).decode('ascii')
                return {
                    "success": True,
                    "content": content,
                    "path": path,
                    "is_binary": True
                }

            # Get total line count first
            wc_result = container.exec_run(["wc", "-l", actual_path], workdir=chat_workspace)
            total_lines = 0
            if wc_result.exit_code == 0:
                try:
                    total_lines = int(wc_result.output.decode('utf-8').split()[0])
                except (ValueError, IndexError):
                    total_lines = 0

            # Handle summary_only mode
            if summary_only:
                return self._get_file_summary(container, actual_path, path, total_lines, chat_workspace)

            # Build the read command based on parameters
            if start_line is not None and end_line is not None:
                # Specific line range using sed
                cmd = f"sed -n '{start_line},{end_line}p' {actual_path}"
                result = container.exec_run(["sh", "-c", cmd], workdir=chat_workspace)
                line_info = f"lines {start_line}-{end_line} of {total_lines}"
            elif max_lines is not None:
                if from_end:
                    # Last N lines using tail
                    result = container.exec_run(["tail", "-n", str(max_lines), actual_path], workdir=chat_workspace)
                    line_info = f"last {max_lines} lines of {total_lines}"
                else:
                    # First N lines using head
                    result = container.exec_run(["head", "-n", str(max_lines), actual_path], workdir=chat_workspace)
                    line_info = f"first {max_lines} lines of {total_lines}"
            else:
                # Full file
                result = container.exec_run(["cat", actual_path], workdir=chat_workspace)
                line_info = f"{total_lines} lines"

            if result.exit_code != 0:
                return {"success": False, "error": result.output.decode('utf-8')}

            content = result.output.decode('utf-8')

            return {
                "success": True,
                "content": content,
                "path": path,
                "is_binary": False,
                "total_lines": total_lines,
                "line_info": line_info,
            }

        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return {"success": False, "error": str(e)}

    def _get_file_summary(self, container, actual_path: str, path: str,
                          total_lines: int, chat_workspace: str) -> dict:
        """Get file structure summary without full content."""
        ext = path.lower().split('.')[-1] if '.' in path else ''

        # Python files
        if ext == 'py':
            cmd = f"grep -n '^class \\|^def \\|^    def \\|^import \\|^from ' {actual_path} | head -100"
        # JavaScript/TypeScript
        elif ext in ('js', 'ts', 'jsx', 'tsx'):
            cmd = f"grep -n 'function \\|class \\|export \\|import \\|const .*= \\|=>' {actual_path} | head -100"
        # Other files - just show first and last few lines
        else:
            cmd = f"(head -20 {actual_path}; echo '\\n... ({total_lines} total lines) ...\\n'; tail -10 {actual_path})"

        result = container.exec_run(["sh", "-c", cmd], workdir=chat_workspace)

        if result.exit_code != 0:
            summary = f"[Could not parse structure. File has {total_lines} lines]"
        else:
            summary = result.output.decode('utf-8')

        return {
            "success": True,
            "content": summary,
            "path": path,
            "is_binary": False,
            "total_lines": total_lines,
            "summary_only": True,
            "line_info": f"structure summary of {total_lines} lines",
        }

    def search_code(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                    sync_mode: bool, pattern: str, path: str = ".",
                    include: Optional[str] = None, context_lines: int = 0,
                    max_results: int = 50, ignore_case: bool = False) -> dict:
        """Search for patterns in files using grep.

        Args:
            pattern: Regex pattern to search for
            path: Directory or file to search in (relative to workspace)
            include: Glob pattern to filter files (e.g., '*.py')
            context_lines: Lines of context around matches
            max_results: Maximum number of matches
            ignore_case: Case-insensitive search
        """
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Ensure chat workspace directory exists
            container.exec_run(["mkdir", "-p", chat_workspace, "/workspace/tmp",
                                "/workspace/.pip-packages", "/workspace/.pip-cache",
                                "/workspace/.npm-cache", "/workspace/.npm-global"])

            # Validate and normalize the search path
            if path in [".", "/", "/workspace", ""]:
                search_path = chat_workspace
            else:
                is_valid, search_path, _ = self._validate_and_normalize_path(path, chat_workspace, container)
                if not is_valid:
                    return {"success": False, "error": "Invalid path: access denied"}

            # Build grep command
            # Using grep -r for recursive, -n for line numbers, -E for extended regex
            grep_args = ["grep", "-r", "-n", "-E"]

            # Add flags
            if ignore_case:
                grep_args.append("-i")

            if context_lines > 0:
                grep_args.append(f"-C{min(context_lines, 10)}")  # Cap at 10 lines context

            # Add include pattern if specified
            if include:
                grep_args.extend(["--include", include])

            # Exclude common directories that shouldn't be searched
            grep_args.extend([
                "--exclude-dir=node_modules",
                "--exclude-dir=.git",
                "--exclude-dir=__pycache__",
                "--exclude-dir=.venv",
                "--exclude-dir=venv",
                "--exclude-dir=dist",
                "--exclude-dir=build",
                "--exclude-dir=.next",
                "--exclude=*.min.js",
                "--exclude=*.min.css",
                "--exclude=package-lock.json",
                "--exclude=yarn.lock",
            ])

            # Add pattern and path
            grep_args.extend([pattern, search_path])

            # Execute grep with head to limit results
            cmd = " ".join(f'"{arg}"' if " " in arg else arg for arg in grep_args)
            cmd = f"{cmd} | head -n {max_results * 5}"  # Allow for context lines

            result = container.exec_run(["sh", "-c", cmd], workdir=chat_workspace)

            output = result.output.decode('utf-8', errors='replace')

            # Parse results
            matches = []
            match_count = 0

            for line in output.split('\n'):
                if not line.strip():
                    continue

                if match_count >= max_results:
                    break

                # Parse grep output: file:line:content or file-line-content (context)
                if ':' in line or (context_lines > 0 and '-' in line):
                    # Try to parse as grep output
                    parts = line.split(':', 2) if ':' in line else line.split('-', 2)
                    if len(parts) >= 3:
                        file_path = parts[0]
                        try:
                            line_num = int(parts[1])
                            content = parts[2] if len(parts) > 2 else ""

                            # Make path relative to workspace
                            if file_path.startswith(chat_workspace):
                                file_path = file_path[len(chat_workspace):].lstrip('/')

                            matches.append({
                                "file": file_path,
                                "line": line_num,
                                "content": content[:500],  # Truncate long lines
                                "is_match": ':' in line  # True for matches, False for context
                            })
                            match_count += 1
                        except (ValueError, IndexError):
                            continue

            return {
                "success": True,
                "data": {
                    "pattern": pattern,
                    "path": path,
                    "matches": matches,
                    "match_count": len([m for m in matches if m.get("is_match", True)]),
                    "total_results": len(matches),
                    "truncated": match_count >= max_results
                }
            }

        except Exception as e:
            logger.error(f"Failed to search code: {e}")
            return {"success": False, "error": str(e)}

    def write_file(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                  sync_mode: bool, path: str, content: str, model_metadata: Optional[dict] = None,
                  is_base64: bool = False) -> dict:
        """Write content to file."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Ensure chat workspace directory exists
            container.exec_run(["mkdir", "-p", chat_workspace, "/workspace/tmp",
                                "/workspace/.pip-packages", "/workspace/.pip-cache",
                                "/workspace/.npm-cache", "/workspace/.npm-global"])

            # Translate path to chat-scoped path
            import os as os_module

            # SECURITY: Validate and normalize path to prevent path traversal attacks (CWE-22, CWE-59)
            is_valid, actual_path, relative_path = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {
                    "success": False,
                    "error": "Invalid path: directory traversal not allowed"
                }

            # SECURITY: Enforce file size limits to prevent resource exhaustion (CWE-400)
            content_size = len(content.encode('utf-8') if isinstance(content, str) else content)
            if content_size > MAX_FILE_SIZE_BYTES:
                logger.error(f"[SECURITY] File size limit exceeded: {content_size} bytes > {MAX_FILE_SIZE_BYTES} bytes for {path}")
                return {
                    "success": False,
                    "error": f"File too large: {content_size / (1024*1024):.1f}MB exceeds limit of {MAX_FILE_SIZE_BYTES / (1024*1024):.0f}MB"
                }

            # Create parent directories if they don't exist
            parent_dir = os_module.path.dirname(actual_path)
            if parent_dir and parent_dir != '/':
                container.exec_run(["mkdir", "-p", parent_dir], workdir=chat_workspace)

            # Simple logic: only auto-rename for UI creating new empty files
            renamed = False
            original_path = path
            is_ui_new_file = content == '' and model_metadata is None

            if is_ui_new_file:
                # UI creating new file - check if exists and auto-rename
                check_result = container.exec_run(["test", "-f", actual_path])
                if check_result.exit_code == 0:  # File exists
                    base_path = os_module.path.dirname(relative_path)
                    filename = os_module.path.basename(relative_path)
                    name_parts = os_module.path.splitext(filename)
                    name_without_ext = name_parts[0]
                    extension = name_parts[1]

                    counter = 1
                    while True:
                        new_filename = f"{name_without_ext} ({counter}){extension}"
                        new_relative_path = os_module.path.join(base_path, new_filename) if base_path else new_filename
                        new_actual_path = f"{chat_workspace}/{new_relative_path}".replace("//", "/")

                        check_result = container.exec_run(["test", "-f", new_actual_path])
                        if check_result.exit_code != 0:  # File doesn't exist
                            actual_path = new_actual_path
                            path = f"/workspace/{new_relative_path}"
                            renamed = True
                            break
                        counter += 1

                        if counter > 100:
                            break
            # For all other cases (AI writes, UI saves) - allow normal overwrite

            # Encode content to base64 to safely handle special characters
            import base64
            import shlex

            # If content is already base64 (binary files from frontend), use as-is
            # Otherwise, encode text content to base64
            if is_base64:
                # Content is already base64-encoded (binary file from frontend)
                encoded_content = content
            else:
                # Text file - encode to base64
                encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')

            # Escape paths

            # Create parent directory
            parent_dir = os_module.path.dirname(actual_path)
            if parent_dir and parent_dir != '/':
                container.exec_run(["mkdir", "-p", parent_dir])

            exec_kwargs = {} if path.startswith("/tmp/") else {"workdir": chat_workspace}

            # Special case: empty files
            if not encoded_content:
                # Directly create empty file without temp file overhead
                result = container.exec_run(
                    ["touch", actual_path],
                    **exec_kwargs
                )
                if result.exit_code != 0:
                    error_msg = result.output.decode('utf-8') if hasattr(result.output, 'decode') else str(result.output)
                    return {"success": False, "error": f"Failed to create empty file: {error_msg}"}
            else:
                # For large files, we need to write the base64 content in chunks to a temp file
                # then decode it with Python - this completely avoids ARG_MAX limits
                import uuid
                temp_b64_file = f"/tmp/upload_{uuid.uuid4().hex}.b64"

                # Write base64 content in chunks to temp file
                chunk_size = 50000  # 50KB chunks - well below ARG_MAX
                for i in range(0, len(encoded_content), chunk_size):
                    chunk = encoded_content[i:i+chunk_size]
                    redirect = ">" if i == 0 else ">>"
                    chunk_result = container.exec_run(
                        ["sh", "-c", f"printf '%s' {shlex.quote(chunk)} {redirect} {temp_b64_file}"]
                    )
                    if chunk_result.exit_code != 0:
                        # Clean up temp file
                        container.exec_run(["rm", "-f", temp_b64_file])
                        error_msg = chunk_result.output.decode('utf-8') if hasattr(chunk_result.output, 'decode') else str(chunk_result.output)
                        return {"success": False, "error": f"Failed to write temp file: {error_msg}"}

                # Now decode the temp file with Python
                python_code = f"""
import base64
with open({repr(temp_b64_file)}, 'r') as f:
    content = f.read()
with open({repr(actual_path)}, 'wb') as f:
    f.write(base64.b64decode(content))
"""

                result = container.exec_run(
                    ["python3", "-c", python_code],
                    **exec_kwargs
                )

                # Clean up temp file
                container.exec_run(["rm", "-f", temp_b64_file])

                if result.exit_code != 0:
                    error_msg = result.output.decode('utf-8') if hasattr(result.output, 'decode') else str(result.output)
                    return {"success": False, "error": f"Failed to decode file: {error_msg}"}

            # Store model metadata as JSON sidecar file if provided
            if model_metadata:
                try:
                    import json
                    import time

                    # Create metadata directory structure in workspace
                    # Using metadata-{chat_id} folder for isolation (separate from chat files)

                    # Get metadata base path for this chat
                    metadata_base = self._get_metadata_base_path(chat_id, conversation_id)

                    # SECURITY: Use safe metadata path construction to prevent traversal (CWE-22)
                    is_valid_meta, meta_dir, meta_path = self._get_safe_metadata_path(path, metadata_base)
                    if not is_valid_meta:
                        logger.warning(f"[SECURITY] Skipping metadata for invalid path: {path}")
                    else:
                        # Ensure metadata directory exists
                        container.exec_run(["mkdir", "-p", meta_dir])

                        # Check if metadata file exists to determine if this is creation or modification
                        meta_check = container.exec_run(["test", "-f", meta_path])
                        is_creation = meta_check.exit_code != 0

                        # Build metadata structure
                        timestamp = time.time()
                        metadata_content = {}

                        if is_creation:
                            # First time creating the file
                            metadata_content = {
                                "created_by": {
                                    "model_name": model_metadata.get("model_name"),
                                    "model_id": model_metadata.get("model_id"),
                                    "provider": model_metadata.get("provider"),
                                    "model_icon_slug": model_metadata.get("model_icon_slug"),
                                    "model_icon_url": model_metadata.get("model_icon_url"),
                                    "provider_icon_slug": model_metadata.get("provider_icon_slug"),
                                    "provider_icon_url": model_metadata.get("provider_icon_url"),
                                    "message_id": model_metadata.get("message_id"),
                                    "timestamp": timestamp
                                },
                                "modified_by": {
                                    "model_name": model_metadata.get("model_name"),
                                    "model_id": model_metadata.get("model_id"),
                                    "provider": model_metadata.get("provider"),
                                    "model_icon_slug": model_metadata.get("model_icon_slug"),
                                    "model_icon_url": model_metadata.get("model_icon_url"),
                                    "provider_icon_slug": model_metadata.get("provider_icon_slug"),
                                    "provider_icon_url": model_metadata.get("provider_icon_url"),
                                    "message_id": model_metadata.get("message_id"),
                                    "timestamp": timestamp
                                }
                            }
                        else:
                            # File being modified - read existing metadata to preserve created_by
                            read_meta_result = container.exec_run(["cat", meta_path])
                            if read_meta_result.exit_code == 0:
                                existing_metadata = json.loads(read_meta_result.output.decode('utf-8'))
                                metadata_content = {
                                    "created_by": existing_metadata.get("created_by"),
                                    "modified_by": {
                                        "model_name": model_metadata.get("model_name"),
                                        "model_id": model_metadata.get("model_id"),
                                        "provider": model_metadata.get("provider"),
                                        "model_icon_slug": model_metadata.get("model_icon_slug"),
                                        "model_icon_url": model_metadata.get("model_icon_url"),
                                        "provider_icon_slug": model_metadata.get("provider_icon_slug"),
                                        "provider_icon_url": model_metadata.get("provider_icon_url"),
                                        "message_id": model_metadata.get("message_id"),
                                        "timestamp": timestamp
                                    }
                                }

                        # Write metadata file
                        meta_json = json.dumps(metadata_content)
                        encoded_meta = base64.b64encode(meta_json.encode('utf-8')).decode('ascii')
                        escaped_meta_path = shlex.quote(meta_path)

                        container.exec_run(
                            ["sh", "-c", f"echo '{encoded_meta}' | base64 -d > {escaped_meta_path}"]
                        )

                        logger.info(f"Stored metadata for file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to store metadata for {path}: {e}")

            response = {"success": True, "path": path}
            if renamed:
                original_filename = os_module.path.basename(original_path)
                new_filename = os_module.path.basename(path)
                response["renamed"] = True
                response["message"] = f"A file named '{original_filename}' already exists. Created as '{new_filename}' instead."
            return response

        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            return {"success": False, "error": str(e)}

    def _normalize_escaped_content(self, content: str) -> str:
        """
        Normalize over-escaped content from LLM tool calls.
        Some models double-escape strings when constructing tool arguments.
        E.g., they send '\\"' instead of '"' and '\\n' instead of newline.
        """
        import codecs
        normalized = content

        # Remove leading/trailing quotes if present (model wrapping in extra quotes)
        if normalized.startswith('"') and normalized.endswith('"'):
            normalized = normalized[1:-1]
        elif normalized.startswith("'") and normalized.endswith("'"):
            normalized = normalized[1:-1]

        # Try to decode unicode escapes (handles \\n -> \n, \\" -> ", etc.)
        try:
            # Use unicode_escape to convert escape sequences
            normalized = codecs.decode(normalized, 'unicode_escape')
        except (UnicodeDecodeError, ValueError):
            # If decoding fails, try manual replacement of common escapes
            normalized = normalized.replace('\\n', '\n')
            normalized = normalized.replace('\\t', '\t')
            normalized = normalized.replace('\\"', '"')
            normalized = normalized.replace("\\'", "'")
            normalized = normalized.replace('\\\\', '\\')

        return normalized

    def edit_file(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                  sync_mode: bool, path: str, old_content: str, new_content: str) -> dict:
        """Edit file by replacing old content with new content."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # SECURITY: Validate path to prevent traversal and symlink attacks (CWE-22, CWE-59)
            is_valid, actual_path, _ = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {"success": False, "error": "Invalid path: access denied"}

            # Read current file content (don't use shlex.quote with list-style exec_run)
            read_result = container.exec_run(["cat", actual_path])

            if read_result.exit_code != 0:
                return {"success": False, "error": f"File not found: {path}"}

            current_content = read_result.output.decode('utf-8')

            # Check if old_content exists in the file
            # First try direct match, then try with normalized (unescaped) content
            actual_old_content = old_content
            actual_new_content = new_content

            if old_content not in current_content:
                # Try normalizing escaped content (some models double-escape strings)
                normalized_old = self._normalize_escaped_content(old_content)
                if normalized_old in current_content:
                    actual_old_content = normalized_old
                    # Also normalize new_content to match
                    actual_new_content = self._normalize_escaped_content(new_content)
                    logger.info("edit_file: Using normalized content for matching")

            if actual_old_content not in current_content:
                return {
                    "success": False,
                    "error": "Old content not found in file. The file may have been modified. Please read the file first to see current content."
                }

            # Replace old content with new content (using actual/normalized versions)
            updated_content = current_content.replace(actual_old_content, actual_new_content, 1)

            # Generate unified diff for visual display
            import difflib
            diff_lines = list(difflib.unified_diff(
                current_content.splitlines(keepends=True),
                updated_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm=''
            ))
            diff_output = ''.join(diff_lines)

            # Write back the updated content
            import base64
            import shlex
            encoded_content = base64.b64encode(updated_content.encode('utf-8')).decode('ascii')
            escaped_path = shlex.quote(actual_path)  # Need shell escaping for sh -c
            write_result = container.exec_run(
                ["sh", "-c", f"echo '{encoded_content}' | base64 -d > {escaped_path}"],
                workdir=chat_workspace
            )

            if write_result.exit_code != 0:
                return {"success": False, "error": write_result.output.decode('utf-8')}

            return {
                "success": True,
                "path": path,
                "diff": diff_output
            }

        except Exception as e:
            logger.error(f"Failed to edit file: {e}")
            return {"success": False, "error": str(e)}

    def delete_file(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                   sync_mode: bool, path: str) -> dict:
        """Delete file or directory."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # SECURITY: Validate path to prevent traversal and symlink attacks (CWE-22, CWE-59)
            is_valid, actual_path, _ = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {"success": False, "error": "Invalid path: access denied"}

            result = container.exec_run(["rm", "-rf", actual_path], workdir=chat_workspace)

            if result.exit_code != 0:
                return {"success": False, "error": result.output.decode('utf-8')}

            return {"success": True, "path": path}

        except Exception as e:
            logger.error(f"Failed to delete: {e}")
            return {"success": False, "error": str(e)}

    def rename_file(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                   sync_mode: bool, old_path: str, new_path: str) -> dict:
        """Rename file or directory."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # SECURITY: Validate both paths to prevent traversal and symlink attacks (CWE-22, CWE-59)
            is_valid_old, actual_old_path, _ = self._validate_and_normalize_path(old_path, chat_workspace, container)
            if not is_valid_old:
                return {"success": False, "error": "Invalid source path: access denied"}

            is_valid_new, actual_new_path, _ = self._validate_and_normalize_path(new_path, chat_workspace, container)
            if not is_valid_new:
                return {"success": False, "error": "Invalid destination path: access denied"}

            result = container.exec_run(["mv", actual_old_path, actual_new_path], workdir=chat_workspace)

            if result.exit_code != 0:
                return {"success": False, "error": result.output.decode('utf-8')}

            return {"success": True, "old_path": old_path, "new_path": new_path}

        except Exception as e:
            logger.error(f"Failed to rename: {e}")
            return {"success": False, "error": str(e)}

    def create_directory(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                        sync_mode: bool, path: str, model_metadata: Optional[dict] = None) -> dict:
        """Create directory."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # SECURITY: Validate path to prevent traversal attacks (CWE-22)
            # Note: container not passed for symlink check since directory doesn't exist yet
            is_valid, actual_path, relative_path = self._validate_and_normalize_path(path, chat_workspace)
            if not is_valid:
                return {"success": False, "error": "Invalid path: access denied"}

            result = container.exec_run(["mkdir", "-p", actual_path], workdir=chat_workspace)

            if result.exit_code != 0:
                return {"success": False, "error": result.output.decode('utf-8')}

            # Store model metadata as JSON sidecar file if provided
            if model_metadata:
                try:
                    import json
                    import time
                    import base64
                    import shlex

                    # Get metadata base path for this chat
                    metadata_base = self._get_metadata_base_path(chat_id, conversation_id)

                    # SECURITY: Use safe metadata path construction to prevent traversal (CWE-22)
                    # Strip trailing slash for directory paths before passing to helper
                    clean_path = path.rstrip('/')
                    is_valid_meta, meta_dir, meta_path = self._get_safe_metadata_path(clean_path, metadata_base)
                    if not is_valid_meta:
                        logger.warning(f"[SECURITY] Skipping metadata for invalid directory path: {path}")
                    else:
                        # Ensure metadata directory exists
                        container.exec_run(["mkdir", "-p", meta_dir])

                        # Build metadata structure
                        timestamp = time.time()
                        metadata_content = {
                            "created_by": {
                                "model_name": model_metadata.get("model_name"),
                                "model_id": model_metadata.get("model_id"),
                                "provider": model_metadata.get("provider"),
                                "model_icon_slug": model_metadata.get("model_icon_slug"),
                                "model_icon_url": model_metadata.get("model_icon_url"),
                                "provider_icon_slug": model_metadata.get("provider_icon_slug"),
                                "provider_icon_url": model_metadata.get("provider_icon_url"),
                                "message_id": model_metadata.get("message_id"),
                                "timestamp": timestamp
                            }
                        }

                        # Write metadata file
                        meta_json = json.dumps(metadata_content)
                        encoded_meta = base64.b64encode(meta_json.encode('utf-8')).decode('ascii')
                        escaped_meta_path = shlex.quote(meta_path)

                        container.exec_run(
                            ["sh", "-c", f"echo '{encoded_meta}' | base64 -d > {escaped_meta_path}"]
                        )

                        logger.info(f"Stored metadata for directory: {path}")
                except Exception as e:
                    logger.warning(f"Failed to store metadata for {path}: {e}")

            return {"success": True, "path": path}

        except Exception as e:
            logger.error(f"Failed to create directory: {e}")
            return {"success": False, "error": str(e)}

    def get_file_metadata(self, user_id: str, conversation_id: str, chat_id: Optional[str],
                         sync_mode: bool, path: str) -> dict:
        """Get file metadata including timestamps and size."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # SECURITY: Validate path to prevent traversal and symlink attacks (CWE-22, CWE-59)
            is_valid, actual_path, _ = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {"success": False, "error": "Invalid path: access denied"}

            # Check if file exists
            result = container.exec_run(["test", "-f", actual_path], workdir=chat_workspace)
            if result.exit_code != 0:
                return {"success": False, "error": f"File not found: {path}"}

            # Get file stats using stat command
            # Format: size|access_time|modify_time|change_time
            stat_result = container.exec_run(
                ["stat", "-c", "%s|%X|%Y|%Z", actual_path],
                workdir=chat_workspace
            )

            if stat_result.exit_code != 0:
                return {"success": False, "error": "Failed to get file stats"}

            # Parse stat output
            stat_output = stat_result.output.decode('utf-8').strip()
            size, atime, mtime, ctime = stat_output.split('|')

            # Extract file name from path
            import os as os_module
            file_name = os_module.path.basename(path)

            # Build basic metadata response
            metadata = {
                "path": path,
                "name": file_name,
                "size": int(size),
                "created_at": ctime,  # Unix timestamp
                "modified_at": mtime,  # Unix timestamp
            }

            # Try to read model metadata from JSON sidecar file (stored in workspace)
            try:
                import json

                # Get metadata base path for this chat
                metadata_base = self._get_metadata_base_path(chat_id, conversation_id)

                # SECURITY: Use safe metadata path construction to prevent traversal (CWE-22)
                is_valid_meta, _, meta_path = self._get_safe_metadata_path(path, metadata_base)
                if not is_valid_meta:
                    logger.warning(f"[SECURITY] Skipping metadata read for invalid path: {path}")
                else:
                    # Check if metadata file exists
                    meta_check = container.exec_run(["test", "-f", meta_path])

                    if meta_check.exit_code == 0:
                        # Read metadata file
                        read_result = container.exec_run(["cat", meta_path])

                        if read_result.exit_code == 0:
                            meta_content = json.loads(read_result.output.decode('utf-8'))

                            # Add model tracking info to metadata
                            if "created_by" in meta_content:
                                metadata["created_by"] = meta_content["created_by"]

                            if "modified_by" in meta_content:
                                metadata["modified_by"] = meta_content["modified_by"]

                            logger.info(f"Retrieved model metadata for file: {path}")
                        else:
                            logger.warning(f"Failed to read metadata file: {meta_path}")
                    else:
                        logger.debug(f"No metadata file found for: {path}")

            except Exception as e:
                logger.warning(f"Error reading metadata for {path}: {e}")

            return {"success": True, "metadata": metadata}

        except Exception as e:
            logger.error(f"Failed to get file metadata: {e}")
            return {"success": False, "error": str(e)}

    def read_excel(self, user_id: str, conversation_id: str, chat_id: str, sync_mode: bool, path: str, sheet_index: int = 0) -> dict:
        """Read an Excel file with formulas using openpyxl."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Validate and normalize path (with symlink check)
            is_valid, actual_path, relative_path = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {"success": False, "error": "Invalid file path"}

            # Generate Python script using excel_handler
            python_script = excel_handler.get_read_excel_script(actual_path, sheet_index)

            # Log the script for debugging
            logger.info(f"Executing Excel read script for {actual_path}")
            logger.debug(f"Python script:\n{python_script}")

            result = container.exec_run(
                ["python3", "-c", python_script],
                workdir=chat_workspace
            )

            # Decode output for logging
            output = result.output.decode('utf-8') if hasattr(result.output, 'decode') else str(result.output)
            logger.debug(f"Script output (exit_code={result.exit_code}):\n{output}")

            if result.exit_code != 0:
                logger.error(f"Excel read failed with exit code {result.exit_code}: {output}")
                return {"success": False, "error": f"Failed to read Excel file: {output}"}

            # Parse JSON output
            try:
                excel_data = json.loads(output)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Excel output as JSON: {e}\nOutput: {output}")
                return {"success": False, "error": f"Invalid JSON output: {str(e)}"}

            if "error" in excel_data:
                return {"success": False, "error": excel_data["error"]}

            return {"success": True, **excel_data}

        except Exception as e:
            logger.error(f"Failed to read Excel file: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def update_excel_cell(self, user_id: str, conversation_id: str, chat_id: str, sync_mode: bool,
                         path: str, sheet_index: int, row: int, col: int,
                         value: str = None, formula: str = None) -> dict:
        """Update an Excel cell with value or formula using openpyxl."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Validate and normalize path (with symlink check)
            is_valid, actual_path, relative_path = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {"success": False, "error": "Invalid file path"}

            # Generate Python script using excel_handler
            python_script = excel_handler.get_update_cell_script(
                actual_path, sheet_index, row, col, value, formula
            )

            logger.info(f"Executing Excel update script for {actual_path}")
            logger.debug(f"Python script:\n{python_script}")

            result = container.exec_run(
                ["python3", "-c", python_script],
                workdir=chat_workspace
            )

            # Decode output for logging
            output = result.output.decode('utf-8') if hasattr(result.output, 'decode') else str(result.output)
            logger.debug(f"Script output (exit_code={result.exit_code}):\n{output}")

            if result.exit_code != 0:
                logger.error(f"Excel update failed with exit code {result.exit_code}: {output}")
                return {"success": False, "error": f"Failed to update Excel cell: {output}"}

            # Parse JSON output
            if not output or not output.strip():
                logger.error("Empty output from Excel update script")
                return {"success": False, "error": "Script produced no output"}

            try:
                update_data = json.loads(output)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Excel update output as JSON: {e}\nOutput: {output}")
                return {"success": False, "error": f"Invalid JSON output: {str(e)}"}

            if "error" in update_data:
                return {"success": False, "error": update_data["error"]}

            return {"success": True, **update_data}

        except Exception as e:
            logger.error(f"Failed to update Excel cell: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def batch_update_excel_cells(self, user_id: str, conversation_id: str, chat_id: str, sync_mode: bool,
                                 path: str, sheet_index: int, updates: list) -> dict:
        """
        Update multiple Excel cells in batch (MUCH faster than multiple update_excel_cell calls).

        Args:
            updates: List of dicts with format: [{"row": 0, "col": 0, "value": "x", "formula": None}, ...]
        """
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Validate and normalize path (with symlink check)
            is_valid, actual_path, relative_path = self._validate_and_normalize_path(path, chat_workspace, container)
            if not is_valid:
                return {"success": False, "error": "Invalid file path"}

            # Generate Python script using excel_handler
            python_script = excel_handler.get_batch_update_cells_script(
                actual_path, sheet_index, updates
            )

            logger.info(f"Executing Excel batch update script for {actual_path} ({len(updates)} cells)")

            result = container.exec_run(
                ["python3", "-c", python_script],
                workdir=chat_workspace
            )

            # Decode output for logging
            output = result.output.decode('utf-8') if hasattr(result.output, 'decode') else str(result.output)
            logger.debug(f"Script output (exit_code={result.exit_code}):\n{output}")

            if result.exit_code != 0:
                logger.error(f"Excel batch update failed with exit code {result.exit_code}: {output}")
                return {"success": False, "error": f"Failed to batch update Excel cells: {output}"}

            # Parse JSON output
            if not output or not output.strip():
                logger.error("Empty output from Excel batch update script")
                return {"success": False, "error": "Script produced no output"}

            try:
                update_data = json.loads(output)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Excel batch update output as JSON: {e}\nOutput: {output}")
                return {"success": False, "error": f"Invalid JSON output: {str(e)}"}

            if "error" in update_data:
                return {"success": False, "error": update_data["error"]}

            return {"success": True, **update_data}

        except Exception as e:
            logger.error(f"Failed to batch update Excel cells: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def delete_chat_workspace(self, user_id: str, conversation_id: str, chat_id: Optional[str], sync_mode: bool) -> dict:
        """
        Delete entire workspace for a specific chat.
        This removes all files and metadata for the chat.

        Args:
            user_id: User ID
            conversation_id: Conversation ID
            chat_id: Chat ID (if None, deletes conversation workspace)
            sync_mode: Sync mode flag

        Returns:
            dict: Success/failure status
        """
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        chat_workspace = self._get_chat_workspace_path(chat_id, conversation_id)
        metadata_path = self._get_metadata_base_path(chat_id, conversation_id)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # Delete chat workspace directory
            workspace_result = container.exec_run(
                ["rm", "-rf", chat_workspace],
                workdir="/workspace"
            )

            if workspace_result.exit_code != 0:
                output = workspace_result.output.decode('utf-8') if hasattr(workspace_result.output, 'decode') else str(workspace_result.output)
                logger.error(f"Failed to delete workspace {chat_workspace}: {output}")
                return {"success": False, "error": f"Failed to delete workspace: {output}"}

            # Delete metadata directory
            metadata_result = container.exec_run(
                ["rm", "-rf", metadata_path],
                workdir="/workspace"
            )

            if metadata_result.exit_code != 0:
                output = metadata_result.output.decode('utf-8') if hasattr(metadata_result.output, 'decode') else str(metadata_result.output)
                logger.warning(f"Failed to delete metadata {metadata_path}: {output}")
                # Don't fail if metadata deletion fails, as workspace is the primary concern

            logger.info(f"Successfully deleted workspace and metadata for chat_id={chat_id}, conversation_id={conversation_id}")
            return {"success": True, "message": "Workspace deleted successfully"}

        except Exception as e:
            logger.error(f"Failed to delete workspace: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def delete_conversation_workspaces(self, user_id: str, conversation_id: str, sync_mode: bool) -> dict:
        """
        Delete all workspaces for a conversation.
        This removes all chat-* and metadata-* directories associated with the conversation.

        Args:
            user_id: User ID
            conversation_id: Conversation ID
            sync_mode: Sync mode flag

        Returns:
            dict: Success/failure status with count of deleted workspaces
        """
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, None, sync_mode)

        try:
            container = self._get_or_create_sandbox(sandbox_id)

            # List all directories in /workspace that start with "chat-" or "metadata-"
            list_result = container.exec_run(
                ["sh", "-c", "ls -d chat-* metadata-* 2>/dev/null || true"],
                workdir="/workspace"
            )

            if list_result.exit_code == 0:
                output = list_result.output.decode('utf-8') if hasattr(list_result.output, 'decode') else str(list_result.output)
                directories = [d.strip() for d in output.split('\n') if d.strip()]

                deleted_count = 0
                failed = []

                for directory in directories:
                    delete_result = container.exec_run(
                        ["rm", "-rf", directory],
                        workdir="/workspace"
                    )

                    if delete_result.exit_code == 0:
                        deleted_count += 1
                        logger.info(f"Deleted workspace directory: {directory}")
                    else:
                        delete_output = delete_result.output.decode('utf-8') if hasattr(delete_result.output, 'decode') else str(delete_result.output)
                        failed.append(f"{directory}: {delete_output}")
                        logger.error(f"Failed to delete {directory}: {delete_output}")

                if failed:
                    return {
                        "success": False,
                        "error": f"Failed to delete some directories: {'; '.join(failed)}",
                        "deleted_count": deleted_count
                    }

                logger.info(f"Successfully deleted {deleted_count} workspace directories for conversation_id={conversation_id}")
                return {
                    "success": True,
                    "message": f"Deleted {deleted_count} workspace(s)",
                    "deleted_count": deleted_count
                }
            else:
                # No directories found or error listing
                logger.info(f"No workspace directories found for conversation_id={conversation_id}")
                return {
                    "success": True,
                    "message": "No workspaces to delete",
                    "deleted_count": 0
                }

        except Exception as e:
            logger.error(f"Failed to delete conversation workspaces: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ========================================================================
    # MCP Gateway Management
    # ========================================================================
    # MCP servers run as child processes inside the user's sandbox container,
    # managed by the MCP Gateway (mcp-gateway.js). This avoids creating
    # separate containers per MCP server.
    # ========================================================================

    def _ensure_mcp_gateway_running(self, container) -> bool:
        """Ensure the MCP Gateway is running in the container."""
        import time

        # Check if gateway is already running by hitting its health endpoint
        health_check = container.exec_run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "2", "http://127.0.0.1:3100/health"],
            user="sandboxuser"
        )

        if health_check.exit_code == 0 and health_check.output.decode('utf-8').strip() == "200":
            logger.info("MCP Gateway already running")
            return True

        # Start the MCP gateway
        logger.info("Starting MCP Gateway in sandbox container")

        # Start gateway in background
        # The gateway listens on port 3100 for HTTP requests
        start_result = container.exec_run(
            ["sh", "-c", "nohup node /opt/mcp-gateway/mcp-gateway.js > /tmp/mcp-gateway.log 2>&1 &"],
            user="sandboxuser",
            detach=False
        )

        if start_result.exit_code != 0:
            logger.error(f"Failed to start MCP Gateway: {start_result.output.decode('utf-8')}")
            return False

        # Wait for gateway to be ready by polling the health endpoint
        max_attempts = 10
        for attempt in range(max_attempts):
            time.sleep(0.5)

            health_result = container.exec_run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "2", "http://127.0.0.1:3100/health"],
                user="sandboxuser"
            )

            if health_result.exit_code == 0 and health_result.output.decode('utf-8').strip() == "200":
                logger.info(f"MCP Gateway started successfully (attempt {attempt + 1})")
                return True

        # Failed to start - check logs for error
        log_result = container.exec_run(["cat", "/tmp/mcp-gateway.log"], user="sandboxuser")
        logger.error(f"MCP Gateway failed to start after {max_attempts} attempts. Logs: {log_result.output.decode('utf-8')}")
        return False

    def _call_mcp_gateway(self, container, path: str, data: dict, timeout: int = 30) -> dict:
        """Make an HTTP request to the MCP Gateway running in the container."""
        import json
        import shlex

        # Build curl command to call gateway
        json_data = json.dumps(data)
        escaped_data = shlex.quote(json_data)

        curl_cmd = f"curl -s -X POST -H 'Content-Type: application/json' -d {escaped_data} --max-time {timeout} http://127.0.0.1:3100{path}"

        result = container.exec_run(
            ["sh", "-c", curl_cmd],
            user="sandboxuser"
        )

        if result.exit_code != 0:
            return {"error": f"Gateway request failed: {result.output.decode('utf-8')}"}

        try:
            return json.loads(result.output.decode('utf-8'))
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON response: {result.output.decode('utf-8')[:500]}"}

    def _register_egress_whitelist(self, domains: List[str]) -> bool:
        """
        Register domains with the egress proxy's dynamic whitelist.

        The egress proxy exposes a control API on port 8889 that allows
        dynamic addition of whitelisted domains for MCP servers.

        Args:
            domains: List of domains to whitelist

        Returns:
            True if registration succeeded, False otherwise
        """
        if not domains:
            return True

        import urllib.request
        import urllib.error

        try:
            # Call the egress proxy's control API
            # The orchestrator and egress-proxy are on the same Docker network
            url = "http://egress-proxy:8889/whitelist/add"
            data = json.dumps({"domains": domains}).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get("success"):
                    logger.info(f"[Egress] Registered {len(domains)} domains: {domains}")
                    return True
                else:
                    logger.error(f"[Egress] Failed to register domains: {result}")
                    return False

        except urllib.error.URLError as e:
            logger.error(f"[Egress] Failed to connect to proxy control API: {e}")
            return False
        except Exception as e:
            logger.error(f"[Egress] Failed to register domains: {e}")
            return False

    def _unregister_egress_whitelist(self, domains: List[str]) -> bool:
        """
        Remove domains from the egress proxy's dynamic whitelist.

        Args:
            domains: List of domains to remove

        Returns:
            True if removal succeeded, False otherwise
        """
        if not domains:
            return True

        import urllib.request
        import urllib.error

        try:
            url = "http://egress-proxy:8889/whitelist/remove"
            data = json.dumps({"domains": domains}).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get("success"):
                    logger.info(f"[Egress] Unregistered {len(domains)} domains: {domains}")
                    return True
                else:
                    logger.error(f"[Egress] Failed to unregister domains: {result}")
                    return False

        except Exception as e:
            logger.error(f"[Egress] Failed to unregister domains: {e}")
            return False

    def start_mcp_server(
        self,
        user_id: str,
        server_id: str,
        npm_package: str,
        env_vars: Optional[Dict[str, str]] = None,
        allowed_domains: Optional[List[str]] = None,
    ) -> dict:
        """
        Start an MCP server inside the user's sandbox container.

        The MCP server runs as a child process managed by the MCP Gateway,
        not as a separate container. This is much more scalable.

        Args:
            user_id: User who owns the sandbox
            server_id: Unique identifier for this MCP server instance
            npm_package: NPM package to run (e.g., '@brave/brave-search-mcp-server')
            env_vars: Environment variables (API keys, etc.)
            allowed_domains: Domains to whitelist for network egress

        Returns:
            dict with success status and server info
        """
        # Get the user's sandbox container
        sandbox_id = f"sandbox-exec-{user_id}"

        try:
            container = self._get_or_create_sandbox(sandbox_id)
        except Exception as e:
            logger.error(f"Failed to get sandbox for user {user_id}: {e}")
            return {"success": False, "error": f"Failed to get sandbox: {e}"}

        # Ensure MCP gateway is running
        if not self._ensure_mcp_gateway_running(container):
            return {"success": False, "error": "Failed to start MCP Gateway"}

        # Build environment variables for the MCP server
        # These will be passed to the child process
        mcp_env = {}

        # Add egress proxy settings (inherited from sandbox)
        # MCP servers will use the sandbox's egress proxy
        mcp_env["HTTP_PROXY"] = "http://egress-proxy:8888"
        mcp_env["HTTPS_PROXY"] = "http://egress-proxy:8888"
        mcp_env["http_proxy"] = "http://egress-proxy:8888"
        mcp_env["https_proxy"] = "http://egress-proxy:8888"
        mcp_env["NO_PROXY"] = "localhost,127.0.0.1"
        mcp_env["no_proxy"] = "localhost,127.0.0.1"
        mcp_env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"

        # Register allowed domains with the egress proxy's dynamic whitelist
        # This is the proper way to whitelist domains - the proxy has a control API
        if allowed_domains:
            if not self._register_egress_whitelist(allowed_domains):
                logger.warning(f"Failed to register egress whitelist for {server_id}, but continuing...")
            # Also set as env var for reference (not used by proxy, but useful for debugging)
            mcp_env["EGRESS_WHITELIST"] = ",".join(allowed_domains)

        # Add user-provided environment variables (API keys, etc.)
        if env_vars:
            mcp_env.update(env_vars)

        # Call gateway to start the server
        response = self._call_mcp_gateway(container, "/servers/start", {
            "serverId": server_id,
            "npmPackage": npm_package,
            "envVars": mcp_env,
        }, timeout=60)

        if "error" in response:
            logger.error(f"Failed to start MCP server {server_id}: {response['error']}")
            return {"success": False, "error": response["error"]}

        logger.info(f"Started MCP server {server_id} ({npm_package}) in sandbox {sandbox_id}")
        return {
            "success": True,
            "server_id": server_id,
            "npm_package": npm_package,
            "message": response.get("message", "Server started"),
        }

    def stop_mcp_server(self, user_id: str, server_id: str) -> dict:
        """
        Stop an MCP server running in the user's sandbox.

        Args:
            user_id: User who owns the sandbox
            server_id: Server instance to stop

        Returns:
            dict with success status
        """
        sandbox_id = f"sandbox-exec-{user_id}"

        try:
            container = self.docker.containers.get(sandbox_id)
        except Exception as e:
            return {"success": False, "error": f"Sandbox not found: {e}"}

        response = self._call_mcp_gateway(container, "/servers/stop", {
            "serverId": server_id,
        })

        if "error" in response:
            return {"success": False, "error": response["error"]}

        logger.info(f"Stopped MCP server {server_id} in sandbox {sandbox_id}")
        return {"success": True, "message": response.get("message", "Server stopped")}

    def list_mcp_servers(self, user_id: str) -> dict:
        """
        List all MCP servers running in the user's sandbox.

        Args:
            user_id: User who owns the sandbox

        Returns:
            dict with list of running servers
        """
        sandbox_id = f"sandbox-exec-{user_id}"

        try:
            container = self.docker.containers.get(sandbox_id)
        except Exception:
            return {"success": True, "servers": []}  # No sandbox = no servers

        # Check if gateway is running
        check_result = container.exec_run(
            ["pgrep", "-f", "mcp-gateway.js"],
            user="sandboxuser"
        )

        if check_result.exit_code != 0:
            return {"success": True, "servers": []}  # Gateway not running = no servers

        response = self._call_mcp_gateway(container, "/servers", {})

        if "error" in response:
            return {"success": False, "error": response["error"]}

        return {"success": True, "servers": response.get("servers", [])}

    def mcp_server_status(self, user_id: str, server_id: str) -> dict:
        """
        Get status of an MCP server.

        Args:
            user_id: User who owns the sandbox
            server_id: Server instance to check

        Returns:
            dict with server status
        """
        sandbox_id = f"sandbox-exec-{user_id}"

        try:
            container = self.docker.containers.get(sandbox_id)
        except Exception as e:
            return {"running": False, "error": f"Sandbox not found: {e}"}

        response = self._call_mcp_gateway(container, "/servers/status", {
            "serverId": server_id,
        })

        return response

    def discover_mcp_tools(self, user_id: str, server_id: str) -> dict:
        """
        Discover tools available from an MCP server.

        Args:
            user_id: User who owns the sandbox
            server_id: Server instance to query

        Returns:
            dict with list of tools
        """
        import time

        sandbox_id = f"sandbox-exec-{user_id}"

        try:
            container = self.docker.containers.get(sandbox_id)
        except Exception as e:
            return {"success": False, "error": f"Sandbox not found: {e}"}

        # Retry with exponential backoff - MCP server needs time to initialize and discover tools
        max_attempts = 10
        base_wait = 1.0  # Start with 1 second wait

        for attempt in range(max_attempts):
            response = self._call_mcp_gateway(container, "/tools/list", {
                "serverId": server_id,
            })

            if "error" in response:
                return {"success": False, "error": response["error"]}

            tools = response.get("tools", [])
            if tools:
                logger.info(f"Discovered {len(tools)} tools from server {server_id} (attempt {attempt + 1})")
                return {"success": True, "tools": tools}

            # No tools yet - wait and retry
            if attempt < max_attempts - 1:
                wait_time = min(base_wait * (1.5 ** attempt), 5.0)  # Cap at 5 seconds
                logger.debug(f"No tools discovered yet, waiting {wait_time:.1f}s (attempt {attempt + 1}/{max_attempts})")
                time.sleep(wait_time)

        # Return empty if no tools after all attempts
        logger.warning(f"No tools discovered from server {server_id} after {max_attempts} attempts")
        return {"success": True, "tools": []}

    def call_mcp_tool(
        self,
        user_id: str,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: int = 60,
    ) -> dict:
        """
        Call a tool on an MCP server.

        Args:
            user_id: User who owns the sandbox
            server_id: Server instance to call
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            timeout: Execution timeout in seconds

        Returns:
            dict with tool execution result
        """
        sandbox_id = f"sandbox-exec-{user_id}"

        try:
            container = self.docker.containers.get(sandbox_id)
        except Exception as e:
            return {"success": False, "error": f"Sandbox not found: {e}"}

        response = self._call_mcp_gateway(container, "/tools/call", {
            "serverId": server_id,
            "toolName": tool_name,
            "arguments": arguments,
            "timeout": timeout * 1000,  # Convert to milliseconds
        }, timeout=timeout + 5)

        if "error" in response:
            return {"success": False, "error": response["error"]}

        # Check for JSON-RPC error in response
        if response.get("error"):
            return {"success": False, "error": response["error"]}

        return {"success": True, "result": response.get("result")}

    # --- Process Management ---

    def get_container_ip(self, user_id: str, conversation_id: str,
                         chat_id: Optional[str], sync_mode: bool) -> Optional[str]:
        """Get sandbox container IP on the isolated network."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        with self.lock:
            entry = self.sandboxes.get(sandbox_id)
            if not entry:
                return None
            container = entry['container']
            entry['last_used'] = time.time()
        try:
            container.reload()
            networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
            net = networks.get('sandbox_sandbox-isolated', {})
            return net.get('IPAddress')
        except Exception:
            return None

    def start_background_process(self, user_id: str, conversation_id: str,
                                 chat_id: Optional[str], sync_mode: bool,
                                 command: str, chat_workspace: str) -> dict:
        """Start a background process inside sandbox. Returns {pid, command}."""
        import shlex
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        container = self._get_or_create_sandbox(sandbox_id)
        # Ensure tmp dir exists for logs
        container.exec_run(["mkdir", "-p", "/workspace/tmp"], user="sandboxuser")
        # SECURITY: Escape workspace path to prevent shell injection (CWE-78)
        safe_workspace = shlex.quote(chat_workspace)
        # nohup + redirect + echo PID
        wrapped = f'cd {safe_workspace} && nohup {command} > /workspace/tmp/proc-$$.log 2>&1 & echo $!'
        result = container.exec_run(["sh", "-c", wrapped], workdir=chat_workspace, user="sandboxuser")
        pid = result.output.decode().strip()
        return {"pid": int(pid), "command": command}

    def list_processes(self, user_id: str, conversation_id: str,
                       chat_id: Optional[str], sync_mode: bool) -> list:
        """List running processes (non-system) inside sandbox via /proc (no ps required)."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        with self.lock:
            entry = self.sandboxes.get(sandbox_id)
            if not entry:
                return []
            container = entry['container']
            entry['last_used'] = time.time()
        # Use /proc to list processes — works in minimal containers without procps
        script = '''
for pid_dir in /proc/[0-9]*/; do
  pid=$(basename "$pid_dir")
  cmd=$(tr '\\0' ' ' < "$pid_dir/cmdline" 2>/dev/null)
  [ -z "$cmd" ] && continue
  echo "$pid|$cmd"
done
'''
        result = container.exec_run(["sh", "-c", script], user="sandboxuser")
        lines = result.output.decode().strip().split('\n') if result.output else []
        processes = []
        skip_patterns = {'tail -f /dev/null', '/bin/sh', 'sh -c'}
        for line in lines:
            if '|' not in line:
                continue
            pid_str, cmd = line.split('|', 1)
            cmd = cmd.strip()
            if not cmd or any(s in cmd for s in skip_patterns):
                continue
            try:
                processes.append({"pid": int(pid_str), "command": cmd})
            except ValueError:
                continue
        return processes

    def stop_process(self, user_id: str, conversation_id: str,
                     chat_id: Optional[str], sync_mode: bool, pid: int) -> bool:
        """Kill a process by PID inside sandbox (uses sh built-in kill)."""
        sandbox_id = self._generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)
        with self.lock:
            entry = self.sandboxes.get(sandbox_id)
            if not entry:
                return False
            container = entry['container']
        result = container.exec_run(["sh", "-c", f"kill {pid}"], user="sandboxuser")
        return result.exit_code == 0
