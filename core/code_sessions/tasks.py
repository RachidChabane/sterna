"""Celery tasks for code job execution.

This module contains background tasks for executing coding jobs
in isolated sandboxes with real-time progress updates via WebSocket.

Includes token optimization features:
- Conversation summarization (older jobs → summaries)
- Tool result compression
- Smart context truncation
- explore_codebase tool (scout agent called by main model when needed)
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from asgiref.sync import async_to_sync
from celery import shared_task  # type: ignore[import-untyped]
from channels.layers import get_channel_layer  # type: ignore[import-untyped]
from django.utils import timezone

from code_sessions.models import GitHubConnection

# Import optimization modules
from code_sessions.optimization.constants import (
    ENABLE_TOKEN_OPTIMIZATION,
    ENABLE_CONVERSATION_SUMMARIZATION,
    ENABLE_TOOL_COMPRESSION,
    MAX_FULL_HISTORY_JOBS,
)
from code_sessions.optimization.history_pruner import prune_conversation_history

# History pruning - enabled by default when token optimization is on
ENABLE_HISTORY_PRUNING = ENABLE_TOKEN_OPTIMIZATION

logger = logging.getLogger(__name__)


def _convert_decimals(obj):
    """Convert Decimal values to float for JSON serialization."""
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj


def send_job_update(
    job_id: str,
    status: str,
    progress: int,
    message: str,
    **kwargs,
) -> None:
    """Send real-time job update via WebSocket.

    Args:
        job_id: UUID of the job
        status: Job status (pending, running, completed, failed, etc.)
        progress: Progress percentage (0-100)
        message: Human-readable progress message
        **kwargs: Additional data to send (result, files_modified, etc.)
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("No channel layer configured, skipping WebSocket update")
        return

    # Convert kwargs to handle Decimal types
    serializable_kwargs = _convert_decimals(kwargs)

    try:
        async_to_sync(channel_layer.group_send)(
            f"job_{job_id}",
            {
                "type": "job_status_update",
                "job_id": str(job_id),
                "status": status,
                "progress": progress,
                "message": message,
                "timestamp": timezone.now().isoformat(),
                **serializable_kwargs,
            },
        )
    except Exception as e:
        logger.error(f"Failed to send WebSocket update for job {job_id}: {e}")


def send_step_event(
    job_id: str,
    step_type: str,
    **kwargs,
) -> None:
    """Send a step event via WebSocket (text, reasoning, tool_execution).

    Args:
        job_id: UUID of the job
        step_type: Type of step (text, reasoning, tool_executing, tool_executed)
        **kwargs: Step-specific data
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    serializable_kwargs = _convert_decimals(kwargs)

    try:
        async_to_sync(channel_layer.group_send)(
            f"job_{job_id}",
            {
                "type": "job_step_event",
                "job_id": str(job_id),
                "step_type": step_type,
                "timestamp": timezone.now().isoformat(),
                **serializable_kwargs,
            },
        )
    except Exception as e:
        logger.error(f"Failed to send step event for job {job_id}: {e}")


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def execute_code_job(self, job_id: str) -> dict:
    """Execute a coding job in the sandbox.

    This task:
    1. Initializes the sandbox environment
    2. Clones the repository if needed
    3. Runs the AI agent loop with file tools
    4. Reports progress via WebSocket
    5. Stores results in the database

    Args:
        job_id: UUID of the CodeJob to execute

    Returns:
        dict: Execution result with status and output
    """
    from .models import CodeJob, JobLog

    # Load the job
    try:
        job = CodeJob.objects.select_related("session__user").get(id=job_id)
    except CodeJob.DoesNotExist:
        logger.error(f"Job {job_id} not found")
        return {"error": "Job not found"}

    # Update job with Celery task ID
    job.celery_task_id = self.request.id
    job.status = CodeJob.Status.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["celery_task_id", "status", "started_at"])

    # Create initial log
    JobLog.objects.create(
        job=job,
        level=JobLog.Level.INFO,
        message=f"Job started with task ID {self.request.id}",
    )

    send_job_update(job_id, "running", 5, "Initializing sandbox...")

    try:

        # Progress callback for the agent
        def on_progress(progress_pct: float, message: str):
            """Update progress during execution."""
            # Map agent progress (0-1) to our range (35-95)
            mapped_progress = 35 + int(progress_pct * 60)
            job.update_progress(mapped_progress, message)
            send_job_update(job_id, "running", mapped_progress, message)

        send_job_update(job_id, "running", 10, "Sandbox ready")

        # Clone repository if needed
        if job.session.github_repo_full_name and not job.session.repo_cloned:
            send_job_update(job_id, "cloning", 15, "Cloning repository...")
            job.status = CodeJob.Status.CLONING
            job.save(update_fields=["status"])

            clone_result = clone_repository_for_job(job)
            if not clone_result.get("success"):
                raise Exception(f"Failed to clone repository: {clone_result.get('error')}")

            job.session.repo_cloned = True
            job.session.save(update_fields=["repo_cloned"])
            send_job_update(job_id, "running", 30, "Repository cloned")

            JobLog.objects.create(
                job=job,
                level=JobLog.Level.INFO,
                message=f"Repository cloned: {job.session.github_repo_full_name}",
            )

        # Execute with LLM agent loop
        send_job_update(job_id, "running", 35, "Starting AI agent...")
        job.status = CodeJob.Status.RUNNING
        job.save(update_fields=["status"])

        result = run_agent_loop(
            job=job,
            on_progress=on_progress,
        )

        # Extract modified files from result
        files_modified = result.get("files_modified", [])
        job.files_modified = files_modified

        # Extract token usage
        job.total_tokens = result.get("total_tokens", 0)
        job.prompt_tokens = result.get("prompt_tokens", 0)
        job.completion_tokens = result.get("completion_tokens", 0)
        job.total_cost = result.get("total_cost", 0)

        # Mark completed
        job.mark_completed(result)

        JobLog.objects.create(
            job=job,
            level=JobLog.Level.INFO,
            message=f"Job completed successfully. Modified {len(files_modified)} files.",
            metadata={"files_modified": files_modified},
        )

        send_job_update(
            job_id,
            "completed",
            100,
            "Job completed successfully",
            result=result,
            files_modified=files_modified,
            steps=result.get("steps", []),
        )

        logger.info(f"Job {job_id} completed successfully")
        return {"success": True, "result": result}

    except Exception as e:
        logger.exception(f"Job {job_id} failed")

        error_message = str(e)
        job.mark_failed(error_message)

        JobLog.objects.create(
            job=job,
            level=JobLog.Level.ERROR,
            message=f"Job failed: {error_message}",
        )

        send_job_update(job_id, "failed", job.progress, error_message)

        # Re-raise for Celery retry mechanism
        raise


def clone_repository_for_job(job) -> dict:
    """Clone the repository for a job.

    Args:
        job: CodeJob instance with session containing repo info

    Returns:
        dict: Clone result with success status
    """
    from .models import GitHubConnection
    from .services.github import GitHubService

    try:
        # Get GitHub connection for user
        connection = GitHubConnection.objects.get(user=job.session.user)

        # Get authenticated clone URL
        github = GitHubService(connection.access_token)
        owner, repo = job.session.github_repo_full_name.split("/")
        clone_url = github.get_authenticated_remote_url(owner, repo)

        # Determine branch to clone - use session branch or fetch from GitHub API
        branch_to_clone = job.session.github_branch
        logger.info(f"[Clone] Attempting to clone {owner}/{repo} branch: {branch_to_clone}")

        # Execute clone in sandbox
        import httpx
        from authentication.jwt_utils import JWTManager

        # Generate JWT token for orchestrator auth
        auth_token = JWTManager.create_access_token(job.session.user)

        from sterna.middleware.request_id import request_id_headers

        response = httpx.post(
            "http://sterna-orchestrator:8003/execute",
            headers=request_id_headers({"Authorization": f"Bearer {auth_token}"}),
            json={
                "user_id": str(job.session.user.id),
                "conversation_id": str(job.session.id),
                "chat_id": str(job.session.id),
                "language": "python",
                "timeout": 300,
                "code": f'''
import subprocess
import os
import shutil

# Use chat-specific workspace (matches file tools workspace)
chat_workspace = "/workspace/chat-{job.session.id}"
repo_path = f"{{chat_workspace}}/repo"

# Create chat workspace if it doesn't exist
os.makedirs(chat_workspace, exist_ok=True)
print(f"Using workspace: {{chat_workspace}}")

# Remove existing repo directory if exists
if os.path.exists(repo_path):
    shutil.rmtree(repo_path)
    print(f"Removed existing {{repo_path}} directory")

# Try to clone with specified branch first
branch = "{branch_to_clone}"
clone_url = "{clone_url}"

print(f"Attempting to clone branch: {{branch}}")

# First try with specified branch
result = subprocess.run(
    ["git", "clone", "--branch", branch,
     "--single-branch", "--depth", "50", clone_url, repo_path],
    capture_output=True,
    text=True,
    timeout=300
)

# If branch not found, try without --branch to use remote's default
if result.returncode != 0 and "not found" in result.stderr.lower():
    print(f"Branch '{{branch}}' not found, trying with default branch...")
    # Clean up failed clone attempt
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)

    # Clone without specifying branch (uses remote's HEAD)
    result = subprocess.run(
        ["git", "clone", "--depth", "50", clone_url, repo_path],
        capture_output=True,
        text=True,
        timeout=300
    )

    if result.returncode == 0:
        # Get the actual branch we cloned
        branch_result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True
        )
        actual_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        print(f"Successfully cloned default branch: {{actual_branch}}")

if result.returncode != 0:
    print(f"Clone failed: {{result.stderr}}")
    raise Exception(result.stderr)

print("Repository cloned successfully")

# List files
for root, dirs, files in os.walk(repo_path):
    # Skip .git directory
    dirs[:] = [d for d in dirs if d != ".git"]
    for file in files[:10]:  # Limit output
        print(os.path.join(root, file))
''',
            },
            timeout=600,
        )

        if response.status_code != 200:
            logger.error(f"[Clone] Orchestrator returned {response.status_code}: {response.text}")
            return {"success": False, "error": response.text}

        result = response.json()
        # ExecuteCodeResponse has: output, error, exit_code, execution_time, artifacts
        exit_code = result.get("exit_code", 1)
        error = result.get("error", "")
        output = result.get("output", "")

        if exit_code == 0 and not error:
            logger.info(f"[Clone] Successfully cloned {owner}/{repo}")
        else:
            logger.error(f"[Clone] Failed: exit_code={exit_code}, error={error}, output={output}")

        return {
            "success": exit_code == 0 and not error,
            "output": output,
            "error": error if error else (output if exit_code != 0 else ""),
        }

    except GitHubConnection.DoesNotExist:
        logger.error("[Clone] GitHub account not connected")
        return {"success": False, "error": "GitHub account not connected"}
    except Exception as e:
        logger.exception(f"[Clone] Exception during clone: {e}")
        return {"success": False, "error": str(e)}


def run_agent_loop(
    job,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> dict:
    """Run the AI agent loop for a coding task.

    This function orchestrates the LLM with file tools to complete
    the coding task specified in the job prompt.

    Supports token optimization modes:
    - Two-phase Scout/Editor: Cheap model explores, expensive model edits
    - Single-phase optimized: Summarization + compression without scout
    - Legacy mode: Original behavior (no optimizations)

    Args:
        job: CodeJob instance
        on_progress: Optional callback for progress updates (0-1, message)

    Returns:
        dict: Execution result with files_modified, tokens, steps, etc.
    """
    import json
    import uuid

    from authentication.jwt_utils import JWTManager
    from llm.client import OpenRouterClient
    from llm.file_tools_integration import handle_file_tool_calls
    from sandbox.orchestrator.file_tools import get_all_tools

    job_id = str(job.id)

    if on_progress:
        on_progress(0.1, "Preparing AI agent...")

    # Check if user has GitHub connection for GitHub tools
    github_token = None
    has_github = False
    try:
        github_connection = GitHubConnection.objects.get(user=job.session.user)
        github_token = github_connection.access_token  # Auto-decrypted
        has_github = True
        logger.info(f"GitHub connection found for user {job.session.user.id}")
    except GitHubConnection.DoesNotExist:
        logger.info(f"No GitHub connection for user {job.session.user.id}")

    # Generate auth token for tool execution
    auth_token = JWTManager.create_access_token(job.session.user)

    # Single-phase execution with tools (including explore_codebase for codebase exploration)
    logger.info(f"[CodeJob {job.id}] === SINGLE-PHASE EXECUTION ===")
    logger.info(f"[CodeJob {job.id}] Optimizations: summarization={ENABLE_CONVERSATION_SUMMARIZATION}, "
               f"compression={ENABLE_TOOL_COMPRESSION}")

    # Build messages for the agent
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": _build_coding_system_prompt(job, has_github=has_github),
        },
    ]

    # Add conversation history from previous completed jobs in this session
    # This enables multi-turn conversations where the AI remembers prior tasks
    from .models import CodeJob
    previous_jobs = list(CodeJob.objects.filter(
        session=job.session,
        status__in=[CodeJob.Status.COMPLETED, CodeJob.Status.FAILED, CodeJob.Status.CANCELLED],
    ).exclude(id=job.id).order_by('created_at'))

    # Use conversation summarization if enabled and we have many previous jobs
    if ENABLE_TOKEN_OPTIMIZATION and ENABLE_CONVERSATION_SUMMARIZATION and len(previous_jobs) > MAX_FULL_HISTORY_JOBS:
        from code_sessions.optimization.summarizer import summarize_conversation_history

        logger.info(f"Summarizing {len(previous_jobs)} previous jobs (keeping last {MAX_FULL_HISTORY_JOBS} in full)")

        history = summarize_conversation_history(
            jobs=previous_jobs,
            max_full_jobs=MAX_FULL_HISTORY_JOBS,
            user=job.session.user,
        )

        # Add summary of older jobs
        if history.get("summary"):
            messages.append({
                "role": "system",
                "content": f"## Previous Work Summary\n{history['summary']}",
            })
            logger.info(f"Added summary for {history['metrics'].get('jobs_summarized', 0)} older jobs")

        # Add full context for recent jobs
        recent_jobs = history.get("recent_jobs", [])
        for prev_job in recent_jobs:
            messages.append({
                "role": "user",
                "content": prev_job.prompt,
            })
            # Add assistant response
            summary_parts = []
            if prev_job.steps:
                for step in prev_job.steps:
                    if step.get("type") == "text" and step.get("content"):
                        summary_parts.append(step["content"])
            if summary_parts:
                messages.append({
                    "role": "assistant",
                    "content": "\n\n".join(summary_parts[:2]),  # Limit to first 2 text blocks
                })
            elif prev_job.result and isinstance(prev_job.result, dict) and prev_job.result.get("content"):
                messages.append({
                    "role": "assistant",
                    "content": prev_job.result["content"][:2000],  # Truncate long responses
                })

        logger.info(f"Added {len(recent_jobs)} recent jobs in full context")

    else:
        # Original behavior: include all previous jobs in full
        for prev_job in previous_jobs:
            # Add the user's prompt from the previous job
            messages.append({
                "role": "user",
                "content": prev_job.prompt,
            })
            # Add a summary of what was done (from steps or final content)
            summary_parts = []
            if prev_job.steps:
                for step in prev_job.steps:
                    if step.get("type") == "text" and step.get("content"):
                        summary_parts.append(step["content"])
            if summary_parts:
                messages.append({
                    "role": "assistant",
                    "content": "\n\n".join(summary_parts),
                })
            elif prev_job.result and isinstance(prev_job.result, dict) and prev_job.result.get("content"):
                messages.append({
                    "role": "assistant",
                    "content": prev_job.result["content"],
                })
            else:
                # Fallback: indicate the job was processed
                status_msg = "Task completed." if prev_job.status == CodeJob.Status.COMPLETED else f"Task {prev_job.status}."
                if prev_job.files_modified:
                    status_msg += f" Modified files: {', '.join(prev_job.files_modified)}"
                messages.append({
                    "role": "assistant",
                    "content": status_msg,
                })

        logger.info(f"Added conversation history from {len(previous_jobs)} previous jobs (no summarization)")

    # Add current user prompt
    messages.append({
        "role": "user",
        "content": job.prompt,
    })

    # Add any existing messages from the job (for retries/continuations)
    for msg in job.messages:
        messages.append(msg)

    # Get tools definitions (including GitHub if connected)
    file_tools = get_all_tools(include_github=has_github)
    file_tool_names = {
        "list_files", "read_file", "search_code", "write_file", "create_directory",
        "delete_file", "rename_file", "edit_file", "run_bash", "update_todos",
        "prepare_pull_request", "execute_programming_task", "explore_codebase"
    }
    if has_github:
        # Add GitHub tool names
        github_tool_names = {
            "github_get_issue", "github_list_issues", "github_create_issue",
            "github_create_pull_request", "github_get_pull_request", "github_list_pull_requests",
            "github_get_file_contents", "github_push_files", "github_create_branch",
            "github_search_code", "github_search_issues"
        }
        file_tool_names.update(github_tool_names)

    if on_progress:
        on_progress(0.2, "Sending request to AI...")

    # Use the LLM client directly
    client = OpenRouterClient(user=job.session.user, request_source='code_session')

    # Track accumulated usage
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost = 0.0
    all_files_modified = []
    all_content = []
    all_steps = []  # Track steps for UI display

    # Loop detection - track file reads to prevent infinite loops
    file_read_counts: dict[str, int] = {}  # path -> read count
    MAX_READS_PER_FILE = 2  # After 2 reads, return error instead

    # Todo tracking - persist todos and inject into each iteration
    current_todos: list[dict] = []  # Current todo list state

    # Agent loop - continue until LLM gives final response
    max_iterations = 100  # Allow plenty of iterations for complex tasks
    iteration = 0

    try:
        while iteration < max_iterations:
            iteration += 1
            progress_base = 0.2 + (iteration * 0.06)  # Progress from 0.2 to 0.8

            if on_progress:
                on_progress(min(progress_base, 0.8), f"AI thinking... (step {iteration})")

            # Prune conversation history to reduce tokens (after first iteration)
            if ENABLE_HISTORY_PRUNING and iteration > 1 and len(messages) > 6:
                original_count = len(messages)
                messages = prune_conversation_history(messages, user=job.session.user)
                if len(messages) != original_count:
                    logger.info(f"[HistoryPruner] Pruned messages: {original_count} -> {len(messages)}")

            logger.info(f"Agent loop iteration {iteration}, messages count: {len(messages)}")
            logger.info(f"Sending {len(file_tools)} tools to LLM: {[t['function']['name'] for t in file_tools]}")

            # Inject current todos into messages for context (CRITICAL for steering)
            messages_with_todos = messages.copy()
            if current_todos:
                todo_status = _format_todos_for_context(current_todos)
                # Add as a system reminder before the LLM call
                messages_with_todos.append({
                    "role": "user",
                    "content": f"[CURRENT TODO STATUS - Follow this plan]\n{todo_status}"
                })
                logger.info(f"Injected {len(current_todos)} todos into context")

            # Call LLM with tools (use messages_with_todos to include current todo state)
            result = client.complete(
                model=job.session.model_id,
                messages=messages_with_todos,
                max_tokens=8000,
                tools=file_tools,
                tool_choice="auto",
            )

            # Accumulate usage
            usage = result.get("usage", {})
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_cost += float(result.get("cost", 0) or 0)

            # Check for tool calls
            tool_calls = result.get("tool_calls", [])
            finish_reason = result.get("finish_reason", "stop")
            content = result.get("content", "")

            logger.info(f"LLM response: finish_reason={finish_reason}, tool_calls={len(tool_calls)}, content_len={len(content)}")

            # Send text content as a step event
            if content:
                all_content.append(content)
                text_step = {
                    "type": "text",
                    "content": content,
                    "iteration": iteration,
                }
                all_steps.append(text_step)
                send_step_event(job_id, "text", content=content, iteration=iteration)
                # Save steps incrementally
                job.steps = all_steps
                job.save(update_fields=["steps"])

            # If no tool calls, we're done
            # Note: Check for tool_calls presence directly - some providers may not set finish_reason correctly
            if not tool_calls:
                logger.info(f"No tool calls in response (finish_reason={finish_reason}), agent loop complete")
                break

            # Fix tool call IDs if missing
            for tc in tool_calls:
                if not tc.get("id"):
                    tc["id"] = f"call_{uuid.uuid4().hex[:16]}"

            # Filter to file tools only
            file_tool_calls = [
                tc for tc in tool_calls
                if tc.get("function", {}).get("name") in file_tool_names
            ]

            if not file_tool_calls:
                logger.info("No file tool calls to execute")
                break

            if on_progress:
                tool_names = [tc.get("function", {}).get("name") for tc in file_tool_calls]
                on_progress(min(progress_base + 0.03, 0.85), f"Executing: {', '.join(tool_names)}")

            logger.info(f"Executing {len(file_tool_calls)} file tool calls")

            # Send tool_executing events for each tool
            tool_executions = []
            for tc in file_tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "unknown")
                try:
                    tool_args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                execution = {
                    "tool_call_id": tc.get("id"),
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "status": "executing",
                    "result": None,
                }
                tool_executions.append(execution)

                # Send executing event
                send_step_event(
                    job_id,
                    "tool_executing",
                    tool_call_id=tc.get("id"),
                    tool_name=tool_name,
                    arguments=tool_args,
                )

            # Execute file tools
            user_id = str(job.session.user.id)
            conversation_id = str(job.session.id)
            chat_id = str(job.session.id)

            # Loop detection: check for repeated read_file calls
            tool_calls_to_execute = []
            loop_blocked_results = []

            for tc in file_tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    tool_args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                # Track read_file calls
                if tool_name == "read_file":
                    path = tool_args.get("path", "")
                    file_read_counts[path] = file_read_counts.get(path, 0) + 1

                    if file_read_counts[path] > MAX_READS_PER_FILE:
                        # Block this read - return error to break loop
                        logger.warning(f"[LoopDetection] Blocking repeated read of {path} (count: {file_read_counts[path]})")
                        loop_blocked_results.append({
                            "tool_call": tc,
                            "result": {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "content": json.dumps({
                                    "success": False,
                                    "error": f"LOOP DETECTED: You have already read '{path}' {MAX_READS_PER_FILE} times. "
                                             f"The content is already in your context. "
                                             f"STOP re-reading and PROCEED with implementation. "
                                             f"Use the information you already have."
                                })
                            }
                        })
                        continue

                tool_calls_to_execute.append(tc)

            # Generate JWT token for internal service call to orchestrator
            from authentication.jwt_utils import JWTManager
            auth_token = JWTManager.create_access_token(job.session.user)

            # Execute only non-blocked tool calls
            if tool_calls_to_execute:
                executed_results = handle_file_tool_calls(
                    tool_calls=tool_calls_to_execute,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    chat_id=chat_id,
                    sync_mode=True,
                    auth_token=auth_token,
                    github_token=github_token,
                )
            else:
                executed_results = []

            # Merge results in original order
            tool_results = []
            executed_idx = 0
            blocked_idx = 0
            for tc in file_tool_calls:
                # Check if this was blocked
                if blocked_idx < len(loop_blocked_results) and loop_blocked_results[blocked_idx]["tool_call"] == tc:
                    tool_results.append(loop_blocked_results[blocked_idx]["result"])
                    blocked_idx += 1
                else:
                    tool_results.append(executed_results[executed_idx])
                    executed_idx += 1

            logger.info(f"Tool execution completed: {len(tool_results)} results")

            # Update tool executions with results and send executed events
            for i, (tc, tool_result) in enumerate(zip(file_tool_calls, tool_results)):
                func = tc.get("function", {})
                tool_name = func.get("name", "unknown")
                result_content = tool_result.get("content", "")

                # Truncate very long results for display
                display_result = result_content
                if len(display_result) > 2000:
                    display_result = display_result[:2000] + "\n... (truncated)"

                tool_executions[i]["status"] = "completed"
                tool_executions[i]["result"] = display_result

                # Send executed event
                send_step_event(
                    job_id,
                    "tool_executed",
                    tool_call_id=tc.get("id"),
                    tool_name=tool_name,
                    result=display_result,
                    success=True,
                )

            # Add tool_executions step
            tool_step = {
                "type": "tool_executions",
                "executions": tool_executions,
                "iteration": iteration,
            }
            all_steps.append(tool_step)

            # Save steps incrementally (so they persist even if job is cancelled)
            job.steps = all_steps
            job.save(update_fields=["steps"])

            # Extract todos from update_todos results (CRITICAL for steering)
            for i, tc in enumerate(file_tool_calls):
                func = tc.get("function", {})
                tool_name = func.get("name")
                if tool_name == "update_todos":
                    try:
                        result_content = tool_results[i].get("content", "")
                        result_data = json.loads(result_content)
                        if result_data.get("success") and result_data.get("data", {}).get("todos"):
                            current_todos = result_data["data"]["todos"]
                            logger.info(f"Updated todos: {len(current_todos)} items")
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to extract todos: {e}")

            # Track modified files and PR metadata
            for i, tc in enumerate(file_tool_calls):
                func = tc.get("function", {})
                tool_name = func.get("name")
                if tool_name in ("write_file", "edit_file"):
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                        if args.get("path"):
                            all_files_modified.append(args["path"])
                    except json.JSONDecodeError:
                        pass
                # Check for prepare_pull_request result
                elif tool_name == "prepare_pull_request":
                    if i < len(tool_results):
                        result_content = tool_results[i].get("content", "")
                        try:
                            result_data = json.loads(result_content) if isinstance(result_content, str) else result_content
                            if isinstance(result_data, dict) and result_data.get("data"):
                                pr_data = result_data["data"]
                                if pr_data.get("pr_ready"):
                                    job.pr_title = pr_data.get("pr_title", "")
                                    job.pr_body = pr_data.get("pr_body", "")
                                    job.pr_ready = True
                                    job.save(update_fields=["pr_title", "pr_body", "pr_ready"])
                                    logger.info(f"PR metadata stored for job {job.id}: {job.pr_title}")
                        except (json.JSONDecodeError, TypeError):
                            pass

            # Add assistant message with tool_calls to messages
            messages.append({
                "role": "assistant",
                "content": content or "",
                "tool_calls": file_tool_calls,
            })

            # Add tool result messages (with optional compression)
            if ENABLE_TOKEN_OPTIMIZATION and ENABLE_TOOL_COMPRESSION:
                from code_sessions.optimization.compressor import compress_tool_result

                for i, tool_msg in enumerate(tool_results):
                    tc = file_tool_calls[i]
                    func = tc.get("function", {})
                    tool_name = func.get("name", "unknown")
                    try:
                        tool_args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        tool_args = {}

                    # Compress the tool result content
                    original_content = tool_msg.get("content", "")
                    compressed_content = compress_tool_result(tool_name, original_content, tool_args)

                    compressed_msg = {
                        "role": tool_msg.get("role", "tool"),
                        "tool_call_id": tool_msg.get("tool_call_id"),
                        "content": compressed_content,
                    }
                    messages.append(compressed_msg)
            else:
                # No compression: add results as-is
                for tool_msg in tool_results:
                    messages.append(tool_msg)

        if on_progress:
            on_progress(0.9, "Processing response...")

        # Combine all content
        final_content = "\n\n".join(filter(None, all_content))

        # Add final assistant message to job history
        if final_content:
            job.add_message("assistant", final_content)

        # Store steps on job
        job.steps = all_steps
        job.save(update_fields=["steps"])

        # Return result with metadata
        return {
            "success": True,
            "content": final_content,
            "files_modified": list(set(all_files_modified)),
            "steps": all_steps,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_cost": total_cost,
            "iterations": iteration,
        }

    except Exception:
        logger.exception(f"Agent loop failed for job {job.id}")
        raise


def _build_coding_system_prompt(job, has_github: bool = False) -> str:
    """Build the system prompt for the coding agent.

    Optimized for TOKEN EFFICIENCY - encourages parallel tool calls
    and batch operations to minimize iterations.
    """
    repo_context = ""
    if job.session.github_repo_full_name:
        repo_context = f"Repository: {job.session.github_repo_full_name} (branch: {job.session.github_branch}), cloned to 'repo/'."

    github_section = ""
    if has_github:
        github_section = """
GitHub tools: github_list_issues, github_get_issue, github_create_issue, github_create_pull_request, github_get_pull_request, github_list_pull_requests, github_get_file_contents, github_push_files, github_create_branch, github_search_code, github_search_issues"""

    return f"""Expert software engineer. Be EFFICIENT - minimize tool call iterations.

{repo_context}
{github_section}

## EFFICIENCY RULES

1. **PARALLEL TOOL CALLS**: Call MULTIPLE tools in a SINGLE response when possible.
   - BAD: Call list_files, wait, then call read_file separately
   - GOOD: Call list_files + read_file + read_file together in ONE response

2. **MINIMIZE EXPLORATION**: Don't recursively list every directory. Target specific paths.

3. **CHAIN GIT COMMANDS**: `cd repo && git checkout -b feature/x && git add -A && git commit -m "msg"`

## Tools
- **update_todos**: CRITICAL - Use this FIRST to plan your work. Update as you complete tasks. Your todo list is shown to you each iteration.
- **explore_codebase**: Use for unfamiliar code or complex tasks. Returns analysis of relevant files.
- **read_file**: Read file contents. For large files, use parameters:
  - `read_file(path="file.py", max_lines=50)` - first 50 lines
  - `read_file(path="file.py", start_line=100, end_line=150)` - specific range
- **edit_file**: Modify existing files. ALWAYS read_file first to get exact content.
- **write_file**: Create new files.
- **run_bash**: Shell commands (git, npm, pip, tests). NOT for reading files.
- **list_files**: Browse directory contents.
- **search_code**: Search for patterns in files using regex. Faster than reading multiple files.
  - `search_code(pattern="def process_")` - find function definitions
  - `search_code(pattern="import.*requests", include="*.py")` - find imports in Python files
  - `search_code(pattern="TODO|FIXME", context_lines=2)` - find TODOs with context
- **prepare_pull_request**: Final step with title, summary, changes, test_plan.

## When to use explore_codebase
- Unfamiliar codebase or complex task requiring discovery
- Task mentions "find", "search", or doesn't specify exact files
- SKIP for simple, targeted changes where you already know the file

## Workflow
1. **PLAN FIRST**: Call `update_todos` to create your task plan (this keeps you on track)
2. Understand task → explore_codebase if needed
3. Create branch: `run_bash(command="cd repo && git checkout -b feature/name")`
4. Read files you need to modify: `read_file(path="...")`
5. Make changes: `edit_file` for existing files, `write_file` for new files
6. **UPDATE TODOS** as you complete each task (mark completed, update in_progress)
7. Test: `run_bash(command="cd repo && npm test")`
8. Commit: `run_bash(command="cd repo && git add -A && git commit -m 'description'")`
9. Call prepare_pull_request

## Rules
- ALWAYS read_file before edit_file (need exact content match)
- NEVER use run_bash for reading files (no cat/head/tail) - use read_file
- NEVER re-read a file you already read - the content is in your context
- Call tools in PARALLEL when they don't depend on each other
"""


def _format_todos_for_context(todos: list[dict]) -> str:
    """Format todos for injection into LLM context.

    This keeps the model aware of its plan and progress.
    """
    if not todos:
        return "No todos set."

    lines = []
    for todo in todos:
        status = todo.get("status", "pending")
        text = todo.get("text", todo.get("content", ""))
        if status == "completed":
            marker = "✓"
        elif status == "in_progress":
            marker = "→"
        else:
            marker = "○"
        lines.append(f"{marker} [{status}] {text}")

    # Add summary
    completed = len([t for t in todos if t.get("status") == "completed"])
    total = len(todos)
    lines.append(f"\nProgress: {completed}/{total} completed")

    return "\n".join(lines)


@shared_task
def cleanup_stale_jobs() -> dict:
    """Clean up jobs that have been running too long.

    This task runs periodically to mark stuck jobs as failed.

    Returns:
        dict: Cleanup results
    """
    from datetime import timedelta

    from .models import CodeJob

    # Find jobs that have been running for more than 2 hours
    stale_threshold = timezone.now() - timedelta(hours=2)
    stale_jobs = CodeJob.objects.filter(
        status__in=[CodeJob.Status.RUNNING, CodeJob.Status.CLONING],
        started_at__lt=stale_threshold,
    )

    count = 0
    for job in stale_jobs:
        job.mark_failed("Job timed out after 2 hours")
        send_job_update(str(job.id), "failed", job.progress, "Job timed out")
        count += 1
        logger.warning(f"Marked stale job {job.id} as failed")

    return {"cleaned_up": count}
