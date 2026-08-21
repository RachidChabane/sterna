"""
Coding Agent Service

Manages Coding Agent job lifecycle including creation, tracking, and cancellation.
Coordinates execution via the sandbox orchestrator service.

This service provides a clean interface for the HTTP tool executor and LangChain
tools to invoke Coding Agent without needing to know orchestrator details.
"""

import uuid
import logging
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from django.conf import settings
from asgiref.sync import sync_to_async

from mcp.claude_config import serialize_mcp_servers_for_claude

logger = logging.getLogger(__name__)


class CodingAgentJobStatus(str, Enum):
    """Status of a Coding Agent execution job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CodingAgentStep:
    """A single step in Coding Agent execution."""
    step_index: int
    type: str  # 'thinking', 'tool_call', 'tool_result', 'text'
    tool: Optional[str] = None
    content: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class CodingAgentResult:
    """Result of a Coding Agent execution."""
    success: bool
    summary: Optional[str] = None
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    error: Optional[str] = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0  # Cost from OpenRouter API calls


@dataclass
class CodingAgentJob:
    """Represents a Coding Agent execution job."""
    job_id: str
    user_id: str
    chat_id: str
    task: str
    model: str
    allowed_tools: List[str]
    max_iterations: int
    status: CodingAgentJobStatus = CodingAgentJobStatus.PENDING
    steps: List[CodingAgentStep] = field(default_factory=list)
    result: Optional[CodingAgentResult] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "task": self.task,
            "model": self.model,
            "status": self.status.value,
            "steps": [
                {
                    "step_index": s.step_index,
                    "type": s.type,
                    "tool": s.tool,
                    "content": s.content[:200] if s.content else None,  # Truncate for safety
                    "timestamp": s.timestamp,
                }
                for s in self.steps
            ],
            "result": {
                "success": self.result.success,
                "summary": self.result.summary,
                "files_modified": self.result.files_modified,
                "files_created": self.result.files_created,
                "error": self.result.error,
            } if self.result else None,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }


class CodingAgentService:
    """
    Service for managing Coding Agent executions.

    Coordinates with the orchestrator to run Coding Agent
    inside user sandboxes with proper isolation.

    Usage:
        service = get_coding_agent_service()
        result = await service.execute(
            user_id="123",
            chat_id="456",
            task="Fix the bug in auth.py",
            model="anthropic/claude-sonnet-4",
            api_key="sk-or-...",
        )
    """

    # Default allowed tools for Coding Agent execution
    DEFAULT_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    # Default max iterations
    DEFAULT_MAX_ITERATIONS = 20

    # Maximum allowed iterations
    MAX_ITERATIONS_LIMIT = 100

    # Execution timeout in seconds
    EXECUTION_TIMEOUT = 600  # 10 minutes

    def __init__(self):
        self.active_jobs: Dict[str, CodingAgentJob] = {}
        self._orchestrator_url = getattr(
            settings, 'ORCHESTRATOR_URL',
            'http://orchestrator:8003'
        )

    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        return f"cc_{uuid.uuid4().hex[:12]}"

    def _validate_allowed_tools(self, tools: List[str]) -> List[str]:
        """Validate and sanitize allowed tools list."""
        valid_tools = {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}
        return [t for t in tools if t in valid_tools]

    def _validate_max_iterations(self, max_iterations: int) -> int:
        """Validate max iterations within limits."""
        return min(max(1, max_iterations), self.MAX_ITERATIONS_LIMIT)

    def create_job(
        self,
        user_id: str,
        chat_id: str,
        task: str,
        model: str,
        allowed_tools: Optional[List[str]] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> CodingAgentJob:
        """
        Create a new Coding Agent job.

        Args:
            user_id: User ID for sandbox isolation
            chat_id: Chat ID for workspace scoping
            task: Task description for Coding Agent
            model: OpenRouter model ID
            allowed_tools: List of tools Coding Agent can use
            max_iterations: Maximum agent iterations

        Returns:
            Created CodingAgentJob instance
        """
        job_id = self._generate_job_id()

        # Validate inputs
        validated_tools = self._validate_allowed_tools(
            allowed_tools or self.DEFAULT_ALLOWED_TOOLS
        )
        validated_iterations = self._validate_max_iterations(max_iterations)

        job = CodingAgentJob(
            job_id=job_id,
            user_id=user_id,
            chat_id=chat_id,
            task=task,
            model=model,
            allowed_tools=validated_tools,
            max_iterations=validated_iterations,
        )

        self.active_jobs[job_id] = job
        logger.info(f"[CodingAgent] Created job {job_id} for user {user_id}, task: {task[:50]}...")

        return job

    def get_job(self, job_id: str) -> Optional[CodingAgentJob]:
        """Get a job by ID."""
        return self.active_jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancelled, False if job not found or not running
        """
        job = self.active_jobs.get(job_id)
        if job and job.status == CodingAgentJobStatus.RUNNING:
            job.status = CodingAgentJobStatus.CANCELLED
            job.completed_at = datetime.utcnow().isoformat()
            logger.info(f"[CodingAgent] Cancelled job {job_id}")
            return True
        return False

    def _cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove jobs older than max_age_hours."""
        cutoff = datetime.utcnow().timestamp() - (max_age_hours * 3600)
        to_remove = []

        for job_id, job in self.active_jobs.items():
            try:
                job_time = datetime.fromisoformat(job.created_at).timestamp()
                if job_time < cutoff:
                    to_remove.append(job_id)
            except (ValueError, TypeError):
                pass

        for job_id in to_remove:
            del self.active_jobs[job_id]

        if to_remove:
            logger.debug(f"[CodingAgent] Cleaned up {len(to_remove)} old jobs")

    async def _fetch_user_mcp_servers(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Fetch user's active MCP servers and serialize them for Coding Agent.

        Args:
            user_id: User ID to fetch servers for

        Returns:
            Dict of serialized MCP server configs for --mcp-config flag
        """
        try:
            from mcp.models import MCPServer

            # Wrap synchronous Django ORM calls with sync_to_async
            @sync_to_async
            def get_mcp_servers():
                servers = MCPServer.objects.filter(
                    user_id=user_id,
                    is_active=True,
                ).select_related()
                return list(servers)

            server_list = await get_mcp_servers()

            if not server_list:
                logger.debug(f"[CodingAgent] No active MCP servers for user {user_id}")
                return {}

            # Log server details for debugging
            for server in server_list:
                logger.info(
                    f"[CodingAgent] Found MCP server: name='{server.name}', "
                    f"transport={server.transport_type}, auth={server.auth_type}, "
                    f"remote_url={server.remote_url}, has_token={bool(server.oauth_access_token)}"
                )

            # Serialize for Claude CLI
            serialized = serialize_mcp_servers_for_claude(server_list)

            logger.info(
                f"[CodingAgent] Serialized {len(serialized)}/{len(server_list)} MCP servers for user {user_id}: "
                f"{list(serialized.keys())}"
            )

            return serialized

        except Exception as e:
            logger.error(
                f"[CodingAgent] Failed to fetch MCP servers for user {user_id}: {e}",
                exc_info=True
            )
            # Don't fail the execution, just proceed without MCP servers
            return {}

    async def execute(
        self,
        user_id: str,
        chat_id: str,
        task: str,
        model: str,
        api_key: str,
        auth_token: str,
        allowed_tools: Optional[List[str]] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        conversation_id: Optional[str] = None,
        model_metadata: Optional[Dict[str, Any]] = None,
        mode: str = "auto",
        plan_id: Optional[str] = None,
        sub_agents: Optional[List[Dict[str, Any]]] = None,
        user_model_preferences: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a Coding Agent task.

        This is the main entry point for running Coding Agent.
        Creates a job, sends it to the orchestrator, and returns results.

        Args:
            user_id: User ID for sandbox isolation
            chat_id: Chat ID for workspace scoping
            task: Task description
            model: OpenRouter model ID
            api_key: OpenRouter API key
            auth_token: JWT auth token for orchestrator authentication
            allowed_tools: Tools Coding Agent can use
            max_iterations: Maximum iterations
            conversation_id: Optional conversation ID for context
            model_metadata: Model metadata for file attribution (model_name, model_id, provider, icons)
            mode: Agent mode - "plan" (create plan), "implement" (execute plan), or "auto" (default)
            plan_id: Plan ID to implement (required when mode="implement")

        Returns:
            Dict with execution results
        """
        # Periodic cleanup
        self._cleanup_old_jobs()

        # Create job
        job = self.create_job(
            user_id=user_id,
            chat_id=chat_id,
            task=task,
            model=model,
            allowed_tools=allowed_tools,
            max_iterations=max_iterations,
        )

        # Mark as running
        job.status = CodingAgentJobStatus.RUNNING
        job.started_at = datetime.utcnow().isoformat()

        # Fetch user's MCP servers to pass to Coding Agent
        mcp_servers = await self._fetch_user_mcp_servers(user_id)

        try:
            # Send to orchestrator
            result = await self._execute_via_orchestrator(
                job=job,
                api_key=api_key,
                auth_token=auth_token,
                conversation_id=conversation_id,
                model_metadata=model_metadata,
                mcp_servers=mcp_servers,
                mode=mode,
                plan_id=plan_id,
                sub_agents=sub_agents,
                user_model_preferences=user_model_preferences,
            )

            # Update job with results
            # Use orchestrator's job_id (the one used for file versioning)
            orchestrator_job_id = result.get("job_id")
            if orchestrator_job_id:
                job.job_id = orchestrator_job_id
            job.status = CodingAgentJobStatus.COMPLETED
            job.completed_at = datetime.utcnow().isoformat()

            if job.started_at:
                start = datetime.fromisoformat(job.started_at)
                end = datetime.fromisoformat(job.completed_at)
                job.duration_ms = int((end - start).total_seconds() * 1000)

            job.result = CodingAgentResult(
                success=result.get("success", False),
                summary=result.get("summary"),
                files_modified=result.get("files_modified", []),
                files_created=result.get("files_created", []),
                error=result.get("error"),
                total_tokens=result.get("total_tokens", 0),
                total_cost_usd=result.get("total_cost_usd", 0.0),
            )

            # Parse steps if provided
            for i, step_data in enumerate(result.get("steps", [])):
                job.steps.append(CodingAgentStep(
                    step_index=i,
                    type=step_data.get("type", "text"),
                    tool=step_data.get("tool"),
                    content=step_data.get("content"),
                ))

            logger.info(
                f"[CodingAgent] Job {job.job_id} completed: "
                f"success={job.result.success}, duration={job.duration_ms}ms"
            )

            ret = {
                "success": True,
                "job_id": job.job_id,
                "status": job.status.value,
                "steps": [
                    {"type": s.type, "tool": s.tool, "content": s.content}
                    for s in job.steps
                ],
                "result": {
                    "success": job.result.success,
                    "summary": job.result.summary,
                    "files_modified": job.result.files_modified,
                    "files_created": job.result.files_created,
                    "total_tokens": job.result.total_tokens,
                    "total_cost_usd": job.result.total_cost_usd,
                },
                "duration_ms": job.duration_ms,
            }
            # Pass through plan_content from orchestrator (plan mode)
            if result.get("plan_content"):
                ret["plan_content"] = result["plan_content"]
            return ret

        except asyncio.TimeoutError:
            job.status = CodingAgentJobStatus.FAILED
            job.completed_at = datetime.utcnow().isoformat()
            job.result = CodingAgentResult(
                success=False,
                error="Execution timed out"
            )
            logger.error(f"[CodingAgent] Job {job.job_id} timed out")
            # Propagate any partial cost from orchestrator (available if runner
            # extracted it from progress store before the timeout propagated)
            partial_cost = 0.0
            try:
                if 'result' in dir() and isinstance(result, dict):
                    partial_cost = result.get("total_cost_usd", 0.0)
            except Exception:
                pass
            return {
                "success": False,
                "job_id": job.job_id,
                "status": job.status.value,
                "error": "Execution timed out after 10 minutes",
                "result": {"total_cost_usd": partial_cost},
            }

        except Exception as e:
            job.status = CodingAgentJobStatus.FAILED
            job.completed_at = datetime.utcnow().isoformat()
            job.result = CodingAgentResult(
                success=False,
                error=str(e)
            )
            logger.error(f"[CodingAgent] Job {job.job_id} failed: {e}", exc_info=True)
            partial_cost = 0.0
            try:
                if 'result' in dir() and isinstance(result, dict):
                    partial_cost = result.get("total_cost_usd", 0.0)
            except Exception:
                pass
            return {
                "success": False,
                "job_id": job.job_id,
                "status": job.status.value,
                "error": str(e),
                "result": {"total_cost_usd": partial_cost},
            }

    async def _execute_via_orchestrator(
        self,
        job: CodingAgentJob,
        api_key: str,
        auth_token: str,
        conversation_id: Optional[str] = None,
        model_metadata: Optional[Dict[str, Any]] = None,
        mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None,
        mode: str = "auto",
        plan_id: Optional[str] = None,
        sub_agents: Optional[List[Dict[str, Any]]] = None,
        user_model_preferences: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Send execution request to orchestrator service.

        Args:
            job: The job to execute
            api_key: OpenRouter API key
            auth_token: JWT auth token for orchestrator authentication
            conversation_id: Optional conversation ID
            model_metadata: Model metadata for file attribution
            mcp_servers: Serialized MCP server configs for Coding Agent CLI
            mode: Agent mode - "plan", "implement", or "auto"
            plan_id: Plan ID for implement mode
            sub_agents: Sub-agent definitions as {name, markdown} dicts

        Returns:
            Dict with execution results from orchestrator
        """
        payload = {
            "user_id": job.user_id,
            "conversation_id": conversation_id or job.chat_id,
            "chat_id": job.chat_id,
            "task": job.task,
            "model": job.model,
            "allowed_tools": job.allowed_tools,
            "max_iterations": job.max_iterations,
            "openrouter_api_key": api_key,
            "model_metadata": model_metadata,
            "mcp_servers": mcp_servers,  # Pass MCP servers to orchestrator
            "mode": mode,
            "plan_id": plan_id,
            "sub_agents": sub_agents,
            "user_model_preferences": user_model_preferences,
        }

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.EXECUTION_TIMEOUT) as client:
            response = await client.post(
                f"{self._orchestrator_url}/coding-agent/execute",
                json=payload,
                headers=headers,
            )

            if response.status_code != 200:
                error_detail = response.text[:500]
                raise RuntimeError(
                    f"Orchestrator returned {response.status_code}: {error_detail}"
                )

            return response.json()

    async def send_answer(
        self,
        user_id: str,
        chat_id: str,
        answer: str,
        auth_token: str,
    ) -> Dict[str, Any]:
        """
        Send an answer to a pending coding agent question.

        Args:
            user_id: User ID
            chat_id: Chat ID
            answer: The user's answer text
            auth_token: JWT auth token for orchestrator authentication

        Returns:
            Dict with success status
        """
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self._orchestrator_url}/coding-agent/answer",
                    json={"user_id": user_id, "chat_id": chat_id, "answer": answer},
                    headers=headers,
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.warning(f"[CodingAgent] Failed to send answer: {e}")
            return {"success": False, "error": str(e)}

    async def get_progress(
        self,
        user_id: str,
        chat_id: str,
        job_id: Optional[str],
        auth_token: str,
    ) -> Dict[str, Any]:
        """
        Get real-time progress of a running Coding Agent job.

        Args:
            user_id: User ID for sandbox isolation
            chat_id: Chat ID for workspace scoping
            job_id: Optional job ID (will find most recent job if not provided)
            auth_token: JWT auth token for orchestrator authentication

        Returns:
            Dict with progress data
        """
        payload = {
            "user_id": user_id,
            "chat_id": chat_id,
        }
        if job_id:
            payload["job_id"] = job_id

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self._orchestrator_url}/coding-agent/progress",
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {"found": False}
        except Exception as e:
            logger.warning(f"[CodingAgent] Failed to get progress: {e}")
            return {"found": False}


# Singleton instance
_service: Optional[CodingAgentService] = None


def get_coding_agent_service() -> CodingAgentService:
    """Get the Coding Agent service singleton."""
    global _service
    if _service is None:
        _service = CodingAgentService()
    return _service


# Convenience functions

async def execute_coding_agent(
    user_id: str,
    chat_id: str,
    task: str,
    model: str,
    api_key: str,
    auth_token: str,
    allowed_tools: Optional[List[str]] = None,
    max_iterations: int = 20,
    conversation_id: Optional[str] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
    mode: str = "auto",
    plan_id: Optional[str] = None,
    sub_agents: Optional[List[Dict[str, Any]]] = None,
    user_model_preferences: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to execute Coding Agent.

    Args:
        user_id: User ID for sandbox isolation
        chat_id: Chat ID for workspace scoping
        task: Task description
        model: OpenRouter model ID
        api_key: OpenRouter API key
        auth_token: JWT auth token for orchestrator authentication
        allowed_tools: Tools Coding Agent can use
        max_iterations: Maximum iterations
        conversation_id: Optional conversation ID
        model_metadata: Model metadata for file attribution
        mode: Agent mode - "plan", "implement", or "auto"
        plan_id: Plan ID for implement mode
        sub_agents: Sub-agent definitions as {name, markdown} dicts
        user_model_preferences: User's tier→model mapping for sandbox ENV vars

    Returns:
        Dict with execution results
    """
    service = get_coding_agent_service()
    return await service.execute(
        user_id=user_id,
        chat_id=chat_id,
        task=task,
        model=model,
        api_key=api_key,
        auth_token=auth_token,
        allowed_tools=allowed_tools,
        max_iterations=max_iterations,
        conversation_id=conversation_id,
        model_metadata=model_metadata,
        mode=mode,
        plan_id=plan_id,
        sub_agents=sub_agents,
        user_model_preferences=user_model_preferences,
    )


async def get_coding_agent_progress(
    user_id: str,
    chat_id: str,
    job_id: Optional[str],
    auth_token: str,
) -> Dict[str, Any]:
    """
    Get real-time progress of a running Coding Agent job.

    Args:
        user_id: User ID for sandbox isolation
        chat_id: Chat ID for workspace scoping
        job_id: Optional job ID (will find most recent job if not provided)
        auth_token: JWT auth token for orchestrator authentication

    Returns:
        Dict with progress data
    """
    service = get_coding_agent_service()
    return await service.get_progress(
        user_id=user_id,
        chat_id=chat_id,
        job_id=job_id,
        auth_token=auth_token,
    )
