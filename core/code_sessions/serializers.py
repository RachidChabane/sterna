"""Serializers for code sessions REST API."""

from rest_framework import serializers

from .models import (
    AgentPlan,
    ClonedRepository,
    CodeJob,
    CodeSession,
    CreatedPullRequest,
    GitHubConnection,
    JobLog,
    MAX_SUB_AGENTS_PER_USER,
    PlanStep,
    SubAgent,
    UserModelPreferences,
    VALID_AGENT_TOOLS,
)


class GitHubConnectionSerializer(serializers.ModelSerializer):
    """Serializer for GitHub connection status."""

    connected = serializers.SerializerMethodField()

    class Meta:
        model = GitHubConnection
        fields = [
            "connected",
            "github_username",
            "avatar_url",
            "scopes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_connected(self, obj) -> bool:
        """Always True if object exists."""
        return True


class GitHubRepoSerializer(serializers.Serializer):
    """Serializer for GitHub repository data."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    full_name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    private = serializers.BooleanField()
    html_url = serializers.URLField()
    clone_url = serializers.URLField()
    default_branch = serializers.CharField()
    language = serializers.CharField(allow_null=True)
    stargazers_count = serializers.IntegerField()
    updated_at = serializers.DateTimeField()
    pushed_at = serializers.DateTimeField()

    # Owner info
    owner = serializers.SerializerMethodField()

    def get_owner(self, obj) -> dict:
        """Get owner info."""
        owner = obj.get("owner", {})
        return {
            "login": owner.get("login"),
            "avatar_url": owner.get("avatar_url"),
        }


class GitHubBranchSerializer(serializers.Serializer):
    """Serializer for GitHub branch data."""

    name = serializers.CharField()
    protected = serializers.BooleanField(default=False)


class GitHubIssueSerializer(serializers.Serializer):
    """Serializer for GitHub issue data."""

    id = serializers.IntegerField()
    number = serializers.IntegerField()
    title = serializers.CharField()
    body = serializers.CharField(allow_null=True)
    state = serializers.CharField()
    html_url = serializers.URLField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    # Labels
    labels = serializers.SerializerMethodField()

    # User info
    user = serializers.SerializerMethodField()

    def get_labels(self, obj) -> list[dict]:
        """Get label info."""
        return [
            {"name": label.get("name"), "color": label.get("color")}
            for label in obj.get("labels", [])
        ]

    def get_user(self, obj) -> dict:
        """Get user info."""
        user = obj.get("user", {})
        return {
            "login": user.get("login"),
            "avatar_url": user.get("avatar_url"),
        }


class CodeSessionSerializer(serializers.ModelSerializer):
    """Serializer for code sessions."""

    jobs_count = serializers.SerializerMethodField()
    active_job = serializers.SerializerMethodField()

    class Meta:
        model = CodeSession
        fields = [
            "id",
            "name",
            "description",
            "status",
            "github_repo_full_name",
            "github_repo_url",
            "github_branch",
            "repo_cloned",
            "model_id",
            "settings",
            "created_at",
            "updated_at",
            "last_activity_at",
            "jobs_count",
            "active_job",
        ]
        read_only_fields = [
            "id",
            "repo_cloned",
            "created_at",
            "updated_at",
            "last_activity_at",
            "jobs_count",
            "active_job",
        ]

    def get_jobs_count(self, obj) -> int:
        """Get total number of jobs in session."""
        return obj.jobs.count()

    def get_active_job(self, obj) -> dict | None:
        """Get currently running job if any."""
        active_statuses = [
            CodeJob.Status.PENDING,
            CodeJob.Status.QUEUED,
            CodeJob.Status.CLONING,
            CodeJob.Status.RUNNING,
        ]
        active_job = obj.jobs.filter(status__in=active_statuses).first()
        if active_job:
            return CodeJobSummarySerializer(active_job).data
        return None


class CodeSessionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating code sessions."""

    class Meta:
        model = CodeSession
        fields = [
            "name",
            "description",
            "github_repo_full_name",
            "github_repo_url",
            "github_branch",
            "model_id",
            "settings",
        ]

    def create(self, validated_data):
        """Create session with current user."""
        validated_data["user"] = self.context["request"].user

        # Auto-generate name if not provided
        if not validated_data.get("name"):
            if validated_data.get("github_repo_full_name"):
                validated_data["name"] = validated_data["github_repo_full_name"]
            else:
                # Count user's sessions for naming
                user = validated_data["user"]
                count = CodeSession.objects.filter(user=user).count() + 1
                validated_data["name"] = f"Session {count}"

        return super().create(validated_data)


class CodeJobSummarySerializer(serializers.ModelSerializer):
    """Summary serializer for code jobs (used in lists)."""

    class Meta:
        model = CodeJob
        fields = [
            "id",
            "prompt",
            "status",
            "progress",
            "progress_message",
            "created_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields


class CodeJobSerializer(serializers.ModelSerializer):
    """Full serializer for code jobs."""

    duration_seconds = serializers.ReadOnlyField()
    session_name = serializers.CharField(source="session.name", read_only=True)

    class Meta:
        model = CodeJob
        fields = [
            "id",
            "session",
            "session_name",
            "prompt",
            "status",
            "progress",
            "progress_message",
            "result",
            "error_message",
            "files_modified",
            "messages",
            "steps",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
            "total_cost",
            # Token optimization metrics
            "scout_tokens",
            "scout_cost",
            "editor_tokens",
            "editor_cost",
            "used_two_phase",
            "optimization_metrics",
            "created_at",
            "started_at",
            "completed_at",
            "duration_seconds",
            # PR metadata (generated by assistant)
            "pr_title",
            "pr_body",
            "pr_ready",
        ]
        read_only_fields = [
            "id",
            "session_name",
            "status",
            "progress",
            "progress_message",
            "result",
            "error_message",
            "files_modified",
            "messages",
            "steps",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
            "total_cost",
            "scout_tokens",
            "scout_cost",
            "editor_tokens",
            "editor_cost",
            "used_two_phase",
            "optimization_metrics",
            "created_at",
            "started_at",
            "completed_at",
            "duration_seconds",
            "pr_title",
            "pr_body",
            "pr_ready",
        ]


class CodeJobCreateSerializer(serializers.Serializer):
    """Serializer for creating code jobs."""

    prompt = serializers.CharField(
        min_length=1,
        max_length=50000,
        help_text="The coding task/prompt",
    )
    enable_reasoning = serializers.BooleanField(
        default=False,
        required=False,
        help_text="Whether to enable extended thinking/reasoning",
    )

    def validate_prompt(self, value):
        """Validate prompt content."""
        if not value.strip():
            raise serializers.ValidationError("Prompt cannot be empty.")
        return value.strip()


class JobLogSerializer(serializers.ModelSerializer):
    """Serializer for job logs."""

    class Meta:
        model = JobLog
        fields = [
            "id",
            "level",
            "message",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


# ==================== GitHub OAuth Serializers ====================


class GitHubConnectSerializer(serializers.Serializer):
    """Serializer for initiating GitHub OAuth flow."""

    redirect_uri = serializers.URLField(
        required=False,
        help_text="Optional callback URL override",
    )


class GitHubCallbackSerializer(serializers.Serializer):
    """Serializer for GitHub OAuth callback."""

    code = serializers.CharField(
        help_text="Authorization code from GitHub",
    )
    state = serializers.CharField(
        help_text="CSRF state parameter",
    )


class GitHubStatusSerializer(serializers.Serializer):
    """Serializer for GitHub connection status response."""

    connected = serializers.BooleanField()
    username = serializers.CharField(required=False, allow_null=True)
    avatar_url = serializers.URLField(required=False, allow_null=True)
    scopes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )


# ==================== Cloned Repository Serializers ====================


class ClonedRepositorySerializer(serializers.ModelSerializer):
    """Serializer for cloned repository info."""

    class Meta:
        model = ClonedRepository
        fields = [
            "id",
            "full_name",
            "clone_url",
            "default_branch",
            "current_branch",
            "workspace_path",
            "head_commit_sha",
            "head_commit_message",
            "cloned_at",
        ]
        read_only_fields = fields


# ==================== Agent Plan Serializers ====================


def _compute_plan_progress(plan) -> dict:
    """Shared progress computation for plan serializers (DRY)."""
    completed = plan.steps.filter(status=PlanStep.Status.COMPLETED).count()
    total = plan.total_steps
    return {
        "completed": completed,
        "total": total,
        "percentage": int((completed / total * 100)) if total > 0 else 0,
    }


class PlanStepSerializer(serializers.ModelSerializer):
    """Serializer for plan steps."""

    class Meta:
        model = PlanStep
        fields = [
            "id",
            "step_number",
            "title",
            "description",
            "status",
            "files_to_modify",
            "files_modified",
            "result_summary",
        ]
        read_only_fields = fields


class AgentPlanSerializer(serializers.ModelSerializer):
    """Serializer for agent plans."""

    steps = PlanStepSerializer(many=True, read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = AgentPlan
        fields = [
            "id",
            "title",
            "slug",
            "task_description",
            "plan_content",
            "status",
            "current_step_index",
            "total_steps",
            "planning_job_id",
            "implementation_job_id",
            "github_issue_number",
            "github_issue_url",
            "github_issue_title",
            "implementation_branch",
            "chat_id",
            "source_plan_id",
            "created_at",
            "updated_at",
            "steps",
            "progress",
        ]
        read_only_fields = fields

    def get_progress(self, obj) -> dict:
        return _compute_plan_progress(obj)


class AgentPlanSummarySerializer(serializers.ModelSerializer):
    """Summary serializer for plan lists."""

    progress = serializers.SerializerMethodField()

    class Meta:
        model = AgentPlan
        fields = [
            "id",
            "title",
            "slug",
            "status",
            "current_step_index",
            "total_steps",
            "github_issue_number",
            "github_issue_title",
            "implementation_branch",
            "chat_id",
            "source_plan_id",
            "created_at",
            "progress",
        ]
        read_only_fields = fields

    def get_progress(self, obj) -> dict:
        return _compute_plan_progress(obj)


class ImportablePlanSerializer(AgentPlanSummarySerializer):
    """Extended summary for the import modal — adds conversation context."""

    conversation_name = serializers.CharField(source="conversation.name", read_only=True)
    task_description = serializers.CharField(read_only=True)

    class Meta(AgentPlanSummarySerializer.Meta):
        fields = AgentPlanSummarySerializer.Meta.fields + [
            "conversation_name",
            "task_description",
        ]
        read_only_fields = fields


# ==================== Sub-Agent Serializers ====================


_NAME_RE = __import__("re").compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


class SubAgentSerializer(serializers.ModelSerializer):
    """Full detail serializer for sub-agents."""

    class Meta:
        model = SubAgent
        fields = [
            "id",
            "name",
            "description",
            "model_tier",
            "system_prompt",
            "tools",
            "disallowed_tools",
            "max_turns",
            "permission_mode",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubAgentSummarySerializer(serializers.ModelSerializer):
    """Summary serializer for sub-agent lists."""

    class Meta:
        model = SubAgent
        fields = [
            "id",
            "name",
            "description",
            "model_tier",
            "is_active",
            "updated_at",
        ]
        read_only_fields = fields


class SubAgentCreateSerializer(serializers.ModelSerializer):
    """Create/update serializer with validation."""

    class Meta:
        model = SubAgent
        fields = [
            "name",
            "description",
            "model_tier",
            "system_prompt",
            "tools",
            "disallowed_tools",
            "max_turns",
            "permission_mode",
            "is_active",
        ]

    def validate_name(self, value):
        if not _NAME_RE.match(value):
            raise serializers.ValidationError(
                "Name must start with a letter and contain only letters, digits, hyphens, or underscores."
            )
        return value

    def validate_tools(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list.")
        for tool in value:
            if tool not in VALID_AGENT_TOOLS:
                raise serializers.ValidationError(
                    f"Invalid tool: {tool}. Must be one of: {', '.join(sorted(VALID_AGENT_TOOLS))}"
                )
        return value

    def validate_disallowed_tools(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list.")
        for tool in value:
            if tool not in VALID_AGENT_TOOLS:
                raise serializers.ValidationError(
                    f"Invalid tool: {tool}. Must be one of: {', '.join(sorted(VALID_AGENT_TOOLS))}"
                )
        return value

    def validate_system_prompt(self, value):
        if len(value) > 50000:
            raise serializers.ValidationError("System prompt must not exceed 50,000 characters.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if request and not self.instance:
            count = SubAgent.objects.filter(user=request.user).count()
            if count >= MAX_SUB_AGENTS_PER_USER:
                raise serializers.ValidationError(
                    f"Maximum of {MAX_SUB_AGENTS_PER_USER} sub-agents per user."
                )

        # Tools cannot be both allowed and disallowed
        tools = attrs.get("tools", [])
        disallowed_tools = attrs.get("disallowed_tools", [])
        overlap = set(tools) & set(disallowed_tools)
        if overlap:
            raise serializers.ValidationError(
                f"Tools cannot be both allowed and disallowed: {', '.join(sorted(overlap))}"
            )

        return attrs


# ==================== User Model Preferences Serializers ====================


class UserModelPreferencesSerializer(serializers.ModelSerializer):
    """Serializer for user coding agent model preferences."""

    class Meta:
        model = UserModelPreferences
        fields = [
            "fast_model_id",
            "balanced_model_id",
            "powerful_model_id",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


# ==================== Pull Request Serializers ====================


class CreatedPullRequestSerializer(serializers.ModelSerializer):
    """Serializer for created pull requests."""

    plan_title = serializers.CharField(source="plan.title", read_only=True, allow_null=True)
    repo_full_name = serializers.CharField(source="cloned_repo.full_name", read_only=True)

    class Meta:
        model = CreatedPullRequest
        fields = [
            "id",
            "pr_number",
            "pr_url",
            "pr_title",
            "head_branch",
            "base_branch",
            "created_at",
            "plan_title",
            "repo_full_name",
        ]
        read_only_fields = fields

