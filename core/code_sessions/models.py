"""Models for code sessions and jobs."""

import re
import uuid

import yaml
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from mcp.fields import EncryptedTextField


# ==================== Sub-Agent Constants ====================

VALID_AGENT_TOOLS = frozenset({
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "WebSearch", "WebFetch", "Task", "NotebookEdit",
})

MAX_SUB_AGENTS_PER_USER = 30

User = get_user_model()


class GitHubConnection(models.Model):
    """User's GitHub OAuth connection for code operations.

    Stores encrypted OAuth tokens for secure GitHub API access.
    Each user can have one GitHub connection.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="github_code_connection",
        help_text="User who owns this GitHub connection",
    )

    # OAuth tokens (encrypted at rest for security)
    access_token = EncryptedTextField(
        help_text="Encrypted GitHub OAuth access token"
    )
    refresh_token = EncryptedTextField(
        blank=True,
        default="",
        help_text="Encrypted OAuth refresh token (if available)",
    )
    token_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the access token expires",
    )

    # GitHub user info
    github_username = models.CharField(
        max_length=100,
        help_text="GitHub username",
    )
    github_user_id = models.BigIntegerField(
        help_text="GitHub user ID",
    )
    avatar_url = models.URLField(
        blank=True,
        help_text="GitHub avatar URL",
    )

    # Scope tracking
    scopes = models.JSONField(
        default=list,
        help_text="List of granted OAuth scopes",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "GitHub Connection"
        verbose_name_plural = "GitHub Connections"

    def __str__(self):
        return f"{self.github_username} ({self.user.email})"

    def is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if not self.token_expires_at:
            return False
        return timezone.now() >= self.token_expires_at


class CodeSession(models.Model):
    """A coding session with optional repository connection.

    Sessions track a user's coding work, optionally linked to a GitHub repository.
    Each session can have multiple jobs (coding tasks).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="code_sessions",
        help_text="User who owns this session",
    )

    # Session info
    name = models.CharField(
        max_length=255,
        help_text="Session name (auto-generated or custom)",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional session description",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        help_text="Current session status",
    )

    # Repository connection (optional - can work without GitHub)
    github_repo_full_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Full repository name: owner/repo",
    )
    github_repo_url = models.URLField(
        blank=True,
        help_text="GitHub repository URL",
    )
    github_branch = models.CharField(
        max_length=255,
        default="main",
        help_text="Target branch name",
    )
    repo_cloned = models.BooleanField(
        default=False,
        help_text="Whether the repository has been cloned to workspace",
    )

    # Model selection
    model_id = models.CharField(
        max_length=255,
        default="anthropic/claude-sonnet-4",
        help_text="Selected LLM model for this session",
    )

    # Session settings
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional session settings",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(
        auto_now=True,
        help_text="Last activity timestamp for sorting",
    )

    class Meta:
        ordering = ["-last_activity_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "-last_activity_at"]),
        ]
        verbose_name = "Code Session"
        verbose_name_plural = "Code Sessions"

    def __str__(self):
        return f"{self.name} ({self.user.email})"

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at"])


class CodeJob(models.Model):
    """A coding job/task within a session.

    Jobs represent individual coding requests that run as background tasks.
    They execute in isolated sandboxes and report progress via WebSocket.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUEUED = "queued", "Queued"
        CLONING = "cloning", "Cloning Repository"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    session = models.ForeignKey(
        CodeSession,
        on_delete=models.CASCADE,
        related_name="jobs",
        help_text="Parent session for this job",
    )

    # Job info
    prompt = models.TextField(
        help_text="User's coding request/prompt",
    )
    enable_reasoning = models.BooleanField(
        default=False,
        help_text="Whether to enable extended thinking/reasoning for this job",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current job status",
    )
    progress = models.IntegerField(
        default=0,
        help_text="Progress percentage (0-100)",
    )
    progress_message = models.CharField(
        max_length=500,
        blank=True,
        help_text="Current progress message for UI display",
    )

    # Execution details
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Celery task ID for this job",
    )
    sandbox_container_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Docker container ID for the sandbox",
    )

    # Results
    result = models.JSONField(
        null=True,
        blank=True,
        help_text="Job execution result data",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if job failed",
    )
    files_modified = models.JSONField(
        default=list,
        help_text="List of files modified during job execution",
    )

    # Conversation history for this job
    messages = models.JSONField(
        default=list,
        help_text="Message history (user, assistant, tool messages)",
    )

    # Steps for UI display (text, tool_executions)
    steps = models.JSONField(
        default=list,
        help_text="Execution steps for UI display (text, tool_executions)",
    )

    # PR metadata (generated by the LLM as its final step)
    pr_title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Pull request title (generated by assistant)",
    )
    pr_body = models.TextField(
        blank=True,
        help_text="Pull request body/description (generated by assistant)",
    )
    pr_ready = models.BooleanField(
        default=False,
        help_text="Whether the assistant has prepared PR metadata",
    )

    # Cost tracking
    total_tokens = models.IntegerField(
        default=0,
        help_text="Total tokens used",
    )
    prompt_tokens = models.IntegerField(
        default=0,
        help_text="Prompt tokens used",
    )
    completion_tokens = models.IntegerField(
        default=0,
        help_text="Completion tokens used",
    )
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Total cost in USD",
    )

    # Token optimization metrics (two-phase Scout/Editor architecture)
    scout_tokens = models.IntegerField(
        default=0,
        help_text="Tokens used by scout (cheap) model for exploration",
    )
    scout_cost = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Cost of scout phase in USD",
    )
    editor_tokens = models.IntegerField(
        default=0,
        help_text="Tokens used by editor model for modifications",
    )
    editor_cost = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Cost of editor phase in USD",
    )
    used_two_phase = models.BooleanField(
        default=False,
        help_text="Whether two-phase Scout/Editor architecture was used",
    )
    optimization_metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed optimization metrics (compression ratio, savings, etc.)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the job started execution",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the job completed",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "status"]),
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["celery_task_id"]),
        ]
        verbose_name = "Code Job"
        verbose_name_plural = "Code Jobs"

    def __str__(self):
        return f"Job {self.id} ({self.status})"

    @property
    def duration_seconds(self) -> float | None:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_running(self) -> bool:
        """Check if job is currently running."""
        return self.status in [
            self.Status.QUEUED,
            self.Status.CLONING,
            self.Status.RUNNING,
        ]

    def mark_started(self):
        """Mark job as started."""
        self.status = self.Status.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_completed(self, result: dict = None):
        """Mark job as completed."""
        from decimal import Decimal

        self.status = self.Status.COMPLETED
        self.progress = 100
        self.completed_at = timezone.now()
        if result:
            # Convert any Decimal values to float for JSON serialization
            def convert_decimals(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                elif isinstance(obj, dict):
                    return {k: convert_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_decimals(i) for i in obj]
                return obj

            self.result = convert_decimals(result)
        self.save(update_fields=["status", "progress", "completed_at", "result"])

    def mark_failed(self, error_message: str):
        """Mark job as failed."""
        self.status = self.Status.FAILED
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at"])

    def update_progress(self, progress: int, message: str = ""):
        """Update job progress."""
        self.progress = min(max(progress, 0), 100)
        self.progress_message = message
        self.save(update_fields=["progress", "progress_message"])

    def add_message(self, role: str, content: str, **kwargs):
        """Add a message to the conversation history."""
        message = {
            "role": role,
            "content": content,
            "timestamp": timezone.now().isoformat(),
            **kwargs,
        }
        self.messages.append(message)
        self.save(update_fields=["messages"])


class JobLog(models.Model):
    """Log entries for a code job.

    Stores detailed execution logs for debugging and audit trail.
    """

    class Level(models.TextChoices):
        DEBUG = "debug", "Debug"
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    job = models.ForeignKey(
        CodeJob,
        on_delete=models.CASCADE,
        related_name="logs",
        help_text="Parent job for this log entry",
    )

    level = models.CharField(
        max_length=20,
        choices=Level.choices,
        default=Level.INFO,
        help_text="Log level",
    )
    message = models.TextField(
        help_text="Log message",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional log metadata",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["job", "created_at"]),
            models.Index(fields=["job", "level"]),
        ]
        verbose_name = "Job Log"
        verbose_name_plural = "Job Logs"

    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"


class ClonedRepository(models.Model):
    """A GitHub repository cloned into a conversation's workspace.

    Links a conversation to a cloned GitHub repository for AI agents
    to explore, plan, and implement changes.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    conversation = models.OneToOneField(
        "conversations.Conversation",
        on_delete=models.CASCADE,
        related_name="cloned_repository",
        help_text="Conversation that owns this cloned repository",
    )

    # Repository info
    full_name = models.CharField(
        max_length=255,
        help_text="Full repository name: owner/repo",
    )
    clone_url = models.URLField(
        help_text="GitHub clone URL (https)",
    )
    default_branch = models.CharField(
        max_length=100,
        default="main",
        help_text="Default branch of the repository",
    )
    current_branch = models.CharField(
        max_length=100,
        default="main",
        help_text="Currently checked out branch",
    )
    workspace_path = models.CharField(
        max_length=500,
        help_text="Path to cloned repo in sandbox workspace",
    )

    # HEAD commit tracking
    head_commit_sha = models.CharField(
        max_length=40,
        blank=True,
        help_text="SHA of HEAD commit",
    )
    head_commit_message = models.CharField(
        max_length=500,
        blank=True,
        help_text="Message of HEAD commit",
    )

    cloned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cloned Repository"
        verbose_name_plural = "Cloned Repositories"
        indexes = [
            models.Index(fields=["full_name"]),
            models.Index(fields=["conversation"]),
        ]

    def __str__(self):
        return f"{self.full_name} @ {self.current_branch}"


class AgentPlan(models.Model):
    """An implementation plan created by a planning agent.

    Plans contain detailed steps for implementing a feature or fix,
    created by exploring the codebase and understanding the task.
    """

    class Status(models.TextChoices):
        CREATING = "creating", "Creating"
        READY = "ready", "Ready for Approval"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.CASCADE,
        related_name="agent_plans",
        help_text="Conversation this plan belongs to",
    )
    repo_full_name = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="GitHub repo full name (owner/repo) for cross-conversation persistence",
    )
    chat = models.ForeignKey(
        "conversations.Chat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_plans",
        help_text="Chat this plan belongs to",
    )
    source_plan = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="copies",
        help_text="Original plan this was imported from",
    )

    # Plan metadata
    title = models.CharField(
        max_length=255,
        help_text="Human-readable plan title",
    )
    slug = models.SlugField(
        max_length=100,
        help_text="URL-safe slug for plan file",
    )
    task_description = models.TextField(
        help_text="Original task description from user",
    )
    plan_content = models.TextField(
        help_text="Full markdown plan content",
    )

    # Progress tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATING,
        help_text="Current plan status",
    )
    current_step_index = models.IntegerField(
        default=0,
        help_text="Index of currently executing step",
    )
    total_steps = models.IntegerField(
        default=0,
        help_text="Total number of steps in plan",
    )

    # Job IDs for tracking agent executions
    planning_job_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Coding agent job ID for planning phase",
    )
    implementation_job_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Coding agent job ID for implementation phase",
    )
    implementation_branch = models.CharField(
        max_length=200,
        blank=True,
        help_text="Git branch created for implementation",
    )

    # GitHub issue linking
    github_issue_number = models.IntegerField(
        null=True,
        blank=True,
        help_text="GitHub issue number this plan addresses",
    )
    github_issue_url = models.URLField(
        blank=True,
        help_text="Full URL to the GitHub issue",
    )
    github_issue_title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Title of the GitHub issue",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["conversation", "status"]),
            models.Index(fields=["conversation", "-created_at"]),
            models.Index(fields=["chat", "-created_at"]),
            models.Index(fields=["chat", "repo_full_name"]),
        ]
        verbose_name = "Agent Plan"
        verbose_name_plural = "Agent Plans"

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def progress_percentage(self) -> int:
        """Calculate progress as percentage."""
        if self.total_steps == 0:
            return 0
        completed = self.steps.filter(status=PlanStep.Status.COMPLETED).count()
        return int((completed / self.total_steps) * 100)


class PlanStep(models.Model):
    """A single step within an implementation plan.

    Steps track the progress of plan execution with detailed
    information about files to modify and results.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan = models.ForeignKey(
        AgentPlan,
        on_delete=models.CASCADE,
        related_name="steps",
        help_text="Parent plan for this step",
    )

    # Step details
    step_number = models.IntegerField(
        help_text="Order of step in plan (1-indexed)",
    )
    title = models.CharField(
        max_length=255,
        help_text="Brief step title",
    )
    description = models.TextField(
        help_text="Detailed step description",
    )

    # Progress tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current step status",
    )

    # File tracking
    files_to_modify = models.JSONField(
        default=list,
        help_text="List of files planned to modify",
    )
    files_modified = models.JSONField(
        default=list,
        help_text="List of files actually modified",
    )

    # Results
    result_summary = models.TextField(
        blank=True,
        help_text="Summary of what was done in this step",
    )

    class Meta:
        ordering = ["plan", "step_number"]
        indexes = [
            models.Index(fields=["plan", "step_number"]),
        ]
        verbose_name = "Plan Step"
        verbose_name_plural = "Plan Steps"

    def __str__(self):
        return f"Step {self.step_number}: {self.title}"


class SubAgent(models.Model):
    """A custom sub-agent definition that users can deploy into coding agent sandboxes.

    Sub-agents are serialized as markdown files with YAML frontmatter, which the
    orchestrator rewrites into its harness's format and plants where it looks.
    """

    class PermissionMode(models.TextChoices):
        DEFAULT = "default", "Default"
        PLAN = "plan", "Plan Only (Read-Only)"
        AUTO_EDIT = "autoEdit", "Auto Edit"
        FULL_AUTO = "fullAuto", "Full Auto"

    class ModelTier(models.TextChoices):
        FAST = "fast", "Fast"
        BALANCED = "balanced", "Balanced"
        POWERFUL = "powerful", "Powerful"
        INHERIT = "inherit", "Inherit from Chat"

    _NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sub_agents",
        help_text="User who owns this sub-agent",
    )

    # Agent identity
    name = models.CharField(
        max_length=100,
        help_text="Slug-safe agent name (used as filename)",
    )
    description = models.TextField(
        blank=True,
        help_text="Short description of the agent's purpose",
    )

    # Model tier selection (resolves to concrete model via UserModelPreferences)
    model_tier = models.CharField(
        max_length=20,
        choices=ModelTier.choices,
        default=ModelTier.INHERIT,
        help_text="Model tier for this sub-agent (fast/balanced/powerful/inherit)",
    )

    # Agent configuration
    system_prompt = models.TextField(
        blank=True,
        max_length=50000,
        help_text="System prompt / instructions for the sub-agent",
    )
    tools = models.JSONField(
        default=list,
        help_text="Allowed tools (e.g. Read, Glob, Grep)",
    )
    disallowed_tools = models.JSONField(
        default=list,
        help_text="Explicitly disallowed tools",
    )
    max_turns = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Maximum agentic turns",
    )
    permission_mode = models.CharField(
        max_length=20,
        choices=PermissionMode.choices,
        default=PermissionMode.DEFAULT,
        help_text="Permission mode for the sub-agent",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this agent is deployed to sandboxes",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "name")]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "-updated_at"]),
        ]
        ordering = ["-updated_at"]
        verbose_name = "Sub Agent"
        verbose_name_plural = "Sub Agents"

    def __str__(self):
        return f"{self.name} ({self.user.email})"

    def clean(self):
        """Validate agent data."""
        # Validate name format
        if not self._NAME_RE.match(self.name):
            raise ValidationError({
                "name": "Name must start with a letter and contain only letters, digits, hyphens, or underscores."
            })

        # Validate tools against allowed set
        for tool in self.tools:
            if tool not in VALID_AGENT_TOOLS:
                raise ValidationError({"tools": f"Invalid tool: {tool}. Must be one of: {', '.join(sorted(VALID_AGENT_TOOLS))}"})
        for tool in self.disallowed_tools:
            if tool not in VALID_AGENT_TOOLS:
                raise ValidationError({"disallowed_tools": f"Invalid tool: {tool}. Must be one of: {', '.join(sorted(VALID_AGENT_TOOLS))}"})

        # Tools cannot be both allowed and disallowed
        overlap = set(self.tools) & set(self.disallowed_tools)
        if overlap:
            raise ValidationError({"tools": f"Tools cannot be both allowed and disallowed: {', '.join(sorted(overlap))}"})

        # Enforce per-user limit on create
        if not self.pk:
            count = SubAgent.objects.filter(user=self.user).count()
            if count >= MAX_SUB_AGENTS_PER_USER:
                raise ValidationError(f"Maximum of {MAX_SUB_AGENTS_PER_USER} sub-agents per user.")

    _TIER_TO_ALIAS = {
        "fast": "haiku",
        "balanced": "sonnet",
        "powerful": "opus",
        "inherit": "inherit",
    }

    def _map_model_to_claude_alias(self) -> str:
        """Map model tier to Claude CLI alias."""
        return self._TIER_TO_ALIAS.get(self.model_tier, "sonnet")

    def to_markdown(self) -> str:
        """Export as .md file with YAML frontmatter + system_prompt body."""
        frontmatter = {
            "name": self.name,
            "description": self.description,
        }
        # Only include model in frontmatter if it's a valid Claude CLI alias.
        # "inherit" means use the parent model, so omit model: to let the
        # CLI fall back to its own default model resolution.
        model_alias = self._map_model_to_claude_alias()
        if model_alias != "inherit":
            frontmatter["model"] = model_alias
        if self.tools:
            frontmatter["tools"] = list(self.tools)
        if self.disallowed_tools:
            frontmatter["disallowedTools"] = list(self.disallowed_tools)
        if self.max_turns != 10:
            frontmatter["maxTurns"] = self.max_turns
        if self.permission_mode != self.PermissionMode.DEFAULT:
            frontmatter["permissionMode"] = self.permission_mode

        yaml_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
        body = self.system_prompt or ""
        return f"---\n{yaml_str}\n---\n\n{body}\n"

    @classmethod
    def parse_from_markdown(cls, content: str, user=None) -> "SubAgent":
        """Import from .md file content. Returns unsaved instance."""
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Invalid agent markdown: missing YAML frontmatter delimiters")

        frontmatter = yaml.safe_load(parts[1])
        if not isinstance(frontmatter, dict):
            raise ValueError("Invalid YAML frontmatter")

        body = parts[2].strip()

        # Reverse-map model alias to tier
        model_alias = frontmatter.get("model", "sonnet")
        alias_to_tier = {
            "haiku": cls.ModelTier.FAST,
            "sonnet": cls.ModelTier.BALANCED,
            "opus": cls.ModelTier.POWERFUL,
        }

        agent = cls(
            user=user,
            name=frontmatter.get("name", "unnamed"),
            description=frontmatter.get("description", ""),
            system_prompt=body,
            tools=frontmatter.get("tools", []),
            disallowed_tools=frontmatter.get("disallowedTools", []),
            max_turns=frontmatter.get("maxTurns", 10),
            permission_mode=frontmatter.get("permissionMode", cls.PermissionMode.DEFAULT),
            model_tier=alias_to_tier.get(model_alias, cls.ModelTier.BALANCED),
        )

        return agent


class UserModelPreferences(models.Model):
    """Per-user model preferences for coding agent tiers.

    Maps abstract tiers (fast/balanced/powerful) to concrete OpenRouter model IDs.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="model_preferences",
        help_text="User who owns these preferences",
    )
    fast_model_id = models.CharField(
        max_length=255,
        default="",
        blank=True,
        help_text="OpenRouter model ID for the 'fast' tier (empty = latest haiku)",
    )
    balanced_model_id = models.CharField(
        max_length=255,
        default="",
        blank=True,
        help_text="OpenRouter model ID for the 'balanced' tier (empty = latest sonnet)",
    )
    powerful_model_id = models.CharField(
        max_length=255,
        default="",
        blank=True,
        help_text="OpenRouter model ID for the 'powerful' tier (empty = latest opus)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Model Preferences"
        verbose_name_plural = "User Model Preferences"

    def __str__(self):
        return f"Model prefs for {self.user.email}"

    def get_model_for_tier(self, tier: str) -> str:
        """Get the concrete model ID for a given tier.

        If the stored value is empty, dynamically resolves to the latest
        Anthropic model matching the tier keyword from the model catalog.
        """
        tier_map = {
            "fast": self.fast_model_id,
            "balanced": self.balanced_model_id,
            "powerful": self.powerful_model_id,
        }
        model_id = tier_map.get(tier, self.balanced_model_id)
        if model_id:
            return model_id
        return self._resolve_default_for_tier(tier)

    @staticmethod
    def _resolve_default_for_tier(tier: str) -> str:
        """Resolve the latest Anthropic model for a tier from the catalog."""
        from llm.models import ModelCatalog

        keyword_map = {"fast": "haiku", "balanced": "sonnet", "powerful": "opus"}
        keyword = keyword_map.get(tier, "sonnet")
        fallback_map = {
            "haiku": "anthropic/claude-haiku-4.5",
            "sonnet": "anthropic/claude-sonnet-4.5",
            "opus": "anthropic/claude-opus-4",
        }
        try:
            match = (
                ModelCatalog.objects.filter(model_id__startswith="anthropic/")
                .filter(model_id__contains=keyword)
                .order_by("-model_id")
                .values_list("model_id", flat=True)
                .first()
            )
            if match:
                return match
        except Exception:
            pass
        return fallback_map[keyword]

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create model preferences for a user."""
        prefs, _ = cls.objects.get_or_create(user=user)
        return prefs


class CreatedPullRequest(models.Model):
    """A pull request created from plan implementation.

    Tracks PRs created by the agent after completing a plan,
    linking back to the plan and repository.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan = models.ForeignKey(
        AgentPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pull_requests",
        help_text="Plan that created this PR (may be null)",
    )
    cloned_repo = models.ForeignKey(
        ClonedRepository,
        on_delete=models.CASCADE,
        related_name="pull_requests",
        help_text="Repository this PR was created in",
    )

    # PR info from GitHub
    pr_number = models.IntegerField(
        help_text="GitHub PR number",
    )
    pr_url = models.URLField(
        help_text="Full URL to the PR on GitHub",
    )
    pr_title = models.CharField(
        max_length=255,
        help_text="PR title",
    )

    # Branch info
    head_branch = models.CharField(
        max_length=100,
        help_text="Branch containing changes (head)",
    )
    base_branch = models.CharField(
        max_length=100,
        help_text="Target branch for merge (base)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["cloned_repo", "-created_at"]),
            models.Index(fields=["pr_number"]),
        ]
        verbose_name = "Created Pull Request"
        verbose_name_plural = "Created Pull Requests"

    def __str__(self):
        return f"PR #{self.pr_number}: {self.pr_title}"

