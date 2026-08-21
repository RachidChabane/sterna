"""URL routing for code sessions API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

# Create router for viewsets
router = DefaultRouter()
router.register(r"sessions", views.CodeSessionViewSet, basename="code-session")
router.register(r"jobs", views.CodeJobViewSet, basename="code-job")
router.register(r"plans", views.AgentPlanViewSet, basename="agent-plan")
router.register(r"pull-requests", views.CreatedPullRequestViewSet, basename="created-pull-request")
router.register(r"sub-agents", views.SubAgentViewSet, basename="sub-agent")

urlpatterns = [
    # Plan import (must be before router to avoid "import" being matched as a plan PK)
    path(
        "plans/import/",
        views.import_plan_to_chat,
        name="import-plan-to-chat",
    ),
    # Router URLs (sessions, jobs, plans, PRs CRUD)
    path("", include(router.urls)),
    # GitHub OAuth endpoints
    path("github/connect/", views.github_connect, name="github-connect"),
    path("github/callback/", views.github_callback, name="github-callback"),
    path("github/status/", views.github_status, name="github-status"),
    path("github/disconnect/", views.github_disconnect, name="github-disconnect"),
    path("github/repos/", views.github_repos, name="github-repos"),
    path(
        "github/repos/<str:owner>/<str:repo>/branches/",
        views.github_branches,
        name="github-branches",
    ),
    path(
        "github/repos/<str:owner>/<str:repo>/issues/",
        views.github_issues,
        name="github-issues",
    ),
    path(
        "github/repos/<str:owner>/<str:repo>/commits/",
        views.github_branch_commits,
        name="github-branch-commits",
    ),
    # Session Git operations (diff, commits)
    path(
        "sessions/<str:session_id>/git/diff/",
        views.session_git_diff,
        name="session-git-diff",
    ),
    path(
        "sessions/<str:session_id>/git/commits/",
        views.session_git_commits,
        name="session-git-commits",
    ),
    # Conversation repo status and clone
    path(
        "conversations/<str:conversation_id>/repo/",
        views.conversation_repo_status,
        name="conversation-repo-status",
    ),
    path(
        "conversations/<str:conversation_id>/clone/",
        views.clone_repo,
        name="conversation-clone-repo",
    ),
    path(
        "conversations/<str:conversation_id>/ensure-repo/",
        views.ensure_repo,
        name="conversation-ensure-repo",
    ),
    # Implementation workflow
    path(
        "start-implementation/",
        views.start_implementation,
        name="start-implementation",
    ),
    # Coding agent progress
    path(
        "coding-agent/progress/",
        views.coding_agent_progress,
        name="coding-agent-progress",
    ),
    # Coding agent answer (for ask_user MCP tool)
    path(
        "coding-agent/answer/",
        views.coding_agent_answer,
        name="coding-agent-answer",
    ),
    # Plan management
    path(
        "plans/<str:plan_id>/status/",
        views.update_plan_status,
        name="update-plan-status",
    ),
    path(
        "plans/<str:plan_id>/content/",
        views.update_plan_content,
        name="update-plan-content",
    ),
    path(
        "plans/<str:plan_id>/steps/<str:step_id>/status/",
        views.update_step_status,
        name="update-step-status",
    ),
    path(
        "plans/<str:plan_id>/delete/",
        views.delete_plan,
        name="delete-plan",
    ),
    path(
        "plans/<str:plan_id>/create-pr/",
        views.create_pr_from_plan,
        name="create-pr-from-plan",
    ),
]
