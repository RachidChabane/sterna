"""Views for code sessions REST API."""

import logging
import secrets

from django.conf import settings
from django.core.cache import cache
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from django.shortcuts import get_object_or_404

from .models import AgentPlan, ClonedRepository, CodeJob, CodeSession, CreatedPullRequest, GitHubConnection, PlanStep, SubAgent
from .serializers import (
    AgentPlanSerializer,
    AgentPlanSummarySerializer,
    ClonedRepositorySerializer,
    CodeJobCreateSerializer,
    CodeJobSerializer,
    CodeSessionCreateSerializer,
    CodeSessionSerializer,
    CreatedPullRequestSerializer,
    GitHubBranchSerializer,
    GitHubCallbackSerializer,
    GitHubIssueSerializer,
    GitHubRepoSerializer,
    PlanStepSerializer,
    SubAgentCreateSerializer,
    SubAgentSerializer,
    SubAgentSummarySerializer,
)
from .services.github import GitHubAPIError, GitHubService, parse_repo_full_name

logger = logging.getLogger(__name__)

# Cache key prefix for OAuth state
OAUTH_STATE_PREFIX = "code_github_oauth_state:"
OAUTH_STATE_EXPIRY = 600  # 10 minutes


# ==================== GitHub OAuth Views ====================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_connect(request: Request) -> Response:
    """Initiate GitHub OAuth flow.

    Generates a state token and returns the authorization URL.
    """
    # Generate state token for CSRF protection
    # Prefix with "code:" so the frontend callback knows to route to Code feature
    base_state = secrets.token_urlsafe(32)
    state = f"code:{base_state}"

    # Store state in cache with user ID (use base_state as key)
    cache_key = f"{OAUTH_STATE_PREFIX}{base_state}"
    cache.set(cache_key, str(request.user.id), OAUTH_STATE_EXPIRY)

    # Get redirect URI from settings or request
    redirect_uri = request.query_params.get(
        "redirect_uri",
        settings.GITHUB_OAUTH_REDIRECT_URI,
    )

    # Generate authorization URL
    auth_url = GitHubService.get_authorization_url(
        state=state,
        redirect_uri=redirect_uri,
    )

    return Response({
        "authorization_url": auth_url,
        "state": state,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_callback(request: Request) -> Response:
    """Handle GitHub OAuth callback.

    Exchanges code for token and creates/updates GitHubConnection.
    """
    serializer = GitHubCallbackSerializer(data=request.query_params)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    code = serializer.validated_data["code"]
    state = serializer.validated_data["state"]

    # Strip "code:" prefix if present (added by github_connect)
    base_state = state[5:] if state.startswith("code:") else state

    # Verify state token
    cache_key = f"{OAUTH_STATE_PREFIX}{base_state}"
    stored_user_id = cache.get(cache_key)

    if not stored_user_id:
        return Response(
            {"error": "Invalid or expired state token"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if stored_user_id != str(request.user.id):
        return Response(
            {"error": "State token mismatch"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Delete used state
    cache.delete(cache_key)

    try:
        # Exchange code for token
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            token_data = loop.run_until_complete(
                GitHubService.exchange_code_for_token(code)
            )
        finally:
            loop.close()

        access_token = token_data.get("access_token")
        if not access_token:
            return Response(
                {"error": "No access token received from GitHub"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get user info from GitHub
        async def get_user_info():
            async with GitHubService(access_token) as github:
                return await github.get_user()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            user_info = loop.run_until_complete(get_user_info())
        finally:
            loop.close()

        # Create or update GitHubConnection
        connection, created = GitHubConnection.objects.update_or_create(
            user=request.user,
            defaults={
                "access_token": access_token,
                "github_username": user_info.get("login"),
                "github_user_id": user_info.get("id"),
                "avatar_url": user_info.get("avatar_url", ""),
                "scopes": token_data.get("scope", "").split(","),
            },
        )

        logger.info(
            f"GitHub connected for user {request.user.id}: {user_info.get('login')}"
        )

        return Response({
            "success": True,
            "username": user_info.get("login"),
            "created": created,
        })

    except GitHubAPIError as e:
        logger.error(f"GitHub OAuth error: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.exception("Unexpected error during GitHub OAuth")
        return Response(
            {"error": "Failed to connect GitHub account"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_status(request: Request) -> Response:
    """Get GitHub connection status."""
    try:
        connection = GitHubConnection.objects.get(user=request.user)
        return Response({
            "connected": True,
            "username": connection.github_username,
            "avatar_url": connection.avatar_url,
            "scopes": connection.scopes,
        })
    except GitHubConnection.DoesNotExist:
        return Response({
            "connected": False,
            "username": None,
            "avatar_url": None,
            "scopes": [],
        })


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def github_disconnect(request: Request) -> Response:
    """Disconnect GitHub account."""
    deleted, _ = GitHubConnection.objects.filter(user=request.user).delete()

    if deleted:
        logger.info(f"GitHub disconnected for user {request.user.id}")

    return Response({"success": True, "deleted": deleted > 0})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_repos(request: Request) -> Response:
    """List user's GitHub repositories."""
    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    page = int(request.query_params.get("page", 1))
    per_page = int(request.query_params.get("per_page", 30))

    try:
        import asyncio

        async def fetch_repos():
            async with GitHubService(connection.access_token) as github:
                return await github.list_repos(page=page, per_page=per_page)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            repos = loop.run_until_complete(fetch_repos())
        finally:
            loop.close()

        serializer = GitHubRepoSerializer(repos, many=True)
        return Response({
            "results": serializer.data,
            "page": page,
            "per_page": per_page,
        })

    except GitHubAPIError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_branches(request: Request, owner: str, repo: str) -> Response:
    """List branches for a GitHub repository."""
    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        import asyncio

        async def fetch_branches():
            async with GitHubService(connection.access_token) as github:
                return await github.list_branches(owner, repo)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            branches = loop.run_until_complete(fetch_branches())
        finally:
            loop.close()

        serializer = GitHubBranchSerializer(branches, many=True)
        return Response({"branches": serializer.data})

    except GitHubAPIError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_issues(request: Request, owner: str, repo: str) -> Response:
    """List issues for a GitHub repository."""
    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    page = int(request.query_params.get("page", 1))
    per_page = int(request.query_params.get("per_page", 30))
    state = request.query_params.get("state", "open")

    try:
        import asyncio

        async def fetch_issues():
            async with GitHubService(connection.access_token) as github:
                return await github.list_issues(owner, repo, state=state, page=page, per_page=per_page)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            issues = loop.run_until_complete(fetch_issues())
        finally:
            loop.close()

        serializer = GitHubIssueSerializer(issues, many=True)
        return Response({
            "results": serializer.data,
            "page": page,
            "per_page": per_page,
        })

    except GitHubAPIError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ==================== Code Session Views ====================


class CodeSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for code sessions CRUD."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter sessions to current user."""
        return CodeSession.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        """Use appropriate serializer based on action."""
        if self.action == "create":
            return CodeSessionCreateSerializer
        return CodeSessionSerializer

    def perform_create(self, serializer):
        """Set user when creating session."""
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """Create session and return full serialized response including id."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Return the created session with full serializer (including id)
        response_serializer = CodeSessionSerializer(serializer.instance)
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """Archive a session."""
        session = self.get_object()
        session.status = CodeSession.Status.ARCHIVED
        session.save(update_fields=["status"])
        return Response({"status": "archived"})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate (unarchive) a session."""
        session = self.get_object()
        session.status = CodeSession.Status.ACTIVE
        session.save(update_fields=["status"])
        return Response({"status": "active"})

    @action(detail=True, methods=["get", "post"], url_path="jobs")
    def jobs(self, request, pk=None):
        """List jobs (GET) or create a new job (POST) for a session."""
        session = self.get_object()

        if request.method == "GET":
            # List jobs for the session
            jobs = session.jobs.all().order_by('-created_at')

            page = self.paginate_queryset(jobs)
            if page is not None:
                # Use full serializer to include steps, messages, etc.
                serializer = CodeJobSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            # Use full serializer to include steps, messages, etc.
            serializer = CodeJobSerializer(jobs, many=True)
            return Response(serializer.data)

        else:  # POST - create job
            return self._create_job(request, session)

    def _create_job(self, request, session):
        """Create a new job in the session."""
        from decimal import Decimal

        from usage_quota.billing.service import get_billing_service
        from usage_quota.models import FeatureType, ServiceType

        # Tier gate: refuse when the plan disallows code sessions or
        # the weekly limit is reached. Raises → DRF handler → 402.
        get_billing_service().check_quota(
            user=request.user,
            service=ServiceType.CODE_SESSION,
            estimated_cost=Decimal('0'),
            feature=FeatureType.CODE_SESSION,
            feature_name='code_session',
        )

        serializer = CodeJobCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Create the job
        job = CodeJob.objects.create(
            session=session,
            prompt=serializer.validated_data["prompt"],
            enable_reasoning=serializer.validated_data.get("enable_reasoning", False),
            status=CodeJob.Status.PENDING,
        )

        # Update session activity
        session.update_activity()

        # Queue the job for execution
        from .tasks import execute_code_job

        task = execute_code_job.delay(str(job.id))
        job.celery_task_id = task.id
        job.status = CodeJob.Status.QUEUED
        job.save(update_fields=["celery_task_id", "status"])

        logger.info(f"Created job {job.id} for session {session.id}")

        return Response(
            CodeJobSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )


# ==================== Code Job Views ====================


class CodeJobViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for code jobs (read-only, created via sessions)."""

    permission_classes = [IsAuthenticated]
    serializer_class = CodeJobSerializer

    def get_queryset(self):
        """Filter jobs to current user's sessions."""
        return CodeJob.objects.filter(session__user=self.request.user)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a running job."""
        job = self.get_object()

        if not job.is_running:
            return Response(
                {"error": "Job is not running"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Revoke Celery task
        if job.celery_task_id:
            from celery import current_app

            current_app.control.revoke(job.celery_task_id, terminate=True)

        job.status = CodeJob.Status.CANCELLED
        job.save(update_fields=["status"])

        logger.info(f"Cancelled job {job.id}")

        return Response({"status": "cancelled"})

    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        """Get logs for a job."""
        job = self.get_object()
        logs = job.logs.all()

        from .serializers import JobLogSerializer

        serializer = JobLogSerializer(logs, many=True)
        return Response({"logs": serializer.data})

    @action(detail=True, methods=["get"])
    def files(self, request, pk=None):
        """List files in job workspace."""
        job = self.get_object()

        # Get files from sandbox via orchestrator
        # This will be implemented with the sandbox integration
        # For now, return the files_modified list
        return Response({
            "files": job.files_modified,
            "workspace_path": f"/workspace/chat-{job.session.id}",
        })

    @action(detail=True, methods=["post"])
    def create_pr(self, request, pk=None):
        """Create a pull request with the job's changes."""
        job = self.get_object()
        session = job.session

        # Validate job is completed with changes
        if job.status != "completed":
            return Response(
                {"error": "Job must be completed to create a PR"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not job.files_modified:
            return Response(
                {"error": "No files were modified in this job"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate GitHub connection
        try:
            connection = GitHubConnection.objects.get(user=request.user)
        except GitHubConnection.DoesNotExist:
            return Response(
                {"error": "GitHub account not connected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate session has a GitHub repo
        if not session.github_repo_full_name:
            return Response(
                {"error": "Session is not connected to a GitHub repository"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get PR details from request
        branch = request.data.get("branch")
        draft = request.data.get("draft", False)

        if not branch:
            return Response(
                {"error": "Branch name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use PR metadata prepared by the assistant (if available)
        # Otherwise fall back to auto-generating from the job prompt
        if job.pr_ready and job.pr_title:
            title = job.pr_title
            pr_body = job.pr_body
        else:
            # Fallback: Auto-generate PR title from the job prompt
            prompt_summary = job.prompt.strip()
            if len(prompt_summary) > 72:
                # Truncate at word boundary
                prompt_summary = prompt_summary[:72].rsplit(' ', 1)[0] + '...'
            title = prompt_summary

            # Build fallback PR body
            pr_body = f"## Summary\n\n{job.prompt}\n\n"
            pr_body += "## Files Changed\n\n"
            for f in job.files_modified:
                pr_body += f"- `{f}`\n"
            pr_body += "\n---\n*Created with Sterna*"

        try:
            owner, repo = parse_repo_full_name(session.github_repo_full_name)

            # Use MCP tool executor to push files and create PR
            from sandbox.orchestrator.mcp_tools import MCPToolExecutor
            import httpx

            from sterna.middleware.request_id import request_id_headers

            executor = MCPToolExecutor(github_token=connection.access_token)

            try:
                # First, try to create the branch (will fail silently if exists)
                try:
                    executor.execute("github_create_branch", {
                        "owner": owner,
                        "repo": repo,
                        "branch": branch,
                        "from_branch": session.github_branch or "main"
                    })
                except httpx.HTTPStatusError as e:
                    # 422 means branch already exists, which is fine
                    if e.response.status_code != 422:
                        raise

                # Read and push the modified files from sandbox
                # We need to get the file contents from the sandbox
                orchestrator_url = "http://sterna-orchestrator:8003"

                files_to_push = []
                for file_path in job.files_modified:
                    # Read file from sandbox
                    read_result = httpx.post(
                        f"{orchestrator_url}/fs/read",
                        json={
                            "user_id": str(request.user.id),
                            "conversation_id": str(session.id),
                            "chat_id": str(session.id),  # Use session.id for consistent workspace
                            "sync_mode": True,
                            "path": file_path
                        },
                        headers=request_id_headers({"Authorization": request.headers.get("Authorization", "")}),
                        timeout=30.0
                    )

                    if read_result.status_code == 200:
                        result_data = read_result.json()
                        if result_data.get("success") and result_data.get("content"):
                            files_to_push.append({
                                "path": file_path,
                                "content": result_data["content"]
                            })

                if not files_to_push:
                    return Response(
                        {"error": "Could not read modified files from sandbox"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                # Push files to GitHub
                push_result = executor.execute("github_push_files", {
                    "owner": owner,
                    "repo": repo,
                    "branch": branch,
                    "message": f"{title}\n\nChanges from AI coding assistant",
                    "files": files_to_push
                })

                if not push_result.get("success"):
                    return Response(
                        {"error": push_result.get("error", "Failed to push files")},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                # Create the pull request
                pr_result = executor.execute("github_create_pull_request", {
                    "owner": owner,
                    "repo": repo,
                    "title": title,
                    "body": pr_body,
                    "head": branch,
                    "base": session.github_branch or "main",
                    "draft": draft
                })

                if not pr_result.get("success"):
                    return Response(
                        {"error": pr_result.get("error", "Failed to create pull request")},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                pr_data = pr_result.get("data", {})

                logger.info(f"Created PR #{pr_data.get('number')} for job {job.id}")

                return Response({
                    "success": True,
                    "pr_number": pr_data.get("number"),
                    "pr_url": pr_data.get("html_url"),
                    "pr_title": pr_data.get("title"),
                    "files_pushed": len(files_to_push)
                })

            finally:
                executor.close()

        except GitHubAPIError as e:
            logger.error(f"GitHub API error creating PR: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Error creating PR")
            return Response(
                {"error": f"Failed to create pull request: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ==================== Session Git Operations ====================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def session_git_diff(request: Request, session_id: str) -> Response:
    """Get diff between two refs (branches/commits) for a session.

    Query params:
        - base: Base ref (branch or commit SHA)
        - head: Head ref (branch or commit SHA)
    """
    try:
        session = CodeSession.objects.get(id=session_id, user=request.user)
    except CodeSession.DoesNotExist:
        return Response(
            {"error": "Session not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not session.github_repo_full_name:
        return Response(
            {"error": "Session is not connected to a GitHub repository"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    base = request.query_params.get("base")
    head = request.query_params.get("head")

    if not base or not head:
        return Response(
            {"error": "Both 'base' and 'head' parameters are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        import asyncio

        owner, repo = parse_repo_full_name(session.github_repo_full_name)

        async def get_diff():
            async with GitHubService(connection.access_token) as github:
                return await github.compare_commits(owner, repo, base, head)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            diff_data = loop.run_until_complete(get_diff())
        finally:
            loop.close()

        return Response({
            "diff": diff_data.get("diff", ""),
            "files": [f.get("filename", "") for f in diff_data.get("files", [])],
            "additions": diff_data.get("additions", 0),
            "deletions": diff_data.get("deletions", 0),
        })

    except GitHubAPIError as e:
        logger.error(f"GitHub API error getting diff: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.exception("Error getting diff")
        return Response(
            {"error": f"Failed to get diff: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def session_git_commits(request: Request, session_id: str) -> Response:
    """Get commit history for a branch in a session.

    Query params:
        - branch: Branch name (defaults to session's branch)
        - limit: Max number of commits (default 20)
    """
    try:
        session = CodeSession.objects.get(id=session_id, user=request.user)
    except CodeSession.DoesNotExist:
        return Response(
            {"error": "Session not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not session.github_repo_full_name:
        return Response(
            {"error": "Session is not connected to a GitHub repository"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    branch = request.query_params.get("branch", session.github_branch or "main")
    limit = min(int(request.query_params.get("limit", 20)), 100)

    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        import asyncio

        owner, repo = parse_repo_full_name(session.github_repo_full_name)

        async def get_commits():
            async with GitHubService(connection.access_token) as github:
                return await github.list_commits(owner, repo, branch, limit)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            commits_data = loop.run_until_complete(get_commits())
        finally:
            loop.close()

        commits = []
        for commit in commits_data:
            commit_info = commit.get("commit", {})
            author_info = commit_info.get("author", {})
            commits.append({
                "sha": commit.get("sha", ""),
                "message": commit_info.get("message", ""),
                "author": author_info.get("name", "Unknown"),
                "date": author_info.get("date", ""),
            })

        return Response({"commits": commits})

    except GitHubAPIError as e:
        logger.error(f"GitHub API error getting commits: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.exception("Error getting commits")
        return Response(
            {"error": f"Failed to get commits: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== Cloned Repository Views ====================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def conversation_repo_status(request: Request, conversation_id: str) -> Response:
    """Get cloned repository status for a conversation."""
    try:
        cloned_repo = ClonedRepository.objects.get(
            conversation_id=conversation_id,
            conversation__user=request.user,
        )
        serializer = ClonedRepositorySerializer(cloned_repo)
        return Response({
            "has_repo": True,
            **serializer.data,
        })
    except ClonedRepository.DoesNotExist:
        return Response({
            "has_repo": False,
            "full_name": None,
            "current_branch": None,
            "head_commit_sha": None,
            "workspace_path": None,
        })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def clone_repo(request: Request, conversation_id: str) -> Response:
    """Clone a GitHub repository for a conversation.

    POST body:
        - repo_url: GitHub repo (owner/repo or full URL)
        - branch: Branch to clone (optional)
    """
    from conversations.models import Conversation

    # Validate conversation exists and belongs to user
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
    except Conversation.DoesNotExist:
        return Response(
            {"error": "Conversation not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get repo URL from request
    repo_url = request.data.get("repo_url")
    if not repo_url:
        return Response(
            {"error": "repo_url is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    branch = request.data.get("branch")

    # Check GitHub connection
    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected", "code": "github_not_connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get chat ID (first chat in conversation)
    chat = conversation.chats.first()
    if not chat:
        return Response(
            {"error": "Conversation has no chats"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get auth token from request
    auth_header = request.headers.get("Authorization", "")
    auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

    try:
        import asyncio
        from .services.clone import clone_repository

        async def do_clone():
            return await clone_repository(
                user_id=str(request.user.id),
                conversation_id=str(conversation_id),
                chat_id=str(chat.id),
                repo_url=repo_url,
                branch=branch,
                github_token=connection.access_token,
                auth_token=auth_token,
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(do_clone())
        finally:
            loop.close()

        if result.get("success"):
            logger.info(f"Cloned {result.get('full_name')} for conversation {conversation_id}")
            return Response(result)
        else:
            return Response(
                {"error": result.get("error", "Clone failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception:
        logger.exception("Error cloning repository")
        return Response(
            {"error": "Something went wrong. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ensure_repo(request: Request, conversation_id: str) -> Response:
    """Ensure the cloned repo exists in the sandbox, re-cloning if necessary.

    Called by the frontend before opening the IDE to ensure the workspace
    has a valid git repository (not just loose versioned files).

    After container recycle, the tmpfs workspace is lost. This endpoint:
    1. Checks if .git exists in the sandbox
    2. Re-clones from GitHub if missing (with branch fallback)
    3. Force-restores versioned files on top
    4. Reconciles git state (creates branch, stages, commits)
    """
    from conversations.models import Conversation

    try:
        Conversation.objects.get(id=conversation_id, user=request.user)
    except Conversation.DoesNotExist:
        return Response(
            {"error": "Conversation not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    auth_header = request.headers.get("Authorization", "")
    auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

    try:
        import asyncio
        from .services.clone import ensure_repo_in_sandbox

        async def do_ensure():
            return await ensure_repo_in_sandbox(
                user_id=str(request.user.id),
                conversation_id=str(conversation_id),
                auth_token=auth_token,
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(do_ensure())
        finally:
            loop.close()

        return Response(result)

    except Exception as e:
        logger.exception("Error ensuring repo in sandbox")
        return Response(
            {"error": f"Failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_implementation(request: Request) -> Response:
    """Start the implementation workflow for a GitHub issue.

    This endpoint:
    1. Creates a new conversation
    2. Clones the repository
    3. Creates an initial user message asking the LLM to plan the implementation

    POST body:
        - repo_full_name: GitHub repo (owner/repo format)
        - branch: Branch to work on
        - issue_number: GitHub issue number
        - issue_title: Issue title
        - issue_body: Issue description (optional)
        - issue_url: URL to the issue

    Returns:
        - conversation_id: ID of the created conversation
        - chat_id: ID of the first chat
        - message_id: ID of the initial message
    """
    from conversations.models import Conversation, Chat

    # Validate required fields
    repo_full_name = request.data.get("repo_full_name")
    issue_number = request.data.get("issue_number")
    issue_title = request.data.get("issue_title")

    if not all([repo_full_name, issue_number, issue_title]):
        return Response(
            {"error": "repo_full_name, issue_number, and issue_title are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    branch = request.data.get("branch", "main")
    issue_body = request.data.get("issue_body", "")
    issue_url = request.data.get("issue_url", "")

    # Check GitHub connection
    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected", "code": "github_not_connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # 1. Create conversation
        conversation = Conversation.objects.create(
            user=request.user,
            name=f"#{issue_number}: {issue_title[:50]}",
        )

        # 2. Create a chat in the conversation with all features enabled
        chat = Chat.objects.create(
            conversation=conversation,
            parameters={
                "enable_streaming": True,
                "enable_reasoning": True,
                "enable_brave_search": True,
                "enable_mcp_tools": True,
                "enable_file_tools": True,
                "enable_image_generation": True,
                "enable_video_generation": True,
                "enable_sparks": True,
                "enable_knowledge_base": True,
            }
        )

        # 3. Get auth token from request
        auth_header = request.headers.get("Authorization", "")
        auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

        # 4. Clone the repository
        import asyncio
        from .services.clone import clone_repository

        async def do_clone():
            return await clone_repository(
                user_id=str(request.user.id),
                conversation_id=str(conversation.id),
                chat_id=str(chat.id),
                repo_url=repo_full_name,
                branch=branch,
                github_token=connection.access_token,
                auth_token=auth_token,
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            clone_result = loop.run_until_complete(do_clone())
        finally:
            loop.close()

        if not clone_result.get("success"):
            # Cleanup on failure
            conversation.delete()
            return Response(
                {"error": clone_result.get("error", "Clone failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5. Build the suggested message content for the user to review and send.
        # task-29 H2: the issue title + body are attacker-controllable
        # (anyone with repo write access). Wrap them so injection
        # attempts in the body don't override the system prompt.
        from conversations.prompt_protection import wrap_untrusted_content

        safe_title = wrap_untrusted_content(
            issue_title or "",
            wrapper_tag="github_issue_title",
            source_label=f"GitHub issue #{issue_number} title",
        )
        message_parts = [
            f"I need you to implement GitHub issue #{issue_number}.\n",
            safe_title,
        ]
        if issue_body:
            safe_body = wrap_untrusted_content(
                issue_body,
                wrapper_tag="github_issue_body",
                source_label=f"GitHub issue #{issue_number} body",
            )
            message_parts.append(f"\n\n**Description:**\n{safe_body}")
        if issue_url:
            message_parts.append(f"\n\n**Issue URL:** {issue_url}")
        message_parts.append(f"\n\n**Repository:** {repo_full_name} (branch: {branch})")
        message_parts.append(
            "\n\nPlease use the coding agent to:\n"
            "1. Explore the codebase to understand its structure\n"
            "2. Create a detailed implementation plan for this issue\n"
            "3. Once the plan is ready, I'll review it before you proceed with implementation"
        )

        suggested_message = "".join(message_parts)

        logger.info(
            f"Started implementation workflow for issue #{issue_number} "
            f"in repo {repo_full_name}, conversation {conversation.id}"
        )

        return Response({
            "success": True,
            "conversation_id": str(conversation.id),
            "chat_id": str(chat.id),
            "suggested_message": suggested_message,
            "clone_result": {
                "full_name": clone_result.get("full_name"),
                "branch": clone_result.get("branch"),
                "head_commit_sha": clone_result.get("head_commit_sha"),
            },
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.exception("Error starting implementation workflow")
        return Response(
            {"error": f"Failed to start implementation: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== Agent Plan Views ====================


class AgentPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for agent plans."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter plans to current user's conversations."""
        queryset = AgentPlan.objects.filter(conversation__user=self.request.user)
        chat_id = self.request.query_params.get("chat_id")
        if chat_id:
            queryset = queryset.filter(chat_id=chat_id)
        else:
            repo_full_name = self.request.query_params.get("repo_full_name")
            if repo_full_name:
                queryset = queryset.filter(repo_full_name=repo_full_name)
            else:
                conversation_id = self.request.query_params.get("conversation_id")
                if conversation_id:
                    queryset = queryset.filter(conversation_id=conversation_id)
        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        """Use summary serializer for list, full serializer for detail."""
        if self.action == "list":
            return AgentPlanSummarySerializer
        return AgentPlanSerializer

    @action(detail=True, methods=["get"])
    def steps(self, request, pk=None):
        """Get steps for a plan."""
        plan = self.get_object()
        serializer = PlanStepSerializer(plan.steps.all(), many=True)
        return Response({"steps": serializer.data})

    @action(detail=False, methods=["get"])
    def importable(self, request):
        """List plans importable into a chat (same repo, different chat)."""
        from code_sessions.serializers import ImportablePlanSerializer

        chat_id = request.query_params.get("chat_id")
        repo_full_name = request.query_params.get("repo_full_name")
        if not chat_id or not repo_full_name:
            return Response(
                {"error": "chat_id and repo_full_name are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Exclude plans already imported into the target chat
        already_imported_ids = (
            AgentPlan.objects.filter(chat_id=chat_id)
            .exclude(source_plan__isnull=True)
            .values_list("source_plan_id", flat=True)
        )
        plans = (
            AgentPlan.objects.filter(
                conversation__user=request.user,
                repo_full_name=repo_full_name,
            )
            .exclude(chat_id=chat_id)
            .exclude(id__in=already_imported_ids)
            .select_related("conversation")
            .order_by("-created_at")
        )
        serializer = ImportablePlanSerializer(plans, many=True)
        return Response({"results": serializer.data})


def _get_plan_for_user(plan_id: str, user) -> AgentPlan:
    """Get plan ensuring it belongs to user's conversation (DRY helper)."""
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import PermissionDenied

    plan = get_object_or_404(AgentPlan, id=plan_id)
    if plan.conversation.user != user:
        raise PermissionDenied("Plan not found")
    return plan


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_plan_status(request: Request, plan_id: str) -> Response:
    """Update plan status."""
    plan = _get_plan_for_user(plan_id, request.user)
    new_status = request.data.get("status")
    if new_status and new_status in dict(AgentPlan.Status.choices):
        plan.status = new_status
        plan.save(update_fields=["status", "updated_at"])
        return Response(AgentPlanSerializer(plan).data)
    return Response({"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_plan_content(request: Request, plan_id: str) -> Response:
    """Update plan content (user-side editing).

    Accepts raw markdown, re-parses into steps, and updates the plan.
    """
    from code_sessions.services.plan_service import update_plan_from_content

    plan = _get_plan_for_user(plan_id, request.user)
    new_content = request.data.get("plan_content")
    if not new_content:
        return Response({"error": "plan_content is required"}, status=status.HTTP_400_BAD_REQUEST)

    plan = update_plan_from_content(plan, new_content)
    return Response(AgentPlanSerializer(plan).data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_step_status(request: Request, plan_id: str, step_id: str) -> Response:
    """Update a specific plan step's status."""
    plan = _get_plan_for_user(plan_id, request.user)
    step = plan.steps.filter(id=step_id).first()
    if not step:
        return Response({"error": "Step not found"}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get("status")
    if new_status and new_status in dict(PlanStep.Status.choices):
        step.status = new_status
        step.result_summary = request.data.get("result_summary", step.result_summary)
        step.save(update_fields=["status", "result_summary"])
        return Response(PlanStepSerializer(step).data)
    return Response({"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_plan_to_chat(request: Request) -> Response:
    """Import (copy) a plan from another chat into the target chat.

    POST body:
        - plan_id: UUID of the source plan
        - chat_id: UUID of the target chat
    """
    from conversations.models import Chat
    from code_sessions.services.plan_service import import_plan

    plan_id = request.data.get("plan_id")
    chat_id = request.data.get("chat_id")
    if not plan_id or not chat_id:
        return Response(
            {"error": "plan_id and chat_id are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate user owns the plan
    source_plan = get_object_or_404(AgentPlan, id=plan_id, conversation__user=request.user)

    # Validate user owns the chat and it's for the same repo
    target_chat = get_object_or_404(Chat, id=chat_id, conversation__user=request.user)

    new_plan = import_plan(source_plan, target_chat)
    return Response(AgentPlanSerializer(new_plan).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_plan(request: Request, plan_id: str) -> Response:
    """Delete a plan and its steps."""
    plan = _get_plan_for_user(plan_id, request.user)
    plan.steps.all().delete()
    plan.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ==================== Pull Request Views ====================


class CreatedPullRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for created pull requests."""

    permission_classes = [IsAuthenticated]
    serializer_class = CreatedPullRequestSerializer

    def get_queryset(self):
        """Filter PRs to current user's repos."""
        queryset = CreatedPullRequest.objects.filter(
            cloned_repo__conversation__user=self.request.user
        )
        repo_full_name = self.request.query_params.get("repo_full_name")
        if repo_full_name:
            queryset = queryset.filter(cloned_repo__full_name=repo_full_name)
        else:
            conversation_id = self.request.query_params.get("conversation_id")
            if conversation_id:
                queryset = queryset.filter(cloned_repo__conversation_id=conversation_id)
        return queryset.order_by("-created_at")


# ==================== Branch Commits & PR from Plan Views ====================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_branch_commits(request: Request, owner: str, repo: str) -> Response:
    """List commits on a branch via GitHub API."""
    branch = request.query_params.get("sha", "main")
    per_page = min(int(request.query_params.get("per_page", 20)), 100)

    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response(
            {"error": "GitHub account not connected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        import asyncio

        async def _fetch():
            async with GitHubService(connection.access_token) as github:
                return await github.list_commits(owner, repo, branch=branch, limit=per_page)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            commits = loop.run_until_complete(_fetch())
        finally:
            loop.close()

        return Response({"results": commits})

    except GitHubAPIError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_pr_from_plan(request: Request, plan_id: str) -> Response:
    """Create a GitHub PR from a plan's implementation branch."""
    plan = get_object_or_404(AgentPlan, id=plan_id, conversation__user=request.user)

    if not plan.implementation_branch:
        return Response({"error": "No implementation branch found"}, status=status.HTTP_400_BAD_REQUEST)
    if plan.status != AgentPlan.Status.COMPLETED:
        return Response({"error": "Plan must be completed first"}, status=status.HTTP_400_BAD_REQUEST)

    cloned_repo = ClonedRepository.objects.filter(conversation=plan.conversation).first()
    if not cloned_repo:
        return Response({"error": "No cloned repository"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        connection = GitHubConnection.objects.get(user=request.user)
    except GitHubConnection.DoesNotExist:
        return Response({"error": "GitHub account not connected"}, status=status.HTTP_400_BAD_REQUEST)

    owner, repo_name = cloned_repo.full_name.split("/")

    title = request.data.get("title", plan.title)
    body = request.data.get("body") or _build_pr_body(plan)
    draft = request.data.get("draft", False)

    try:
        import asyncio

        async def _create():
            async with GitHubService(connection.access_token) as github:
                return await github.create_pull_request(
                    owner, repo_name, title, body,
                    head=plan.implementation_branch,
                    base=cloned_repo.default_branch,
                    draft=draft,
                )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            pr_data = loop.run_until_complete(_create())
        finally:
            loop.close()

        pr_record = CreatedPullRequest.objects.create(
            plan=plan,
            cloned_repo=cloned_repo,
            pr_number=pr_data["number"],
            pr_url=pr_data["html_url"],
            pr_title=pr_data["title"],
            head_branch=plan.implementation_branch,
            base_branch=cloned_repo.default_branch,
        )

        return Response(CreatedPullRequestSerializer(pr_record).data, status=status.HTTP_201_CREATED)

    except GitHubAPIError as e:
        logger.error(f"GitHub API error creating PR from plan: {e}")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Error creating PR from plan")
        return Response({"error": f"Failed to create pull request: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _build_pr_body(plan):
    """Build PR description from plan."""
    parts = [f"## {plan.title}", ""]
    if plan.github_issue_number:
        parts.append(f"Closes #{plan.github_issue_number}")
        parts.append("")
    if plan.task_description:
        parts.extend(["## Task", "", plan.task_description, ""])
    parts.extend(["---", "*Created with Sterna*"])
    return "\n".join(parts)


# ==================== Sub-Agent Views ====================


class SubAgentViewSet(viewsets.ModelViewSet):
    """ViewSet for sub-agent CRUD."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = SubAgent.objects.filter(user=self.request.user)
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return SubAgentSummarySerializer
        if self.action in ("create", "update", "partial_update"):
            return SubAgentCreateSerializer
        return SubAgentSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_serializer = SubAgentSerializer(serializer.instance)
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        response_serializer = SubAgentSerializer(serializer.instance)
        return Response(response_serializer.data)

    @action(detail=True, methods=["get"])
    def export_md(self, request, pk=None):
        """Export agent as markdown."""
        agent = self.get_object()
        return Response({
            "markdown": agent.to_markdown(),
            "filename": f"{agent.name}.md",
        })

    @action(detail=False, methods=["post"])
    def import_md(self, request):
        """Import agent from markdown content."""
        content = request.data.get("content")
        if not content:
            return Response({"error": "content is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            agent = SubAgent.parse_from_markdown(content, user=request.user)
            agent.full_clean()
            agent.save()
            return Response(SubAgentSerializer(agent).data, status=status.HTTP_201_CREATED)
        except (ValueError, Exception) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def toggle_active(self, request, pk=None):
        """Toggle agent is_active status."""
        agent = self.get_object()
        agent.is_active = not agent.is_active
        agent.save(update_fields=["is_active", "updated_at"])
        return Response(SubAgentSerializer(agent).data)

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Generate agent config from natural language description."""
        description = (request.data.get("description") or "").strip()
        if not description:
            return Response(
                {"error": "description is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(description) > 2000:
            return Response(
                {"error": "description must be 2000 characters or less"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from asgiref.sync import async_to_sync
            from .agent_generator import generate_agent_from_description

            config = async_to_sync(generate_agent_from_description)(
                description, user=request.user
            )
            return Response(config)
        except Exception as e:
            logger.exception("Agent generation failed")
            return Response(
                {"error": f"Generation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"])
    def active_list(self, request):
        """Lightweight list of active agents for tool descriptions."""
        agents = SubAgent.objects.filter(user=request.user, is_active=True).values(
            "id", "name", "description", "model_tier"
        )
        return Response({"results": list(agents)})


# ==================== Coding Agent Progress Views ====================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def coding_agent_progress(request: Request) -> Response:
    """Get real-time progress of a running Coding Agent job.

    POST body:
        - chat_id: Chat ID for workspace scoping
        - job_id: Optional job ID (will find most recent job if not provided)

    Returns progress data including steps, files modified, etc.
    """
    chat_id = request.data.get("chat_id")
    job_id = request.data.get("job_id")  # Optional

    if not chat_id:
        return Response(
            {"error": "chat_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get auth token from request
    auth_header = request.headers.get("Authorization", "")
    auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

    try:
        import asyncio
        from llm.services.coding_agent_service import get_coding_agent_progress

        async def fetch_progress():
            return await get_coding_agent_progress(
                user_id=str(request.user.id),
                chat_id=str(chat_id),
                job_id=str(job_id) if job_id else None,
                auth_token=auth_token,
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            progress = loop.run_until_complete(fetch_progress())
        finally:
            loop.close()

        return Response(progress)

    except Exception as e:
        logger.exception("Error fetching coding agent progress")
        return Response(
            {"found": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def coding_agent_answer(request: Request) -> Response:
    """Submit an answer to a pending coding agent question.

    POST body:
        - chat_id: Chat ID for workspace scoping
        - answer: The user's answer text
    """
    chat_id = request.data.get("chat_id")
    answer = request.data.get("answer")

    if not chat_id or answer is None:
        return Response(
            {"error": "chat_id and answer are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    auth_header = request.headers.get("Authorization", "")
    auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

    try:
        import asyncio
        from llm.services.coding_agent_service import get_coding_agent_service

        service = get_coding_agent_service()

        async def send():
            return await service.send_answer(
                user_id=str(request.user.id),
                chat_id=str(chat_id),
                answer=str(answer),
                auth_token=auth_token,
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(send())
        finally:
            loop.close()

        return Response(result)

    except Exception as e:
        logger.exception("Error sending coding agent answer")
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
