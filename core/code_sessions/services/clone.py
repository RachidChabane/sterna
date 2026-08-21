"""Clone service for GitHub repositories.

Handles cloning GitHub repositories into user sandboxes for AI agent
exploration and modification.
"""

import logging
import re
from typing import Any, Dict, Optional

import httpx

from .github import GitHubService, parse_repo_full_name
from sterna.middleware.request_id import request_id_headers

logger = logging.getLogger(__name__)


def _sanitize_clone_error(raw_error: str) -> str:
    """Convert raw technical error messages into user-friendly messages.

    Keeps the original error in logs but returns a clean message for the UI.
    """
    lower = raw_error.lower()

    # Repository access / not found
    if "repository" in lower and "not found" in lower:
        return "Repository not found. Check the name or ensure you have access to this repository."
    if "could not read username" in lower or "authentication" in lower or "401" in lower:
        return "Authentication failed. Try reconnecting your GitHub account."
    if "permission denied" in lower or "403" in lower:
        return "Access denied. You don't have permission to clone this repository."

    # Branch issues
    if "remote branch" in lower and "not found" in lower:
        return "Branch not found. The specified branch doesn't exist in this repository."

    # Network / connectivity
    if "could not resolve host" in lower or "name resolution" in lower:
        return "Network error. Could not reach GitHub. Please try again."
    if "timed out" in lower or "timeout" in lower:
        return "Clone timed out. The repository may be too large or the connection is slow. Please try again."
    if "connection refused" in lower or "connection reset" in lower:
        return "Connection error. Please try again in a moment."

    # Sandbox / workspace issues
    if "failed to create workspace" in lower or "command failed with exit code" in lower:
        return "Workspace setup failed. The sandbox may be starting up — please try again in a moment."
    if "http 5" in lower or "internal server error" in lower:
        return "Service temporarily unavailable. Please try again in a moment."
    if "http 502" in lower or "http 503" in lower or "http 504" in lower:
        return "Service temporarily unavailable. Please try again in a moment."

    # Disk / space
    if "no space left" in lower or "disk quota" in lower:
        return "Not enough storage space. Try a smaller repository."

    # Invalid input
    if "invalid repository url" in lower:
        return "Invalid repository URL. Use the format owner/repo or a GitHub URL."

    # Fallback: strip internal prefixes and technical details
    # Remove common prefixes
    cleaned = raw_error
    for prefix in ["Clone failed: ", "Failed to create workspace directory: ", "Re-clone failed: ", "fatal: "]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]

    # If the remaining message is still cryptic (contains exit codes, HTTP details, tracebacks)
    if "exit code" in cleaned.lower() or "traceback" in cleaned.lower() or cleaned.startswith("HTTP "):
        return "Something went wrong. Please try again."

    # Cap length for UI display
    if len(cleaned) > 150:
        cleaned = cleaned[:147] + "..."

    return cleaned


def parse_repo_url(repo_url: str) -> str:
    """Parse repository URL and return owner/repo format.

    Accepts:
    - owner/repo
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git

    Returns:
        str: Repository in owner/repo format
    """
    repo_url = repo_url.strip()

    # Already in owner/repo format
    if "/" in repo_url and not repo_url.startswith("http") and not repo_url.startswith("git@"):
        parts = repo_url.split("/")
        if len(parts) == 2:
            return repo_url

    # HTTPS URL
    if repo_url.startswith("https://github.com/"):
        path = repo_url.replace("https://github.com/", "")
        if path.endswith(".git"):
            path = path[:-4]
        # Remove trailing slash
        path = path.rstrip("/")
        # Extract owner/repo (first two path segments)
        parts = path.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"

    # SSH URL
    if repo_url.startswith("git@github.com:"):
        path = repo_url.replace("git@github.com:", "")
        if path.endswith(".git"):
            path = path[:-4]
        return path

    raise ValueError(f"Invalid repository URL format: {repo_url}")


async def clone_repository(
    user_id: str,
    conversation_id: str,
    chat_id: str,
    repo_url: str,
    branch: Optional[str],
    github_token: str,
    auth_token: str,
) -> Dict[str, Any]:
    """Clone a GitHub repository into the user's sandbox workspace.

    Args:
        user_id: User ID for sandbox isolation
        conversation_id: Conversation ID for ClonedRepository record
        chat_id: Chat ID for workspace scoping
        repo_url: GitHub repository (owner/repo or full URL)
        branch: Branch to clone (optional, uses default if not specified)
        github_token: GitHub OAuth token
        auth_token: Orchestrator auth token

    Returns:
        Dict with clone result
    """
    try:
        # Parse repository URL
        full_name = parse_repo_url(repo_url)
        owner, repo = parse_repo_full_name(full_name)

        logger.info(f"[clone] Cloning {full_name} (branch: {branch or 'default'}) for user {user_id}")

        # Get repository info to determine default branch
        async with GitHubService(github_token) as github:
            repo_info = await github.get_repo(owner, repo)
            default_branch = repo_info.get("default_branch", "main")
            clone_url = github.get_clone_url_with_token(full_name)

        # Private repos not supported yet
        if repo_info.get("private"):
            return {
                "success": False,
                "error": "Private repositories are not supported yet. Please use a public repository."
            }

        # Determine target branch
        target_branch = branch or default_branch

        # Workspace path
        workspace_path = f"/workspace/chat-{chat_id}/repo"

        # Execute clone via orchestrator
        orchestrator_url = "http://sterna-orchestrator:8003"

        # Clear and create workspace directory (supports re-cloning)
        mkdir_response = await _execute_bash(
            orchestrator_url=orchestrator_url,
            auth_token=auth_token,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            command=f"rm -rf {workspace_path} && mkdir -p {workspace_path}",
        )

        if not mkdir_response.get("success"):
            raw = f"Failed to create workspace directory: {mkdir_response.get('error')}"
            logger.error(f"[clone] {raw}")
            return {
                "success": False,
                "error": _sanitize_clone_error(raw)
            }

        # Clone the repository
        clone_cmd = f"cd {workspace_path} && git clone --depth 100 --branch {target_branch} {clone_url} ."

        clone_response = await _execute_bash(
            orchestrator_url=orchestrator_url,
            auth_token=auth_token,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            command=clone_cmd,
            timeout=300,  # 5 minutes for large repos
        )

        if not clone_response.get("success") and clone_response.get("exit_code") != 0:
            error_msg = clone_response.get("output", "Unknown error")
            # Strip token from logs
            error_msg = re.sub(r"oauth2:[^@]+@", "oauth2:***@", error_msg)
            raw = f"Clone failed: {error_msg}"
            logger.error(f"[clone] {raw}")
            return {
                "success": False,
                "error": _sanitize_clone_error(raw)
            }

        # Get HEAD commit info
        head_info = await _execute_bash(
            orchestrator_url=orchestrator_url,
            auth_token=auth_token,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            command=f"cd {workspace_path} && git log -1 --format='%H|||%s'",
        )

        head_commit_sha = ""
        head_commit_message = ""
        if head_info.get("success"):
            output = head_info.get("output", "").strip()
            if "|||" in output:
                parts = output.split("|||", 1)
                head_commit_sha = parts[0]
                head_commit_message = parts[1][:500] if len(parts) > 1 else ""

        # Create or update ClonedRepository record

        try:
            conversation = await _get_conversation(conversation_id)
            if conversation:
                cloned_repo, created = await _create_or_update_cloned_repo(
                    conversation=conversation,
                    full_name=full_name,
                    clone_url=f"https://github.com/{full_name}",
                    default_branch=default_branch,
                    current_branch=target_branch,
                    workspace_path=workspace_path,
                    head_commit_sha=head_commit_sha,
                    head_commit_message=head_commit_message,
                )
                logger.info(f"[clone] {'Created' if created else 'Updated'} ClonedRepository for {full_name}")
        except Exception as e:
            logger.warning(f"[clone] Failed to create ClonedRepository record: {e}")

        return {
            "success": True,
            "full_name": full_name,
            "branch": target_branch,
            "workspace_path": workspace_path,
            "head_commit_sha": head_commit_sha,
            "head_commit_message": head_commit_message,
        }

    except ValueError as e:
        return {
            "success": False,
            "error": _sanitize_clone_error(str(e))
        }
    except Exception as e:
        logger.error(f"[clone] Error cloning repository: {e}", exc_info=True)
        return {
            "success": False,
            "error": _sanitize_clone_error(f"Clone failed: {str(e)}")
        }


async def ensure_repo_in_sandbox(
    user_id: str,
    conversation_id: str,
    auth_token: str,
    orchestrator_url: str = "http://sterna-orchestrator:8003",
) -> Dict[str, Any]:
    """Ensure the cloned repo exists in the sandbox, re-cloning if necessary.

    The sandbox uses tmpfs, so the repo disappears when the container recycles.
    This function:
      1. Checks if /workspace/chat-{id}/repo/.git exists
      2. If missing, re-clones from GitHub with branch fallback
      3. Force-restores versioned files on top
      4. Reconciles git state (creates branch, stages, commits)

    Can be called from both Django views (IDE init) and LLM tools.

    Returns:
        Dict with keys: action ("none", "restored"), success, error, branch, commit_sha
    """
    try:
        cloned_repo = await _get_cloned_repo(conversation_id)

        if not cloned_repo:
            return {"action": "none", "success": True, "message": "No cloned repo for this conversation"}

        # Extract chat_id from workspace_path
        workspace_path = cloned_repo.workspace_path or ""
        import re as _re
        match = _re.search(r"chat-([^/]+)", workspace_path)
        if not match:
            return {"action": "none", "success": True, "message": "Cannot determine chat_id from workspace_path"}
        chat_id = match.group(1)

        # Step 1: Check if repo exists via orchestrator
        async with httpx.AsyncClient() as client:
            check_resp = await client.post(
                f"{orchestrator_url}/workspace/ensure-repo",
                json={"user_id": user_id, "chat_id": chat_id},
                headers=request_id_headers({
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "application/json",
                }),
                timeout=15.0,
            )

        if check_resp.status_code == 200:
            check_data = check_resp.json()
            if not check_data.get("needs_clone"):
                return {"action": "none", "success": True, "message": "Repo already present"}

        logger.info(f"[ensure_repo] Repo missing in sandbox, re-cloning {cloned_repo.full_name}...")

        # Step 2: Get GitHub token
        github_conn = await _get_github_connection(user_id)

        if not github_conn or not github_conn.access_token:
            return {
                "action": "none",
                "success": False,
                "error": "No GitHub token found",
                "code": "github_not_connected",
            }

        # Step 3: Re-clone with branch fallback
        clone_result = await clone_repository(
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            repo_url=cloned_repo.full_name,
            branch=cloned_repo.current_branch,
            github_token=github_conn.access_token,
            auth_token=auth_token,
        )

        if not clone_result.get("success"):
            # Fallback: try default branch if current_branch failed
            if cloned_repo.current_branch != cloned_repo.default_branch:
                logger.info(
                    f"[ensure_repo] Clone with branch '{cloned_repo.current_branch}' failed, "
                    f"falling back to '{cloned_repo.default_branch}'"
                )
                clone_result = await clone_repository(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    chat_id=chat_id,
                    repo_url=cloned_repo.full_name,
                    branch=cloned_repo.default_branch,
                    github_token=github_conn.access_token,
                    auth_token=auth_token,
                )

            if not clone_result.get("success"):
                return {"action": "none", "success": False, "error": _sanitize_clone_error(f"Re-clone failed: {clone_result.get('error')}")}

        logger.info(f"[ensure_repo] Re-cloned {cloned_repo.full_name}")

        # Step 4: Force-restore versioned files on top
        try:
            async with httpx.AsyncClient() as client:
                restore_resp = await client.post(
                    f"{orchestrator_url}/workspace/restore",
                    json={"user_id": user_id, "chat_id": chat_id, "force": True},
                    headers=request_id_headers({
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json",
                    }),
                    timeout=60.0,
                )
            if restore_resp.status_code == 200:
                restore_data = restore_resp.json()
                files_restored = restore_data.get("files_synced", 0)
                if files_restored > 0:
                    logger.info(f"[ensure_repo] Restored {files_restored} versioned files on top of re-cloned repo")
        except Exception as e:
            logger.warning(f"[ensure_repo] Force-restore failed: {e}")

        # Step 5: Reconcile git state (create branch, stage, commit)
        reconcile_result = {"success": False}
        try:
            async with httpx.AsyncClient() as client:
                reconcile_resp = await client.post(
                    f"{orchestrator_url}/workspace/reconcile-git",
                    json={
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "target_branch": cloned_repo.current_branch,
                        "default_branch": cloned_repo.default_branch,
                    },
                    headers=request_id_headers({
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json",
                    }),
                    timeout=30.0,
                )
            if reconcile_resp.status_code == 200:
                reconcile_result = reconcile_resp.json()
                if reconcile_result.get("committed"):
                    logger.info(
                        f"[ensure_repo] Git reconciled: branch={reconcile_result.get('branch')}, "
                        f"sha={reconcile_result.get('commit_sha', '')[:8]}"
                    )
                    # Update ClonedRepository with new HEAD
                    new_sha = reconcile_result.get("commit_sha", "")
                    if new_sha:
                        await _update_cloned_repo_head(conversation_id, new_sha)
        except Exception as e:
            logger.warning(f"[ensure_repo] Git reconciliation failed: {e}")

        return {
            "action": "restored",
            "success": True,
            "branch": reconcile_result.get("branch", cloned_repo.current_branch),
            "commit_sha": reconcile_result.get("commit_sha", ""),
            "committed": reconcile_result.get("committed", False),
        }

    except Exception as e:
        logger.error(f"[ensure_repo] Failed: {e}", exc_info=True)
        return {"action": "none", "success": False, "error": str(e)}


async def _execute_bash(
    orchestrator_url: str,
    auth_token: str,
    user_id: str,
    conversation_id: str,
    chat_id: str,
    command: str,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Execute a bash command via orchestrator.

    Args:
        orchestrator_url: Orchestrator service URL
        auth_token: Authentication token
        user_id: User ID
        conversation_id: Conversation ID
        chat_id: Chat ID
        command: Bash command to execute
        timeout: Command timeout in seconds

    Returns:
        Dict with execution result
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{orchestrator_url}/fs/bash",
                json={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "chat_id": chat_id,
                    "sync_mode": True,
                    "command": command,
                    "timeout": timeout,
                },
                headers=request_id_headers({
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "application/json",
                }),
                timeout=timeout + 30,  # Add buffer to HTTP timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
    except Exception as e:
        logger.error(f"[clone] Bash execution error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _get_cloned_repo(conversation_id: str):
    """Get the ClonedRepository for a conversation (async wrapper for sync ORM).

    Uses ``asyncio.to_thread`` rather than ``asgiref.sync.sync_to_async`` on
    purpose: this function is reached both from genuinely async request
    handling (the coding-agent tool path, see ``llm.langchain_file_tools``)
    and from a plain DRF view that manually opens its own event loop with
    ``asyncio.new_event_loop().run_until_complete(...)`` (see
    ``code_sessions.views.ensure_repo``). ``sync_to_async``'s default
    ``thread_sensitive=True`` tries to hand the DB call back to "the"
    outer thread's executor, which is exactly the thread already blocked in
    ``run_until_complete`` in the latter case, raising "You cannot submit
    onto CurrentThreadExecutor from its own thread". ``asyncio.to_thread``
    runs the call in a fresh worker thread instead and has no such coupling.
    """
    from django.db import close_old_connections
    from code_sessions.models import ClonedRepository
    import asyncio

    def _get():
        close_old_connections()
        return ClonedRepository.objects.filter(conversation_id=conversation_id).first()

    return await asyncio.to_thread(_get)


async def _get_github_connection(user_id: str):
    """Get a user's GitHubConnection (async wrapper for sync ORM).

    See ``_get_cloned_repo`` for why this uses ``asyncio.to_thread`` instead
    of ``sync_to_async``.
    """
    from django.db import close_old_connections
    from code_sessions.models import GitHubConnection
    import asyncio

    def _get():
        close_old_connections()
        return GitHubConnection.objects.filter(user_id=user_id).first()

    return await asyncio.to_thread(_get)


async def _update_cloned_repo_head(conversation_id: str, head_commit_sha: str):
    """Update a ClonedRepository's HEAD after git reconciliation (async wrapper).

    See ``_get_cloned_repo`` for why this uses ``asyncio.to_thread`` instead
    of ``sync_to_async``.
    """
    from django.db import close_old_connections
    from code_sessions.models import ClonedRepository
    import asyncio

    def _update():
        close_old_connections()
        return ClonedRepository.objects.filter(conversation_id=conversation_id).update(
            head_commit_sha=head_commit_sha,
            head_commit_message="workspace restoration",
        )

    return await asyncio.to_thread(_update)


async def _get_conversation(conversation_id: str):
    """Get conversation by ID (async wrapper for sync ORM)."""
    from django.db import close_old_connections
    from conversations.models import Conversation
    import asyncio

    def _get():
        close_old_connections()
        try:
            return Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return None

    return await asyncio.to_thread(_get)


async def _create_or_update_cloned_repo(
    conversation,
    full_name: str,
    clone_url: str,
    default_branch: str,
    current_branch: str,
    workspace_path: str,
    head_commit_sha: str,
    head_commit_message: str,
):
    """Create or update ClonedRepository record (async wrapper)."""
    from django.db import close_old_connections
    from code_sessions.models import ClonedRepository
    import asyncio

    def _create_or_update():
        close_old_connections()
        return ClonedRepository.objects.update_or_create(
            conversation=conversation,
            defaults={
                "full_name": full_name,
                "clone_url": clone_url,
                "default_branch": default_branch,
                "current_branch": current_branch,
                "workspace_path": workspace_path,
                "head_commit_sha": head_commit_sha,
                "head_commit_message": head_commit_message,
            }
        )

    return await asyncio.to_thread(_create_or_update)
