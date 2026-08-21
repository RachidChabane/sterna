"""Admin configuration for code_sessions app."""

from django.contrib import admin

from .models import CodeJob, CodeSession, GitHubConnection, JobLog, SubAgent, UserModelPreferences


@admin.register(GitHubConnection)
class GitHubConnectionAdmin(admin.ModelAdmin):
    """Admin for GitHub connections."""

    list_display = [
        "github_username",
        "user",
        "created_at",
        "updated_at",
    ]
    list_filter = ["created_at"]
    search_fields = ["github_username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CodeSession)
class CodeSessionAdmin(admin.ModelAdmin):
    """Admin for code sessions."""

    list_display = [
        "name",
        "user",
        "status",
        "github_repo_full_name",
        "model_id",
        "created_at",
    ]
    list_filter = ["status", "model_id", "created_at"]
    search_fields = ["name", "user__email", "github_repo_full_name"]
    readonly_fields = ["id", "created_at", "updated_at", "last_activity_at"]
    raw_id_fields = ["user"]


class JobLogInline(admin.TabularInline):
    """Inline admin for job logs."""

    model = JobLog
    extra = 0
    readonly_fields = ["level", "message", "created_at"]
    can_delete = False


@admin.register(CodeJob)
class CodeJobAdmin(admin.ModelAdmin):
    """Admin for code jobs."""

    list_display = [
        "id",
        "session",
        "status",
        "progress",
        "created_at",
        "completed_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["prompt", "session__name", "session__user__email"]
    readonly_fields = [
        "id",
        "celery_task_id",
        "sandbox_container_id",
        "created_at",
        "started_at",
        "completed_at",
    ]
    raw_id_fields = ["session"]
    inlines = [JobLogInline]


@admin.register(JobLog)
class JobLogAdmin(admin.ModelAdmin):
    """Admin for job logs."""

    list_display = ["id", "job", "level", "message", "created_at"]
    list_filter = ["level", "created_at"]
    search_fields = ["message"]
    readonly_fields = ["id", "job", "created_at"]


@admin.register(SubAgent)
class SubAgentAdmin(admin.ModelAdmin):
    """Admin for sub-agents."""

    list_display = ["name", "user", "model_tier", "is_active", "updated_at"]
    list_filter = ["is_active", "model_tier", "created_at"]
    search_fields = ["name", "user__email", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["user"]


@admin.register(UserModelPreferences)
class UserModelPreferencesAdmin(admin.ModelAdmin):
    """Admin for user model preferences."""

    list_display = ["user", "fast_model_id", "balanced_model_id", "powerful_model_id", "updated_at"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["user"]
