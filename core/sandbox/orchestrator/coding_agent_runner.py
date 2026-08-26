"""
Coding Agent Runner

Coordinates Coding Agent execution inside user sandboxes.
Creates isolated job directories with workspace access and runs the agent script.
Captures file versions before/after execution for history tracking.
"""

import uuid
import json
import shlex
import logging
import asyncio
import time
import hashlib
import tarfile
import io
import secrets
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from workspace_client import get_workspace_client
import coding_agent_prompts
import opencode_harness
from budget_guard import over_budget, terminate_command
from coding_harness import (
    IMPLEMENT_MODE,
    PLAN_MODE,
    AgentOutputAdapter,
    create_adapter,
    parse_run_output,
    resolve_harness,
)

logger = logging.getLogger(__name__)

# In-memory progress store for real-time progress tracking.
# Keyed by "{user_id}:{chat_id}". Updated during execution, read by progress endpoint.
# This bypasses the file-based approach which fails when Docker's put_archive
# can't write to tmpfs-mounted workspace directories.
_progress_store: Dict[str, dict] = {}

#: Hosts the ask-user relay must reach past the egress proxy: itself
#: (loopback) and the orchestrator, which the relay calls back into.
RELAY_NO_PROXY_HOSTS = "localhost,127.0.0.1,sterna-orchestrator"


def get_progress_from_store(user_id: str, chat_id: str) -> Optional[dict]:
    """Get cached progress data for a coding agent execution."""
    key = f"{user_id}:{chat_id}"
    return _progress_store.get(key)


@dataclass
class CodingAgentConfig:
    """Configuration for Coding Agent execution."""
    task: str
    model: str
    api_key: str
    allowed_tools: List[str]
    max_iterations: int
    workspace_path: str
    job_dir: str
    mcp_servers: Optional[Dict[str, Any]] = None  # MCP server configs for --mcp-config
    mode: str = "auto"  # "plan", "implement", or "auto"
    plan_id: Optional[str] = None  # Plan ID for implement mode
    plan_content: Optional[str] = None  # Full plan content for implement mode
    sub_agents: Optional[List[Dict[str, Any]]] = None  # Sub-agent defs as {name, markdown} dicts
    user_model_preferences: Optional[Dict[str, str]] = None  # Tier→model mapping from user prefs
    harness: str = ""  # CLI harness that runs the job


@dataclass
class CodingAgentResult:
    """Result of Coding Agent execution."""
    success: bool
    job_id: str
    summary: Optional[str] = None
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class FileSnapshot:
    """Snapshot of a file for before/after comparison."""
    path: str
    content: bytes
    sha256: str
    size: int


class CodingAgentRunner:
    """
    Runs Coding Agent agent inside user sandboxes.

    Creates an isolated job directory at /agents/coding-agent-{job_id}/
    with a symlink to the user's workspace. The agent runs with
    restricted environment variables for OpenRouter access.

    Also captures file versions before/after execution for history tracking.
    """

    # Execution timeout in seconds
    EXECUTION_TIMEOUT = 600  # 10 minutes

    # Valid tools that can be allowed
    VALID_TOOLS = {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}

    # Max file size for version capture (10MB)
    MAX_VERSION_FILE_SIZE = 10 * 1024 * 1024

    # SECURITY: Dangerous config file patterns that could be exploited
    # These files could inject malicious hooks, MCP servers, or settings
    DANGEROUS_CONFIG_PATTERNS = [
        ".claude",           # Claude config directory
        ".clauderc",         # Claude RC file
        "claude.config.json", # Alternative config file
        ".mcp.json",         # MCP server config
        "opencode.json",     # opencode config
        "opencode.jsonc",    # opencode config, comment-tolerant form
        ".opencode",         # opencode config/agent/plan directory
    ]

    def _config_scan_directories(self, workspace_path: str) -> List[str]:
        """The workspace and every directory above it.

        opencode looks for ``opencode.json`` in the working directory
        and each of its ancestors, so a file planted one level up
        reaches the run just as one inside the workspace would.
        """
        directories = [workspace_path]
        current = workspace_path.rstrip("/")
        while "/" in current and current:
            current = current.rsplit("/", 1)[0]
            directories.append(current or "/")
        return directories

    async def _scan_for_dangerous_configs(
        self,
        container,
        workspace_path: str
    ) -> tuple[bool, List[str]]:
        """
        SECURITY: Scan workspace for dangerous agent config files.

        Users could plant malicious config files via the terminal that would
        be read when the coding agent runs, potentially:
        - Defining malicious MCP servers that execute arbitrary code
        - Injecting hooks that run on agent events
        - Modifying agent behavior via settings

        Returns:
            (is_safe, list_of_dangerous_files_found)
        """
        candidates = [
            f"{directory.rstrip('/')}/{pattern}"
            for directory in self._config_scan_directories(workspace_path)
            for pattern in self.DANGEROUS_CONFIG_PATTERNS
        ]
        probe = "; ".join(f'test -e "{path}" && echo "{path}"' for path in candidates)
        result = container.exec_run(
            ["sh", "-c", f"{probe}; true"],
            workdir=workspace_path,
            user="sandboxuser"
        )
        output = result.output.decode().strip() if result.output else ""
        dangerous_found = [line.strip() for line in output.split("\n") if line.strip()]

        for found in dangerous_found:
            logger.warning(f"[SECURITY] Dangerous config file found: {found}")

        if dangerous_found:
            logger.error(
                f"[SECURITY] Blocking Coding Agent execution - {len(dangerous_found)} "
                f"dangerous config file(s) found: {dangerous_found}"
            )
            return (False, dangerous_found)

        return (True, [])

    async def _setup_ephemeral_home(
        self,
        container,
        job_id: str,
    ) -> str:
        """
        SECURITY: Create an ephemeral HOME directory for this job.

        This prevents any persistent config files from being read and
        ensures each execution starts with a clean, controlled
        environment rather than from a file under HOME, and what it does
        read from the ephemeral home is created for it: the data
        directory a planning run's plan lands in, and the configuration
        directory the job's sub-agents are planted in
        (`opencode_harness.subagent_dir_for`).

        Args:
            container: Docker container
            job_id: Unique job identifier

        Returns:
            Path to the ephemeral home directory
        """
        ephemeral_home = f"/tmp/opencode-home-{job_id}"

        setup_cmd = f'mkdir -p "{ephemeral_home}" && chmod 700 "{ephemeral_home}"'
        result = container.exec_run(
            ["sh", "-c", setup_cmd],
            user="sandboxuser"
        )

        if result.exit_code != 0:
            logger.warning(
                f"[SECURITY] Failed to create ephemeral home: {ephemeral_home}, "
                f"falling back to /home/sandboxuser"
            )
            return "/home/sandboxuser"

        container.exec_run(
            ["sh", "-c", f'mkdir -p "{opencode_harness.plans_dir_for(ephemeral_home)}"'],
            user="sandboxuser",
        )
        logger.info(f"[SECURITY] Created ephemeral home directory: {ephemeral_home}")
        return ephemeral_home

    def _plant_sub_agents(
        self,
        container,
        ephemeral_home: str,
        sub_agents: Optional[List[Dict[str, Any]]],
    ) -> None:
        """Put the job's sub-agents where opencode will discover them.

        Each is rewritten into opencode's own agent format
        (`opencode_harness.build_subagent_definition`) and named by its
        file, which is how opencode names an agent.
        """
        if not sub_agents:
            return
        agents_dir = opencode_harness.subagent_dir_for(ephemeral_home)
        write_cmds = [f"mkdir -p {agents_dir}"]
        for agent_def in sub_agents:
            name = agent_def.get("name", "unnamed")
            definition = opencode_harness.build_subagent_definition(
                agent_def.get("markdown", "")
            )
            escaped = definition.replace("'", "'\"'\"'")
            write_cmds.append(f"printf '%s' '{escaped}' > {agents_dir}/{name}.md")

        result = container.exec_run(["sh", "-c", " && ".join(write_cmds)], user="sandboxuser")
        if result.exit_code != 0:
            logger.warning(
                f"[CodingAgent] Failed to write sub-agent files: "
                f"{result.output.decode()[:200] if result.output else 'unknown'}"
            )
        else:
            logger.info(f"[CodingAgent] Wrote {len(sub_agents)} sub-agent files to {agents_dir}")

    def _write_sandbox_file(self, container, path: str, content: str) -> None:
        """Write one file into the sandbox as the unprivileged user."""
        escaped = content.replace("'", "'\"'\"'")
        container.exec_run(
            ["sh", "-c", f"printf '%s' '{escaped}' > {path}"],
            user="sandboxuser",
        )

    async def _prepare_opencode_run(
        self, container, job_dir, ephemeral_home, workspace_path, mode,
        model, api_key, max_iterations, allowed_tools,
        task_file, output_file, full_task, base_env, job_token,
    ) -> tuple:
        """Stage the opencode harness; return its command and environment.

        The ask-user relay and the wrapper that brackets opencode's
        output both live in the ephemeral home, and the job description
        the wrapper reads lives beside the task in the job directory.
        """
        relay_path = f"{ephemeral_home}/mcp-ask-user-opencode.py"
        wrapper_path = f"{ephemeral_home}/opencode-run-wrapper.py"
        spec_path = f"{job_dir}/opencode-job.json"
        here = Path(__file__).parent

        for source, destination in (
            ("mcp_ask_user_opencode.py", relay_path),
            ("opencode_run_wrapper.py", wrapper_path),
        ):
            self._write_sandbox_file(
                container, destination, here.joinpath(source).read_text()
            )

        config = opencode_harness.build_config(
            mode=mode,
            model=model,
            ephemeral_home=ephemeral_home,
            max_steps=max_iterations,
            ask_user_command=["python3", relay_path],
            ask_user_environment={
                "STERNA_USER_ID": self.user_id,
                "STERNA_CHAT_ID": self.chat_id,
                "STERNA_JOB_TOKEN": job_token,
            },
        )
        spec = opencode_harness.build_wrapper_spec(
            mode=mode,
            workspace_path=workspace_path,
            ephemeral_home=ephemeral_home,
            task_file=task_file,
            model=model,
            tools=allowed_tools,
        )
        self._write_sandbox_file(container, spec_path, json.dumps(spec))
        self._write_sandbox_file(container, task_file, full_task)

        env = opencode_harness.build_env(
            config=config,
            ephemeral_home=ephemeral_home,
            api_key=api_key,
            base_env=base_env,
        )
        cmd = (
            f"stdbuf -oL python3 {wrapper_path} {spec_path} "
            f"2>> {job_dir}/.opencode-wrapper.log | tee {output_file} > /dev/null"
        )
        return cmd, env

    def _get_metadata_base_path(self) -> str:
        """Get metadata base path for this chat."""
        return f"/workspace/metadata-{self.chat_id}"

    def _get_safe_metadata_path(self, file_path: str) -> tuple:
        """
        Safely construct metadata path for a file, preventing path traversal (CWE-22).

        Returns:
            (is_valid, meta_dir, meta_path)
        """
        import os

        metadata_base = self._get_metadata_base_path()

        # SECURITY: Block path traversal attempts
        if ".." in file_path:
            logger.error(f"[SECURITY] Metadata path traversal blocked: {file_path}")
            return (False, "", "")

        # Get clean relative path
        relative_path = file_path.lstrip("/")

        # SECURITY: Use basename to prevent directory traversal in filename
        directory = os.path.dirname(relative_path)
        filename = os.path.basename(relative_path)

        # SECURITY: Validate directory doesn't contain traversal
        if directory and (".." in directory or directory.startswith("/")):
            logger.error(f"[SECURITY] Metadata directory traversal blocked: {directory}")
            return (False, "", "")

        # Build metadata path
        meta_dir = os.path.join(metadata_base, directory) if directory else metadata_base
        meta_filename = f"{filename}.meta.json"
        meta_path = os.path.join(meta_dir, meta_filename)

        # SECURITY: Verify the final path is within metadata_base
        normalized_meta_path = os.path.normpath(meta_path)
        normalized_metadata_base = os.path.normpath(metadata_base)
        if not normalized_meta_path.startswith(normalized_metadata_base):
            logger.error(f"[SECURITY] Metadata path escape blocked: {meta_path}")
            return (False, "", "")

        return (True, meta_dir, meta_path)

    async def _write_file_metadata(
        self,
        container,
        file_path: str,
        model_metadata: Dict[str, Any],
        is_creation: bool
    ):
        """
        Write metadata sidecar file for a file created/modified by Coding Agent.

        Args:
            container: Docker container to execute commands in
            file_path: Relative path to the file
            model_metadata: Model info (model_name, model_id, provider, icons)
            is_creation: True if file is newly created, False if modified
        """
        try:
            is_valid, meta_dir, meta_path = self._get_safe_metadata_path(file_path)
            if not is_valid:
                logger.warning(f"[CodingAgent] Skipping metadata for invalid path: {file_path}")
                return

            timestamp = time.time()

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
                else:
                    # No existing metadata - treat as creation
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

            # Ensure metadata directory exists
            container.exec_run(["mkdir", "-p", meta_dir])

            # Write metadata file using heredoc
            meta_json = json.dumps(metadata_content)
            cmd = f"cat > {meta_path} << 'METAEOF'\n{meta_json}\nMETAEOF"
            result = container.exec_run(
                ["sh", "-c", cmd],
                user="sandboxuser"
            )

            if result.exit_code != 0:
                logger.warning(f"[CodingAgent] Failed to write metadata for {file_path}: {result.output.decode()}")
            else:
                logger.debug(f"[CodingAgent] Wrote metadata for {file_path}")

        except Exception as e:
            logger.warning(f"[CodingAgent] Error writing metadata for {file_path}: {e}")

    def __init__(
        self,
        sandbox_executor,
        user_id: str,
        chat_id: str
    ):
        """
        Initialize the runner.

        Args:
            sandbox_executor: SandboxExecutor instance for container access
            user_id: User ID for sandbox isolation
            chat_id: Chat ID for workspace scoping
        """
        self.sandbox_executor = sandbox_executor
        self.user_id = user_id
        self.chat_id = chat_id
        self._workspace_client = None

    def _get_workspace_client(self):
        """Lazy load workspace client."""
        if self._workspace_client is None:
            self._workspace_client = get_workspace_client()
        return self._workspace_client

    async def _capture_workspace_state(
        self,
        container,
        workspace_path: str
    ) -> Dict[str, FileSnapshot]:
        """
        Capture current state of all files in workspace.

        Returns dict mapping file paths to their snapshots.
        """
        snapshots: Dict[str, FileSnapshot] = {}

        try:
            # List all files in workspace
            result = container.exec_run(
                ["find", workspace_path, "-type", "f",
                 "-not", "-path", "*/__pycache__/*",
                 "-not", "-path", "*/node_modules/*",
                 "-not", "-path", "*/.git/*",
                 "-not", "-name", "*.pyc",
                 "-not", "-name", ".coding-agent-*"],
                workdir=workspace_path
            )

            if result.exit_code != 0:
                logger.warning(f"[CodingAgent] Failed to list workspace files: {result.output.decode()}")
                return snapshots

            file_paths = result.output.decode().strip().split('\n')
            file_paths = [p for p in file_paths if p and p != workspace_path]

            for file_path in file_paths:
                try:
                    # Get file size first
                    stat_result = container.exec_run(["stat", "-c", "%s", file_path])
                    if stat_result.exit_code != 0:
                        continue

                    file_size = int(stat_result.output.decode().strip())

                    # Skip large files
                    if file_size > self.MAX_VERSION_FILE_SIZE:
                        continue

                    # Read file content
                    cat_result = container.exec_run(["cat", file_path])
                    if cat_result.exit_code != 0:
                        continue

                    content = cat_result.output
                    sha256 = hashlib.sha256(content).hexdigest()

                    # Get relative path
                    relative_path = file_path.replace(workspace_path + "/", "", 1)

                    snapshots[relative_path] = FileSnapshot(
                        path=relative_path,
                        content=content,
                        sha256=sha256,
                        size=file_size,
                    )

                except Exception as e:
                    logger.debug(f"[CodingAgent] Error capturing {file_path}: {e}")

            logger.info(f"[CodingAgent] Captured {len(snapshots)} files from workspace")

        except Exception as e:
            logger.warning(f"[CodingAgent] Failed to capture workspace state: {e}")

        return snapshots

    async def _create_versions_for_changes(
        self,
        container,
        before_state: Dict[str, FileSnapshot],
        after_state: Dict[str, FileSnapshot],
        job_id: str,
        model_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Compare before/after state and create versions for changed files.
        Also writes metadata sidecar files for file attribution.

        Returns number of versions created.
        """
        versions_created = 0
        workspace_client = self._get_workspace_client()

        try:
            all_paths = set(before_state.keys()) | set(after_state.keys())

            for path in all_paths:
                before = before_state.get(path)
                after = after_state.get(path)

                # Determine if file changed
                if before is None and after is not None:
                    # New file created
                    workspace_client.create_version(
                        user_id=self.user_id,
                        chat_id=self.chat_id,
                        path=path,
                        content=after.content,
                        source_type='coding_agent',
                        source_job_id=job_id,
                        source_tool_name='Write',
                    )
                    versions_created += 1
                    logger.debug(f"[CodingAgent] Created version for new file: {path}")

                    # Write metadata sidecar file for new file
                    if model_metadata:
                        await self._write_file_metadata(
                            container, path, model_metadata, is_creation=True
                        )

                elif before is not None and after is None:
                    # File deleted
                    workspace_client.create_version(
                        user_id=self.user_id,
                        chat_id=self.chat_id,
                        path=path,
                        content=b'',
                        source_type='coding_agent',
                        source_job_id=job_id,
                        is_deleted=True,
                    )
                    versions_created += 1
                    logger.debug(f"[CodingAgent] Created deletion version for: {path}")

                elif before is not None and after is not None:
                    # Check if content changed
                    if before.sha256 != after.sha256:
                        # For modified files, create a "before" version first
                        # This ensures the diff viewer has both states
                        workspace_client.create_version(
                            user_id=self.user_id,
                            chat_id=self.chat_id,
                            path=path,
                            content=before.content,
                            source_type='coding_agent',
                            source_job_id=job_id,
                            source_tool_name='Read',  # Captured state before modification
                        )
                        # Then create the "after" version
                        workspace_client.create_version(
                            user_id=self.user_id,
                            chat_id=self.chat_id,
                            path=path,
                            content=after.content,
                            source_type='coding_agent',
                            source_job_id=job_id,
                            source_tool_name='Edit',
                        )
                        versions_created += 2
                        logger.debug(f"[CodingAgent] Created before/after versions for modified file: {path}")

                        # Write metadata sidecar file for modified file
                        if model_metadata:
                            await self._write_file_metadata(
                                container, path, model_metadata, is_creation=False
                            )

            logger.info(f"[CodingAgent] Created {versions_created} versions for job {job_id}")

        except Exception as e:
            logger.error(f"[CodingAgent] Failed to create versions: {e}")

        return versions_created

    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        return f"cc_{uuid.uuid4().hex[:12]}"

    def _validate_tools(self, tools: List[str]) -> List[str]:
        """Validate and filter allowed tools."""
        return [t for t in tools if t in self.VALID_TOOLS]

    def _sanitize_task(self, task: str, max_length: int = 10000) -> str:
        """Sanitize task string for safety."""
        # Truncate if too long
        if len(task) > max_length:
            task = task[:max_length] + "..."

        # Remove potentially dangerous characters
        # (shell injection protection - task goes through JSON, but be safe)
        task = task.replace('\x00', '')

        return task

    async def execute(
        self,
        task: str,
        model: str,
        api_key: str,
        allowed_tools: Optional[List[str]] = None,
        max_iterations: int = 20,
        conversation_id: Optional[str] = None,
        model_metadata: Optional[Dict[str, Any]] = None,
        mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None,
        mode: str = "auto",
        plan_id: Optional[str] = None,
        sub_agents: Optional[List[Dict[str, Any]]] = None,
        user_model_preferences: Optional[Dict[str, str]] = None,
        harness: Optional[str] = None,
        budget_usd: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute Coding Agent agent.

        Args:
            task: Task description for the agent
            model: OpenRouter model ID
            api_key: OpenRouter API key
            allowed_tools: Tools the agent can use
            max_iterations: Maximum iterations
            conversation_id: Optional conversation ID
            model_metadata: Model metadata for file attribution (model_name, model_id, provider, icons)
            mcp_servers: MCP server configurations to pass to Coding Agent CLI
            mode: Agent mode - "plan" (create plan), "implement" (execute plan), or "auto" (default)
            plan_id: Plan ID to implement (required when mode="implement")
            sub_agents: Sub-agent definitions as {name, markdown} dicts
            budget_usd: Remaining quota ceiling for this job. `None` enforces
                no ceiling; otherwise the job is stopped once its running
                cost crosses it (see `budget_guard.over_budget`).

        Returns:
            Dict with execution results
        """
        job_id = self._generate_job_id()
        start_time = time.time()
        harness = resolve_harness(harness)

        logger.info(f"[CodingAgent] Starting job {job_id}: task={task[:100]}...")

        # Validate inputs
        task = self._sanitize_task(task)
        allowed_tools = self._validate_tools(allowed_tools or list(self.VALID_TOOLS))
        max_iterations = min(max(1, max_iterations), 100)

        try:
            # Get or create sandbox
            sandbox_id = self.sandbox_executor._generate_sandbox_id(
                self.user_id, self.chat_id, self.chat_id, True
            )
            container = self.sandbox_executor._get_or_create_sandbox(sandbox_id)

            # Setup paths
            workspace_path = f"/workspace/chat-{self.chat_id}"
            job_dir = f"/tmp/agents/coding-agent-{job_id}"

            # Generate per-job auth token for MCP ask_user relay
            job_token = secrets.token_urlsafe(32)
            store_key = f"{self.user_id}:{self.chat_id}"
            _progress_store[store_key] = {
                **_progress_store.get(store_key, {}),
                "_job_token": job_token,
            }

            # Create job directory and symlink to workspace
            setup_result = await self._setup_job_directory(
                container, job_dir, workspace_path
            )
            if not setup_result["success"]:
                return {
                    "success": False,
                    "job_id": job_id,
                    "error": setup_result.get("error", "Failed to setup job directory"),
                    "duration_ms": int((time.time() - start_time) * 1000),
                }

            # Load plan content if in implement mode
            plan_content = None
            if mode == IMPLEMENT_MODE and plan_id:
                plan_content = await self._load_plan_content(plan_id, conversation_id)

            # Create config file
            config = CodingAgentConfig(
                task=task,
                model=model,
                api_key=api_key,  # Will be passed via env var, not config
                allowed_tools=allowed_tools,
                max_iterations=max_iterations,
                workspace_path=workspace_path,
                job_dir=job_dir,
                mcp_servers=mcp_servers,
                mode=mode,
                plan_id=plan_id,
                plan_content=plan_content,
                sub_agents=sub_agents,
                user_model_preferences=user_model_preferences,
                harness=harness,
            )

            config_result = await self._create_config_file(container, job_dir, config)
            if not config_result["success"]:
                return {
                    "success": False,
                    "job_id": job_id,
                    "error": config_result.get("error", "Failed to create config"),
                    "duration_ms": int((time.time() - start_time) * 1000),
                }

            # Capture workspace state BEFORE execution for version tracking
            before_state = await self._capture_workspace_state(container, workspace_path)

            # Execute the runner script
            result = await self._run_agent(
                container, job_dir, api_key, model, job_token=job_token, budget_usd=budget_usd,
            )

            # Capture workspace state AFTER execution
            after_state = await self._capture_workspace_state(container, workspace_path)

            # Create versions for any files that changed and write metadata sidecar files
            versions_created = await self._create_versions_for_changes(
                container, before_state, after_state, job_id, model_metadata
            )

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Plan mode: when the agent wrote a plan, the wrapper already
            # resolved it (see opencode_run_wrapper.newest_plan) into the
            # run's summary; `_run_agent` falls the summary back to
            # "Task completed" when there is none, so this is always set
            # on a successful run but is only ever a real plan when one
            # was written.
            if mode == PLAN_MODE and result.get("success"):
                result["plan_content"] = result.get("summary")

            # Parse result
            if result["success"]:
                return {
                    "success": True,
                    "job_id": job_id,
                    "summary": result.get("summary"),
                    "files_modified": result.get("files_modified", []),
                    "files_created": result.get("files_created", []),
                    "steps": result.get("steps", []),
                    "duration_ms": duration_ms,
                    "versions_created": versions_created,
                    "total_cost_usd": result.get("total_cost_usd", 0.0),
                    "total_tokens": result.get("total_tokens", 0),
                    "plan_content": result.get("plan_content"),
                }
            else:
                return {
                    "success": False,
                    "job_id": job_id,
                    "error": result.get("error", "Execution failed"),
                    "steps": result.get("steps", []),
                    "duration_ms": duration_ms,
                    "versions_created": versions_created,
                    "total_cost_usd": result.get("total_cost_usd", 0.0),
                    "total_tokens": result.get("total_tokens", 0),
                    "quota_exceeded": result.get("quota_exceeded", False),
                }

        except asyncio.TimeoutError:
            logger.error(f"[CodingAgent] Job {job_id} timed out")
            # Extract partial cost from progress store before cleanup
            partial_cost = 0.0
            store_key = f"{self.user_id}:{self.chat_id}"
            progress = _progress_store.get(store_key, {})
            if progress:
                partial_cost = progress.get("total_cost_usd", 0.0)
            return {
                "success": False,
                "job_id": job_id,
                "error": f"Execution timed out after {self.EXECUTION_TIMEOUT}s",
                "duration_ms": int((time.time() - start_time) * 1000),
                "total_cost_usd": partial_cost,
            }
        except Exception as e:
            logger.error(f"[CodingAgent] Job {job_id} failed: {e}", exc_info=True)
            partial_cost = 0.0
            store_key = f"{self.user_id}:{self.chat_id}"
            progress = _progress_store.get(store_key, {})
            if progress:
                partial_cost = progress.get("total_cost_usd", 0.0)
            return {
                "success": False,
                "job_id": job_id,
                "error": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
                "total_cost_usd": partial_cost,
            }
        finally:
            # Clean up in-memory progress store
            _progress_store.pop(f"{self.user_id}:{self.chat_id}", None)

    async def _setup_job_directory(
        self,
        container,
        job_dir: str,
        workspace_path: str
    ) -> Dict[str, Any]:
        """Create job directory with workspace symlink."""
        try:
            # Create parent agents directory with proper permissions first
            # Then create job directory and symlink workspace
            commands = [
                "mkdir -p /tmp/agents && chmod 777 /tmp/agents",
                f"mkdir -p {job_dir}",
                f"ln -sf {workspace_path} {job_dir}/workspace",
            ]

            for cmd in commands:
                result = container.exec_run(
                    ["sh", "-c", cmd],
                    workdir="/",
                    user="sandboxuser"
                )
                if result.exit_code != 0:
                    error = result.output.decode() if result.output else "Unknown error"
                    logger.error(f"[CodingAgent] Setup failed: {cmd} -> {error}")
                    return {"success": False, "error": f"Setup failed: {error}"}

            # Verify directory was created
            verify_result = container.exec_run(
                ["test", "-d", job_dir],
                user="sandboxuser"
            )
            if verify_result.exit_code != 0:
                logger.error(f"[CodingAgent] Directory verification failed: {job_dir} does not exist")
                return {"success": False, "error": f"Directory {job_dir} was not created"}

            logger.info(f"[CodingAgent] Job directory created and verified: {job_dir}")
            return {"success": True}

        except Exception as e:
            logger.error(f"[CodingAgent] Setup error: {e}")
            return {"success": False, "error": str(e)}

    async def _create_config_file(
        self,
        container,
        job_dir: str,
        config: CodingAgentConfig
    ) -> Dict[str, Any]:
        """Create config JSON file for the runner script."""
        try:
            # Build config (excluding api_key - that goes via env var)
            config_data = {
                "task": config.task,
                "model": config.model,
                "allowed_tools": config.allowed_tools,
                "max_iterations": config.max_iterations,
                "workspace_path": config.workspace_path,
                "job_dir": config.job_dir,
                "mcp_servers": config.mcp_servers,  # User's MCP servers (may be None)
                "mode": config.mode,  # "plan", "implement", or "auto"
                "plan_content": config.plan_content,  # Plan content for implement mode
                "sub_agents": config.sub_agents,  # Sub-agent definitions (may be None)
                "user_model_preferences": config.user_model_preferences,  # Tier→model mapping
                "harness": config.harness,  # CLI harness that runs the job
            }

            # Write config file
            config_json = json.dumps(config_data, indent=2)

            # Use heredoc to write config
            cmd = f"cat > {job_dir}/config.json << 'CONFIGEOF'\n{config_json}\nCONFIGEOF"

            result = container.exec_run(
                ["sh", "-c", cmd],
                workdir=job_dir,
                user="sandboxuser"
            )

            if result.exit_code != 0:
                error = result.output.decode() if result.output else "Unknown error"
                return {"success": False, "error": f"Config write failed: {error}"}

            logger.debug(f"[CodingAgent] Config written to {job_dir}/config.json")
            return {"success": True}

        except Exception as e:
            logger.error(f"[CodingAgent] Config error: {e}")
            return {"success": False, "error": str(e)}

    async def _load_plan_content(
        self,
        plan_id: str,
        conversation_id: Optional[str]
    ) -> Optional[str]:
        """Load plan content from Django API (orchestrator has no DB access)."""
        if not plan_id:
            return None

        try:
            import httpx

            auth_token = getattr(self, '_auth_token', None)
            if not auth_token:
                logger.warning("[CodingAgent] No auth token for plan loading")
                return None

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://sterna-web:8000/api/code-sessions/plans/{plan_id}/",
                    headers={"Authorization": f"Bearer {auth_token}"},
                    timeout=10.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("plan_content")
                else:
                    logger.warning(f"[CodingAgent] Failed to load plan: {response.status_code}")
                    return None

        except Exception as e:
            logger.warning(f"[CodingAgent] Failed to load plan {plan_id}: {e}")
            return None

    async def _write_mode_claude_md(
        self,
        container,
        workspace_path: str,
        mode: str,
    ) -> Optional[str]:
        """Write a mode-specific CLAUDE.md to the workspace root.

        `opencode_harness.build_env` sets `OPENCODE_DISABLE_PROJECT_CONFIG`,
        which moves opencode's instruction discovery off the workspace, so
        opencode does not read this file. See the call site for what
        actually enforces plan mode.

        Returns the original CLAUDE.md content (if any) for restoration, or None.
        """
        # Save existing CLAUDE.md if present
        original_content = None
        check = container.exec_run(["cat", f"{workspace_path}/CLAUDE.md"], user="sandboxuser")
        if check.exit_code == 0 and check.output:
            original_content = check.output.decode("utf-8", errors="replace")

        if mode == PLAN_MODE:
            claude_md = """# PLANNING MODE — READ ONLY

**You are in PLANNING mode. The workspace is READ-ONLY.**

## Absolute Rules
- Do NOT use `write`, `edit` or `patch` on a file in the workspace — they will fail with permission errors.
- Do NOT use `bash` to create, modify, or delete files (no `cat >`, `sed -i`, `touch`, `mkdir`, `echo >`, `tee`, etc.).
- Do NOT create, modify, or delete ANY files anywhere in the workspace.

## What You CAN Do
- **Read** files with `read`, and find them with `glob` and `grep`.
- **Run read-only `bash`** commands: `find`, `git log`, `git diff`, `tree`, `wc`, `ls`, `cat`, `head`, `tail`, `grep`.
- **Save your plan** with `write`, to the path the task names.

## Your Goal
Explore the codebase thoroughly, then produce a detailed implementation plan.
Writing that plan to the path the task names is the ONLY way to deliver your output.
"""
        elif mode == IMPLEMENT_MODE:
            claude_md = """# IMPLEMENTATION MODE

You are executing a pre-approved implementation plan. Follow the plan steps in order.
After each significant change, create a git commit describing what was done.
Do NOT create branches, push to remote, or create pull requests — this is handled automatically.

## Package Installation
You can install packages: `pip install <package>` and `npm install` (in the project directory) both work.
Do NOT use `npm install -g` (global installs fail on the read-only filesystem).
"""
        else:
            # Auto mode — sandbox-specific guidance
            claude_md = """# Sandbox Environment Notes

## npm / Node.js
- `npm install` is SLOW in this environment (up to 3 minutes) due to network proxy. Always wait for it to complete fully before running build commands.
- Use `npx <command>` instead of `npm run <command>` for build tools (next, tsc, etc.) to avoid PATH issues with `node_modules/.bin`.
- Do NOT use `npm install -g` (global installs fail on the read-only filesystem).
- Use `--prefix <dir>` or run from the project directory.

## Working Directory
- Always verify your cwd before running commands. Use absolute paths.
- If you are building a project in a subdirectory, ALL files must go in that subdirectory — never create project files in the workspace root.

## pip / Python
- `pip install <package>` works (redirected to workspace via PYTHONUSERBASE).
"""

        # If auto mode and nothing to write, skip
        if not claude_md.strip():
            return original_content

        # Prepend original content if it exists
        if original_content:
            claude_md = claude_md + "\n---\n\n" + original_content

        escaped = claude_md.replace("'", "'\"'\"'")
        write_result = container.exec_run(
            ["sh", "-c", f"printf '%s' '{escaped}' > {workspace_path}/CLAUDE.md"],
            user="sandboxuser",
        )
        if write_result.exit_code != 0:
            logger.warning(f"[CodingAgent] Failed to write mode CLAUDE.md: {write_result.output.decode() if write_result.output else ''}")
        else:
            logger.info(f"[CodingAgent] Wrote {mode}-mode CLAUDE.md to workspace ({len(claude_md)} chars)")

        return original_content

    async def _restore_claude_md(
        self,
        container,
        workspace_path: str,
        original_content: Optional[str],
    ):
        """Restore the original CLAUDE.md after execution."""
        if original_content is None:
            # No original file — remove the one we created
            container.exec_run(
                ["rm", "-f", f"{workspace_path}/CLAUDE.md"],
                user="sandboxuser",
            )
        else:
            escaped = original_content.replace("'", "'\"'\"'")
            container.exec_run(
                ["sh", "-c", f"printf '%s' '{escaped}' > {workspace_path}/CLAUDE.md"],
                user="sandboxuser",
            )
        logger.debug("[CodingAgent] Restored original CLAUDE.md")

    async def _run_agent(
        self,
        container,
        job_dir: str,
        api_key: str,
        model: str,
        job_token: str = "",
        budget_usd: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run the coding agent CLI, staged by `_prepare_opencode_run`.

        opencode is invoked non-interactively (`opencode run --format
        json`, staged with the rest of its command line in
        `opencode_harness.build_argv`) against OpenRouter as the backend,
        with its JSON event stream parsed by `OpencodeOutputAdapter`.
        """
        try:
            # Read config to get task and allowed tools
            config_result = container.exec_run(
                ["cat", f"{job_dir}/config.json"],
                workdir=job_dir,
                user="sandboxuser"
            )

            if config_result.exit_code != 0:
                return {"success": False, "error": "Failed to read config"}

            config = json.loads(config_result.output.decode())
            task = config["task"]
            allowed_tools = config.get("allowed_tools", list(self.VALID_TOOLS))
            max_iterations = config.get("max_iterations", 20)
            workspace_path = config["workspace_path"]
            mcp_servers = config.get("mcp_servers")  # User's MCP servers to pass to CLI
            mode = config.get("mode", "auto")
            plan_content = config.get("plan_content")
            sub_agents = config.get("sub_agents")  # Sub-agent defs as {name, markdown} dicts
            harness = resolve_harness(config.get("harness"))

            # SECURITY: Scan for dangerous config files before execution
            is_safe, dangerous_files = await self._scan_for_dangerous_configs(
                container, workspace_path
            )
            if not is_safe:
                return {
                    "success": False,
                    "error": (
                        f"Security check failed: Found potentially malicious config files "
                        f"in workspace that could compromise agent execution: {dangerous_files}. "
                        f"Please remove these files and try again."
                    )
                }

            # SECURITY: an ephemeral HOME keeps a job from reading, or
            # leaving behind, any persistent configuration.
            job_id = job_dir.split("-")[-1] if "-" in job_dir else "unknown"
            ephemeral_home = await self._setup_ephemeral_home(container, job_id)

            # Create writable directories for pip/npm package installs on the workspace tmpfs.
            # The root filesystem is read-only, and /tmp is small, so packages go under /workspace.
            container.exec_run(
                ["sh", "-c", "mkdir -p /workspace/.pip-packages /workspace/.pip-cache /workspace/.npm-cache"],
                user="sandboxuser",
            )

            self._plant_sub_agents(container, ephemeral_home, sub_agents)

            if mcp_servers:
                logger.warning(
                    f"[CodingAgent] MCP config requested with {len(mcp_servers)} servers "
                    f"({list(mcp_servers.keys())}), but only the ask-user relay is wired into "
                    "the harness; user-supplied MCP servers are not passed through."
                )

            # Environment every harness invocation shares: TLS trust for the
            # egress proxy, the ephemeral HOME, and pip/npm redirected onto
            # the workspace tmpfs (the root filesystem is read-only and
            # /tmp is small). `_prepare_opencode_run` layers opencode's own
            # settings on top of this.
            base_env = {
                "NODE_EXTRA_CA_CERTS": "/etc/ssl/proxy-ca/mitmproxy-ca-cert.pem",
                # SECURITY: Use ephemeral home to prevent config persistence attacks
                "HOME": ephemeral_home,
                # SECURITY: Disable command history to prevent credential leakage
                "HISTFILE": "/dev/null",
                # Proxy settings for egress through mitmproxy
                # These may already be set in container, but exec_run with environment
                # replaces rather than merges, so we need to include them explicitly
                "HTTP_PROXY": "http://egress-proxy:8888",
                "HTTPS_PROXY": "http://egress-proxy:8888",
                "http_proxy": "http://egress-proxy:8888",
                "https_proxy": "http://egress-proxy:8888",
                # The ask-user relay calls back into the orchestrator, so it
                # must reach it — and itself — past the egress proxy.
                "NO_PROXY": RELAY_NO_PROXY_HOSTS,
                "no_proxy": RELAY_NO_PROXY_HOSTS,
                # Package install support (pip/npm work inside sandbox)
                # Root filesystem is read-only; /tmp is small (200MB ephemeral home).
                # Redirect pip user-installs and npm cache to /workspace where there's room.
                "PIP_USER": "1",  # pip install uses user scheme (PYTHONUSERBASE)
                "PYTHONUSERBASE": "/workspace/.pip-packages",  # pip writes here instead of ~/.local/
                "PIP_NO_WARN_SCRIPT_LOCATION": "1",
                "PIP_CACHE_DIR": "/workspace/.pip-cache",  # download cache on workspace tmpfs
                "PIP_NO_INPUT": "1",  # Suppress verbose output (internal paths, versions)
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",  # Hide upgrade notices
                "PATH": "/workspace/.pip-packages/bin:{ephemeral_home}/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin".format(ephemeral_home=ephemeral_home),
                "NPM_CONFIG_IGNORE_SCRIPTS": "true",  # Block postinstall scripts (supply chain safety)
                "NPM_CONFIG_CACHE": "/workspace/.npm-cache",  # npm cache on workspace tmpfs
                "NPM_CONFIG_LOGLEVEL": "error",  # Suppress verbose npm output
                "NPM_CONFIG_UPDATE_NOTIFIER": "false",  # Hide "new npm version available" notices
                "NEXT_TELEMETRY_DISABLED": "1",  # Prevent next build from spawning background telemetry (causes hangs)
            }

            full_task = coding_agent_prompts.build_task_prompt(
                mode=mode,
                task=task,
                plan_content=plan_content,
                workspace_path=workspace_path,
                plan_path=opencode_harness.plan_path_for(ephemeral_home),
            )

            # Write control files to job_dir (not workspace) so they are
            # invisible to the end user and don't pollute the project tree.
            task_file = f"{job_dir}/.coding-agent-task.txt"
            output_file = f"{job_dir}/.coding-agent-output.jsonl"
            progress_file = f"{job_dir}/.coding-agent-progress.json"

            cmd, env = await self._prepare_opencode_run(
                container, job_dir, ephemeral_home, workspace_path, mode,
                model, api_key, max_iterations, allowed_tools,
                task_file, output_file, full_task, base_env, job_token,
            )

            logger.info(f"[CodingAgent] Executing {harness} in {workspace_path}")
            logger.debug(f"[CodingAgent] Command: {cmd[:200]}...")
            # Presence only — never log key material (even a prefix).
            logger.info(f"[CodingAgent] API key provided: {bool(api_key)}")

            # Write mode-specific CLAUDE.md before any filesystem restrictions.
            # opencode does not read it — see `_write_mode_claude_md`.
            original_claude_md = await self._write_mode_claude_md(
                container, workspace_path, mode
            )

            # PLAN MODE: Make workspace read-only at filesystem level.
            # This is the reliable enforcement layer beneath opencode's own
            # plan-agent permission profile (`opencode_harness.build_permission_profile`),
            # which denies `edit` but cannot stop `bash` from writing a file
            # a permission rule does not separately deny.
            if mode == PLAN_MODE:
                logger.info(f"[CodingAgent] Plan mode: making workspace read-only: {workspace_path}")
                chmod_result = container.exec_run(
                    ["sh", "-c", f"chmod -R a-w {workspace_path}"],
                    user="root"
                )
                if chmod_result.exit_code != 0:
                    logger.warning(f"[CodingAgent] Failed to make workspace read-only: {chmod_result.output.decode() if chmod_result.output else 'unknown'}")

            try:
                # Execute with file-based progress tracking
                result = await asyncio.wait_for(
                    self._execute_with_file_streaming(
                        container=container,
                        cmd=cmd,
                        workspace_path=workspace_path,
                        env=env,
                        output_file=output_file,
                        progress_file=progress_file,
                        harness=harness,
                        budget_usd=budget_usd,
                    ),
                    timeout=self.EXECUTION_TIMEOUT
                )
            finally:
                # PLAN MODE: Always restore workspace write permissions after execution
                if mode == PLAN_MODE:
                    logger.info("[CodingAgent] Plan mode: restoring workspace write permissions")
                    container.exec_run(
                        ["sh", "-c", f"chmod -R u+w {workspace_path}"],
                        user="root"
                    )
                # Restore original CLAUDE.md (or remove ours)
                await self._restore_claude_md(container, workspace_path, original_claude_md)

            stdout = result.get("output", "")
            exit_code = result.get("exit_code", 1)

            logger.info(f"[CodingAgent] CLI exit code: {exit_code}")
            logger.info(f"[CodingAgent] CLI output length: {len(stdout)} chars")
            # Log first 500 chars of output for debugging
            if stdout:
                logger.info(f"[CodingAgent] CLI output (first 500 chars): {stdout[:500]}")

            # Parse the harness's own stream format
            parsed = parse_run_output(harness, stdout, workspace_path)
            logger.info(f"[CodingAgent] Parsed {len(parsed.steps)} steps from output")

            quota_exceeded = result.get("quota_exceeded", False)
            if quota_exceeded:
                logger.warning(f"[CodingAgent] Job {job_id} stopped: quota exceeded mid-run")
                parsed.success = False
                parsed.error = "Coding agent stopped: usage quota exceeded mid-run"
            # Override: if process was killed but parser didn't detect error
            elif exit_code != 0 and parsed.success:
                logger.warning(f"[CodingAgent] Parser reported success but exit_code={exit_code} — overriding to failure")
                parsed.success = False
                parsed.error = parsed.error or f"Agent process exited with code {exit_code} (likely killed by signal)"

            # Convert steps to serializable format
            steps = []
            for step in parsed.steps:
                steps.append({
                    "type": step.type,
                    "tool": step.tool,
                    "content": step.content,
                    "input": step.input,
                    "output": step.output,
                })

            if parsed.success:
                return {
                    "success": True,
                    "summary": parsed.summary or "Task completed",
                    "files_modified": parsed.files_modified,
                    "files_created": parsed.files_created,
                    "steps": steps,
                    "total_tokens": parsed.total_tokens,
                    "total_cost_usd": parsed.total_cost_usd,
                }
            else:
                failure: Dict[str, Any] = {
                    "success": False,
                    "error": parsed.error or f"CLI exited with code {exit_code}",
                    "summary": parsed.summary,
                    "steps": steps,
                    "files_modified": parsed.files_modified,
                    "files_created": parsed.files_created,
                    "total_cost_usd": parsed.total_cost_usd,
                }
                if quota_exceeded:
                    failure["quota_exceeded"] = True
                return failure

        except asyncio.TimeoutError:
            # Update progress file to indicate timeout before re-raising
            logger.error(f"[CodingAgent] Execution timed out after {self.EXECUTION_TIMEOUT}s")
            try:
                # Extract partial cost/tokens from progress store if available
                store_key = f"{self.user_id}:{self.chat_id}"
                partial_progress = _progress_store.get(store_key, {})
                partial_cost = partial_progress.get("total_cost_usd", 0.0)
                partial_tokens = partial_progress.get("total_tokens", 0)

                # Write timeout status to progress file so UI can show proper state
                timeout_progress = json.dumps({
                    "step_count": partial_progress.get("step_count", 0),
                    "total_steps": partial_progress.get("total_steps", 0),
                    "completed": True,
                    "exit_code": 124,  # Standard timeout exit code
                    "files_created": partial_progress.get("files_created", []),
                    "files_modified": partial_progress.get("files_modified", []),
                    "files_read": partial_progress.get("files_read", []),
                    "files_deleted": [],
                    "steps": partial_progress.get("steps", []),
                    "error": f"Execution timed out after {self.EXECUTION_TIMEOUT}s",
                    "summary": None,
                    "total_cost_usd": partial_cost,
                    "total_tokens": partial_tokens,
                })
                cmd = f"cat > {progress_file} << 'PROGRESSEOF'\n{timeout_progress}\nPROGRESSEOF"
                container.exec_run(["sh", "-c", cmd], user="sandboxuser")
            except Exception as progress_err:
                logger.warning(f"[CodingAgent] Failed to update progress file on timeout: {progress_err}")
            raise
        except Exception as e:
            logger.error(f"[CodingAgent] Run error: {e}", exc_info=True)
            # Extract partial cost from progress store
            partial_cost = 0.0
            store_key = f"{self.user_id}:{self.chat_id}"
            progress = _progress_store.get(store_key, {})
            if progress:
                partial_cost = progress.get("total_cost_usd", 0.0)
            return {"success": False, "error": str(e), "total_cost_usd": partial_cost}

    def _write_progress_file(
        self,
        container,
        progress_file: str,
        parser: AgentOutputAdapter,
        step_count: int,
        completed: bool = False,
        exit_code: Optional[int] = None,
    ):
        """Write current progress to in-memory store and optionally to file."""
        try:
            # Build progress data - include ALL steps with full content
            steps_data = []
            for step in parser.steps:
                step_data = {
                    "type": step.type,
                    "tool": step.tool,
                    "content": step.content,  # Full content, not truncated
                }
                # Include tool input if available
                if step.input:
                    step_data["input"] = step.input
                # Include tool output if available
                if step.output:
                    step_data["output"] = step.output
                steps_data.append(step_data)

            progress = {
                "step_count": step_count,
                "total_steps": len(parser.steps),
                "completed": completed,
                "exit_code": exit_code,
                "files_created": list(parser.files_created),
                "files_modified": list(parser.files_modified),
                "files_read": list(parser.files_read),
                "files_deleted": list(parser.files_deleted),
                "steps": steps_data,  # All steps with full content
                "error": parser.error,
                "summary": parser.summary,  # Full summary
                "total_cost_usd": parser.total_cost_usd,
                "total_tokens": parser.total_tokens,
            }

            # Always update in-memory store (primary source for progress endpoint)
            store_key = f"{self.user_id}:{self.chat_id}"
            _progress_store[store_key] = progress

            # Also try file-based write (best-effort, may fail on tmpfs mounts)
            try:
                progress_json = json.dumps(progress)
                progress_dir = "/".join(progress_file.split("/")[:-1])
                progress_filename = progress_file.split("/")[-1]

                tar_buffer = io.BytesIO()
                with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
                    data = progress_json.encode('utf-8')
                    tarinfo = tarfile.TarInfo(name=progress_filename)
                    tarinfo.size = len(data)
                    tarinfo.uid = 1000
                    tarinfo.gid = 1000
                    tarinfo.mode = 0o644
                    tar.addfile(tarinfo, io.BytesIO(data))
                tar_buffer.seek(0)
                container.put_archive(progress_dir, tar_buffer.getvalue())
            except Exception:
                pass  # File write is best-effort; in-memory store is the primary source

        except Exception as e:
            logger.warning(f"[CodingAgent] Failed to update progress: {e}")

    async def _execute_with_file_streaming(
        self,
        container,
        cmd: str,
        workspace_path: str,
        env: Dict[str, str],
        output_file: str,
        progress_file: str,
        harness: str = "",
        budget_usd: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute the coding-agent CLI with file-based progress tracking.

        Instead of relying on Docker's streaming API (which has buffering issues with piped commands),
        this method:
        1. Runs the command in the background with shell backgrounding
        2. Polls the output file periodically to read new output
        3. Parses the output and updates progress file for the frontend

        Args:
            container: Docker container to run in
            cmd: Command to execute (should use tee to write to output_file)
            workspace_path: Working directory
            env: Environment variables
            output_file: Path where command output is being written via tee
            progress_file: Path to write progress JSON for monitoring
            budget_usd: Quota ceiling; the process is signalled to stop once
                crossed (see `budget_guard.over_budget`).

        Returns:
            Dict with output, exit_code and quota_exceeded
        """
        def _run_with_file_polling():
            """Run command in background and poll output file for progress updates."""
            import time as time_module
            parser = create_adapter(harness, workspace_path)
            step_count = 0
            last_file_position = 0
            quota_exceeded = False
            # Derive control file directory from output_file location
            # In plan mode, output_file is in job_dir (not workspace), so pid/exit-code follow
            _control_dir = "/".join(output_file.rsplit("/", 1)[:-1]) if "/" in output_file else workspace_path
            pid_file = f"{_control_dir}/.coding-agent-pid"
            exit_code_file = f"{_control_dir}/.coding-agent-exit-code"

            try:
                # Write initial progress file to indicate agent is starting
                logger.info(f"[CodingAgent] Writing initial progress file: {progress_file}")
                self._write_progress_file(container, progress_file, parser, 0)

                # Clear output file and pid file
                container.exec_run(
                    ["sh", "-c", f"rm -f {output_file} {pid_file} {exit_code_file}; touch {output_file}"],
                    user="sandboxuser"
                )

                # Docker's environment parameter doesn't always export vars to
                # subshells. Values are quoted, not interpolated: they carry API
                # keys and whole JSON documents that the shell must not reread.
                env_exports = " && ".join([
                    f"export {k}={shlex.quote(str(v))}" for k, v in env.items()
                ])

                # Build background command that writes its PID and exit code
                # The command runs in background, writes PID, and writes exit code on completion
                bg_cmd = f'''
                    {env_exports} && (
                        {cmd}
                        echo $? > {exit_code_file}
                    ) &
                    echo $! > {pid_file}
                '''

                logger.info("[CodingAgent] Starting background command...")
                logger.debug(f"[CodingAgent] Environment exports: {list(env.keys())}")

                # Start the background process
                start_result = container.exec_run(
                    ["sh", "-c", bg_cmd],
                    workdir=workspace_path,
                    user="sandboxuser",
                )

                if start_result.exit_code != 0:
                    logger.error(f"[CodingAgent] Failed to start background process: {start_result.output.decode() if start_result.output else 'no output'}")
                    return {"output": "", "exit_code": 1}

                # Read the PID
                time_module.sleep(0.1)
                pid_result = container.exec_run(["cat", pid_file], user="sandboxuser")
                pid = pid_result.output.decode().strip() if pid_result.exit_code == 0 and pid_result.output else None
                logger.info(f"[CodingAgent] Background process started with PID: {pid}")

                # Poll for completion and process output
                poll_interval = 0.5  # seconds
                max_polls = int(self.EXECUTION_TIMEOUT / poll_interval) + 10
                poll_count = 0
                line_buffer = ""

                while poll_count < max_polls:
                    poll_count += 1

                    # Check if process completed by looking for exit code file
                    # Fallback: also check if the PID is a zombie (process exited but
                    # exit code file was never written, e.g. killed by signal)
                    check_result = container.exec_run(
                        ["sh", "-c", f"test -f {exit_code_file} && echo 'DONE' || echo 'RUNNING'"],
                        user="sandboxuser"
                    )
                    is_running = check_result.output.decode().strip() == "RUNNING" if check_result.output else True

                    # Fallback: if exit code file missing, check if PID is zombie or gone
                    if is_running and poll_count > 10:
                        pid_check = container.exec_run(
                            ["sh", "-c", f"cat {pid_file} 2>/dev/null"],
                            user="sandboxuser"
                        )
                        agent_pid = pid_check.output.decode().strip() if pid_check.output else ""
                        if agent_pid:
                            state_check = container.exec_run(
                                ["sh", "-c", f"cat /proc/{agent_pid}/status 2>/dev/null | grep -m1 '^State:' || echo 'State:\tGONE'"],
                                user="sandboxuser"
                            )
                            state = state_check.output.decode().strip() if state_check.output else ""
                            if "zombie" in state.lower() or "GONE" in state:
                                logger.warning(f"[CodingAgent] Process {agent_pid} is {state} — exit code file missing (likely killed by signal)")
                                is_running = False

                    # Read new content from output file
                    read_cmd = f"tail -c +{last_file_position + 1} {output_file} 2>/dev/null || true"
                    read_result = container.exec_run(
                        ["sh", "-c", read_cmd],
                        user="sandboxuser"
                    )

                    if read_result.exit_code == 0 and read_result.output:
                        new_content = read_result.output.decode('utf-8', errors='replace')
                        if new_content:
                            last_file_position += len(read_result.output)

                            # Parse complete lines
                            line_buffer += new_content
                            while '\n' in line_buffer:
                                line, line_buffer = line_buffer.split('\n', 1)
                                if line.strip() and parser.ingest(line):
                                    step_count += 1

                                    # Update progress file
                                    self._write_progress_file(
                                        container,
                                        progress_file,
                                        parser,
                                        step_count
                                    )

                    # Quota ceiling crossed: signal the process to stop. The
                    # zombie/exit-code handling below then runs unchanged —
                    # a killed process is already indistinguishable from a
                    # timed-out one at this layer.
                    if not quota_exceeded and over_budget(parser, budget_usd):
                        quota_exceeded = True
                        logger.warning(f"[CodingAgent] Budget ${budget_usd} crossed at ${parser.running_cost_usd} — stopping job")
                        if pid:
                            container.exec_run(terminate_command(pid), user="sandboxuser")

                    # Log progress periodically (more frequently at start for debugging)
                    if poll_count <= 5 or poll_count % 20 == 0:
                        logger.info(f"[CodingAgent] Poll {poll_count}: {step_count} steps, {last_file_position} bytes, running={is_running}")

                    # Check if process completed
                    if not is_running:
                        # Give it a moment to finish writing
                        time_module.sleep(0.3)

                        # Read any final content
                        final_read_cmd = f"tail -c +{last_file_position + 1} {output_file} 2>/dev/null || true"
                        final_result = container.exec_run(["sh", "-c", final_read_cmd], user="sandboxuser")
                        if final_result.exit_code == 0 and final_result.output:
                            final_content = final_result.output.decode('utf-8', errors='replace')
                            line_buffer += final_content
                            while '\n' in line_buffer:
                                line, line_buffer = line_buffer.split('\n', 1)
                                if line.strip() and parser.ingest(line):
                                    step_count += 1

                        # Check the final file size for debugging
                        size_result = container.exec_run(["sh", "-c", f"wc -c < {output_file}"], user="sandboxuser")
                        final_size = size_result.output.decode().strip() if size_result.output else "unknown"
                        logger.info(f"[CodingAgent] Process completed after {poll_count} polls, final output size: {final_size} bytes, steps: {step_count}")
                        break

                    # Wait before next poll
                    time_module.sleep(poll_interval)

                # Process any remaining buffered line
                if line_buffer.strip() and parser.ingest(line_buffer):
                    step_count += 1

                # Read complete output file for return value
                full_output_result = container.exec_run(
                    ["cat", output_file],
                    user="sandboxuser"
                )
                full_output = full_output_result.output.decode('utf-8', errors='replace') if full_output_result.output else ""

                # Read exit code from file
                exit_code_result = container.exec_run(["cat", exit_code_file], user="sandboxuser")
                exit_code = 0
                if exit_code_result.exit_code == 0 and exit_code_result.output:
                    try:
                        exit_code = int(exit_code_result.output.decode().strip())
                    except ValueError:
                        exit_code = 1
                else:
                    # Exit code file missing — process was likely killed by signal
                    logger.warning("[CodingAgent] Exit code file missing — defaulting to exit_code=137 (killed)")
                    exit_code = 137

                # Write final progress
                self._write_progress_file(
                    container,
                    progress_file,
                    parser,
                    step_count,
                    completed=True,
                    exit_code=exit_code
                )

                logger.info(f"[CodingAgent] Execution complete: {step_count} steps, exit code {exit_code}")

                return {
                    "output": full_output,
                    "exit_code": exit_code,
                    "quota_exceeded": quota_exceeded,
                }

            except Exception as e:
                logger.error(f"[CodingAgent] File streaming execution error: {e}", exc_info=True)
                # Try to read whatever output we have
                try:
                    output_result = container.exec_run(["cat", output_file], user="sandboxuser")
                    output = output_result.output.decode('utf-8', errors='replace') if output_result.output else ""
                except Exception:
                    output = ""
                return {
                    "output": output,
                    "exit_code": 1,
                    "quota_exceeded": quota_exceeded,
                }

        # Run in thread to not block the event loop
        return await asyncio.to_thread(_run_with_file_polling)
