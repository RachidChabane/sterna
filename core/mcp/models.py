"""Django models for MCP integration."""

from django.contrib.auth import get_user_model
from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

from .fields import EncryptedJSONField, EncryptedTextField

User = get_user_model()


class MCPServer(models.Model):
    """Configuration for an MCP server connection.

    Each user can configure their own MCP servers to connect to.
    Supports both local (sandboxed npm packages) and remote (HTTP/WebSocket) servers.

    Preconfigured servers (is_preconfigured=True) have user=None and are
    available to all users as templates they can connect to.
    """

    class TransportType(models.TextChoices):
        """Available transport types for MCP connections."""

        WEBSOCKET = "websocket", "WebSocket"
        STDIO = "stdio", "Standard I/O"
        HTTP = "http", "HTTP/SSE (Remote)"
        SANDBOXED = "sandboxed", "Sandboxed NPM"

    class AuthType(models.TextChoices):
        """Authentication types for remote MCP servers."""

        NONE = "none", "No Auth"
        API_KEY = "api_key", "API Key"
        BEARER = "bearer", "Bearer Token"
        OAUTH = "oauth", "OAuth 2.0"

    class Category(models.TextChoices):
        """Categories for organizing MCP servers."""

        PRODUCTIVITY = "productivity", "Productivity & Collaboration"
        DEVELOPER = "developer", "Developer Tools"
        CLOUD = "cloud", "Cloud & Infrastructure"
        CRM = "crm", "CRM & Sales"
        FINANCE = "finance", "Finance & Payments"
        AI = "ai", "AI & Knowledge"
        DATA = "data", "Data & Analytics"
        COMMUNICATION = "communication", "Communication & Social"
        AUTOMATION = "automation", "Automation & Integration"
        DESIGN = "design", "Design & Creative"
        ECOMMERCE = "ecommerce", "E-commerce"
        UTILITIES = "utilities", "Utilities & Tools"
        OTHER = "other", "Other"

    # Ownership (null for preconfigured servers)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mcp_servers",
        null=True,
        blank=True,
        help_text="User who owns this server configuration (null for preconfigured servers)",
    )

    # Basic info
    name = models.CharField(
        max_length=200,
        help_text="Human-readable name for this server",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this server provides",
    )
    icon_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL for the server icon (for display in UI)",
    )
    icon_invert_in_dark_mode = models.BooleanField(
        default=False,
        help_text="Whether to invert the icon color in dark mode (for dark/black icons)",
    )
    docs_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL to documentation or source code for this MCP server",
    )
    is_preconfigured = models.BooleanField(
        default=False,
        help_text="Whether this is a system-wide preconfigured server (not user-created)",
    )
    is_official = models.BooleanField(
        default=True,
        help_text="Whether this is an official MCP server from the service provider (False = community/unofficial)",
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
        help_text="Category for grouping servers in the UI",
    )

    # Connection details
    transport_type = models.CharField(
        max_length=20,
        choices=TransportType.choices,
        default=TransportType.WEBSOCKET,
        help_text="Transport protocol to use",
    )

    # WebSocket connection
    url = models.CharField(
        max_length=500,
        blank=True,
        validators=[URLValidator(schemes=["ws", "wss"])],
        help_text="WebSocket URL (required for websocket transport)",
    )

    # Stdio connection (legacy - use npm_package instead)
    command = models.CharField(
        max_length=500,
        blank=True,
        help_text="Command to run for stdio transport (legacy, use npm_package instead)",
    )
    working_directory = models.CharField(
        max_length=500,
        blank=True,
        help_text="Working directory for stdio process",
    )

    # NPM package for sandboxed execution (NEW - preferred for stdio)
    npm_package = models.CharField(
        max_length=200,
        blank=True,
        help_text="NPM package name (e.g., '@modelcontextprotocol/server-github'). Required for stdio transport.",
    )

    # Authentication (encrypted at rest for security - GDPR/CCPA compliance)
    auth_config = EncryptedJSONField(
        default=dict,
        blank=True,
        help_text="Authentication configuration (API keys, tokens, etc.) - encrypted at rest",
    )

    # Environment variables for the MCP server (encrypted at rest)
    env_vars = EncryptedJSONField(
        default=dict,
        blank=True,
        help_text="Environment variables to pass to the MCP server (encrypted at rest). Use for API keys, tokens, etc.",
    )

    # Custom allowed domains for egress proxy
    allowed_domains = models.JSONField(
        default=list,
        blank=True,
        help_text="Custom domains to allow for network egress (in addition to defaults like npm registry)",
    )

    # Remote server configuration (for HTTP/SSE transport)
    remote_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL for remote MCP servers (HTTP/SSE transport)",
    )
    auth_type = models.CharField(
        max_length=20,
        choices=AuthType.choices,
        default=AuthType.NONE,
        help_text="Authentication type for remote servers",
    )
    auth_header_name = models.CharField(
        max_length=100,
        default="Authorization",
        help_text="HTTP header name for authentication (e.g., Authorization, X-API-Key)",
    )

    # OAuth 2.1 Dynamic Discovery fields
    oauth_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Cached OAuth server metadata from /.well-known/oauth-authorization-server",
    )
    oauth_client_id = models.CharField(
        max_length=500,
        blank=True,
        help_text="OAuth client ID (from dynamic registration or manual entry)",
    )
    oauth_client_secret = EncryptedTextField(
        blank=True,
        default='',
        help_text="OAuth client secret (encrypted at rest)",
    )
    oauth_access_token = EncryptedTextField(
        blank=True,
        default='',
        help_text="OAuth access token (encrypted at rest)",
    )
    oauth_refresh_token = EncryptedTextField(
        blank=True,
        default='',
        help_text="OAuth refresh token (encrypted at rest)",
    )
    oauth_token_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the OAuth access token expires",
    )
    oauth_scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="OAuth scopes granted during authorization",
    )
    # Temporary fields for OAuth flow (cleared after completion)
    oauth_state = models.CharField(
        max_length=100,
        blank=True,
        help_text="Temporary state parameter for OAuth flow (CSRF protection)",
    )
    oauth_pkce_verifier = EncryptedTextField(
        blank=True,
        default='',
        help_text="Temporary PKCE code verifier (encrypted at rest)",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this server is currently enabled",
    )
    last_connected = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful connection timestamp",
    )
    last_health_check = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last health check attempt timestamp",
    )
    connection_healthy = models.BooleanField(
        default=False,
        help_text="Whether the last health check was successful",
    )
    last_error = models.TextField(
        blank=True,
        help_text="Last connection error message",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        """String representation."""
        if self.user:
            return f"{self.name} ({self.user.email})"
        return f"{self.name} (preconfigured)"

    def clean(self):
        """Validate the model based on transport type."""
        from django.core.exceptions import ValidationError

        errors = {}

        if self.transport_type == self.TransportType.WEBSOCKET:
            if not self.url:
                errors['url'] = 'WebSocket URL is required for WebSocket transport'
        elif self.transport_type == self.TransportType.STDIO:
            if not self.npm_package and not self.command:
                errors['npm_package'] = 'NPM package or command is required for Stdio transport'

        # Validate npm_package format if provided
        if self.npm_package:
            import re
            # Basic npm package name validation (allows scoped packages)
            pattern = r'^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$'
            if not re.match(pattern, self.npm_package, re.IGNORECASE):
                errors['npm_package'] = 'Invalid NPM package name format'

        # Validate allowed_domains is a list of strings
        if self.allowed_domains:
            if not isinstance(self.allowed_domains, list):
                errors['allowed_domains'] = 'allowed_domains must be a list'
            else:
                for domain in self.allowed_domains:
                    if not isinstance(domain, str):
                        errors['allowed_domains'] = 'All domains must be strings'
                        break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Save the model after validation."""
        # Only run full_clean on create or explicit update
        # to avoid issues with partial updates
        if not kwargs.pop('skip_validation', False):
            try:
                self.full_clean()
            except Exception:
                # Allow save to proceed, validation errors will be caught by forms/serializers
                pass
        super().save(*args, **kwargs)

    def get_effective_npm_package(self):
        """Get the npm package to use, falling back to command if needed."""
        if self.npm_package:
            return self.npm_package
        if self.command and self.command.startswith('npx'):
            # Extract package from npx command: "npx -y @org/package" -> "@org/package"
            parts = self.command.split()
            for i, part in enumerate(parts):
                if part.startswith('@') or (i > 0 and parts[i-1] in ['-y', '--yes', 'npx']):
                    if not part.startswith('-'):
                        return part
        return self.command

    def get_effective_env_vars(self):
        """Get combined environment variables from both fields."""
        env = {}
        if self.auth_config and isinstance(self.auth_config, dict):
            # Legacy: env_vars stored in auth_config
            env.update(self.auth_config.get('env_vars', {}))
        if self.env_vars and isinstance(self.env_vars, dict):
            env.update(self.env_vars)
        return env

    def mark_connected(self):
        """Mark this server as successfully connected."""
        now = timezone.now()
        self.last_connected = now
        self.last_health_check = now
        self.connection_healthy = True
        self.last_error = ""
        self.save(update_fields=["last_connected", "last_health_check", "connection_healthy", "last_error"])

    def mark_error(self, error_message: str):
        """Mark this server as having a connection error."""
        self.last_health_check = timezone.now()
        self.connection_healthy = False
        self.last_error = error_message
        self.save(update_fields=["last_health_check", "connection_healthy", "last_error"])

    def is_connection_fresh(self, threshold_minutes=5):
        """Check if the connection status is fresh (checked recently).

        Args:
            threshold_minutes: How many minutes before status is considered stale

        Returns:
            bool: True if status was checked recently
        """
        if not self.last_health_check:
            return False
        from datetime import timedelta
        threshold = timezone.now() - timedelta(minutes=threshold_minutes)
        return self.last_health_check >= threshold

    @property
    def server_type(self) -> str:
        """Determine server type based on configuration.

        Returns:
            'local' - npm package running in sandbox container
            'remote_http' - HTTP/SSE remote server
            'remote_websocket' - WebSocket remote server
        """
        # If npm_package is set, it's a local sandboxed server
        if self.npm_package:
            return 'local'

        # Check remote_url first (new field)
        if self.remote_url:
            if self.remote_url.startswith(('ws://', 'wss://')):
                return 'remote_websocket'
            return 'remote_http'

        # Fall back to legacy url field (WebSocket)
        if self.url:
            return 'remote_websocket'

        # If only command is set (legacy stdio without npm), treat as local
        if self.command:
            return 'local'

        return 'unknown'

    @property
    def is_remote(self) -> bool:
        """Check if this is a remote server."""
        return self.server_type in ('remote_http', 'remote_websocket')

    @property
    def is_local(self) -> bool:
        """Check if this is a local sandboxed server."""
        return self.server_type == 'local'

    @property
    def requires_oauth(self) -> bool:
        """Check if this server requires OAuth authentication."""
        return self.auth_type == self.AuthType.OAUTH

    @property
    def has_valid_oauth_token(self) -> bool:
        """Check if server has a valid (non-expired) OAuth token."""
        if not self.oauth_access_token:
            return False
        if not self.oauth_token_expires_at:
            # No expiration set, assume valid
            return True
        from datetime import timedelta
        # Consider expired if less than 1 minute remaining
        buffer = timedelta(minutes=1)
        return timezone.now() + buffer < self.oauth_token_expires_at

    @property
    def oauth_needs_refresh(self) -> bool:
        """Check if OAuth token needs refresh (within 5 min of expiry)."""
        if not self.oauth_access_token or not self.oauth_token_expires_at:
            return False
        from datetime import timedelta
        buffer = timedelta(minutes=5)
        return timezone.now() + buffer >= self.oauth_token_expires_at

    @property
    def oauth_connection_status(self) -> str:
        """Get OAuth connection status for display.

        Returns:
            'not_configured' - OAuth not set up
            'pending' - Waiting for user to authorize
            'connected' - Has valid token
            'expired' - Token expired, needs refresh or re-auth
        """
        if self.auth_type != self.AuthType.OAUTH:
            return 'not_configured'
        if self.oauth_state:  # Has pending OAuth flow
            return 'pending'
        if self.oauth_access_token:
            if self.has_valid_oauth_token:
                return 'connected'
            return 'expired'
        return 'not_configured'

    def clear_oauth_tokens(self):
        """Clear all OAuth tokens (for disconnect/revoke)."""
        self.oauth_access_token = ''
        self.oauth_refresh_token = ''
        self.oauth_token_expires_at = None
        self.oauth_scopes = []
        self.oauth_state = ''
        self.oauth_pkce_verifier = ''
        self.save(update_fields=[
            'oauth_access_token', 'oauth_refresh_token',
            'oauth_token_expires_at', 'oauth_scopes',
            'oauth_state', 'oauth_pkce_verifier'
        ])

    def store_oauth_tokens(self, access_token: str, refresh_token: str = '',
                          expires_in: int = None, scopes: list = None):
        """Store OAuth tokens after successful authorization."""
        self.oauth_access_token = access_token
        if refresh_token:
            self.oauth_refresh_token = refresh_token
        if expires_in:
            from datetime import timedelta
            self.oauth_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        if scopes:
            self.oauth_scopes = scopes
        # Clear temporary flow fields
        self.oauth_state = ''
        self.oauth_pkce_verifier = ''
        self.save(update_fields=[
            'oauth_access_token', 'oauth_refresh_token',
            'oauth_token_expires_at', 'oauth_scopes',
            'oauth_state', 'oauth_pkce_verifier'
        ])


class MCPTool(models.Model):
    """A tool discovered from an MCP server.

    Tools are cached to avoid repeated discovery calls.
    The cache is refreshed periodically or when explicitly requested.
    """

    # Association
    server = models.ForeignKey(
        MCPServer,
        on_delete=models.CASCADE,
        related_name="tools",
        help_text="MCP server that provides this tool",
    )

    # Tool definition (from MCP protocol)
    name = models.CharField(
        max_length=200,
        help_text="Tool name (unique per server)",
    )
    description = models.TextField(
        help_text="What this tool does",
    )
    input_schema = models.JSONField(
        help_text="JSON Schema for tool inputs",
    )

    # Additional metadata from MCP
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional tool metadata from MCP server",
    )

    # Cache management
    discovered_at = models.DateTimeField(auto_now_add=True)
    last_refreshed = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        ordering = ["name"]
        unique_together = [["server", "name"]]
        indexes = [
            models.Index(fields=["server", "name"]),
        ]

    def __str__(self):
        """String representation."""
        return f"{self.name} ({self.server.name})"


class MCPToolApproval(models.Model):
    """User approval/rejection for tool usage.

    Implements the manual approval workflow for tool execution.
    Users can approve/reject specific tools, and approvals can be
    scoped to a single use or permanent.
    """

    class ApprovalStatus(models.TextChoices):
        """Approval status options."""

        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class ApprovalScope(models.TextChoices):
        """Scope of the approval."""

        ONCE = "once", "Single Use"
        SESSION = "session", "Current Session"
        PERMANENT = "permanent", "Always Allow"

    # Who and what
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mcp_approvals",
        help_text="User making the approval decision",
    )
    tool = models.ForeignKey(
        MCPTool,
        on_delete=models.CASCADE,
        related_name="approvals",
        help_text="Tool being approved/rejected",
    )

    # Context
    session_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Associated chat session ID",
    )
    proposed_arguments = models.JSONField(
        help_text="Arguments that would be passed to the tool",
    )

    # Decision
    status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        help_text="Approval status",
    )
    scope = models.CharField(
        max_length=20,
        choices=ApprovalScope.choices,
        default=ApprovalScope.ONCE,
        help_text="How long this approval is valid",
    )

    # Metadata
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the approval decision was made",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this approval expires (for session scope)",
    )

    class Meta:
        """Model metadata."""

        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["session_id", "status"]),
        ]

    def __str__(self):
        """String representation."""
        return f"{self.tool.name} - {self.status} ({self.user.email})"

    def approve(self, scope: ApprovalScope = ApprovalScope.ONCE):
        """Approve this tool usage."""
        self.status = self.ApprovalStatus.APPROVED
        self.scope = scope
        self.decided_at = timezone.now()

        # Set expiration for session scope (default 24 hours)
        if scope == self.ApprovalScope.SESSION:
            from datetime import timedelta

            self.expires_at = timezone.now() + timedelta(hours=24)

        self.save()

    def reject(self):
        """Reject this tool usage."""
        self.status = self.ApprovalStatus.REJECTED
        self.decided_at = timezone.now()
        self.save()

    def is_valid(self) -> bool:
        """Check if this approval is still valid."""
        if self.status != self.ApprovalStatus.APPROVED:
            return False

        if self.scope == self.ApprovalScope.ONCE:
            # Check if already used (will be marked in MCPToolExecution)
            return not self.executions.filter(completed_at__isnull=False).exists()

        if self.scope == self.ApprovalScope.SESSION and self.expires_at:
            return timezone.now() < self.expires_at

        return True  # Permanent approval


class MCPToolExecution(models.Model):
    """Record of a tool execution for audit and debugging.

    Tracks every tool call made through the MCP system, including
    inputs, outputs, timing, and any errors.
    """

    class ExecutionStatus(models.TextChoices):
        """Execution status options."""

        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        ERROR = "error", "Error"
        TIMEOUT = "timeout", "Timeout"
        CANCELLED = "cancelled", "Cancelled"

    # Association
    tool = models.ForeignKey(
        MCPTool,
        on_delete=models.CASCADE,
        related_name="executions",
        help_text="Tool that was executed",
    )
    approval = models.ForeignKey(
        MCPToolApproval,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executions",
        help_text="Associated approval (if required)",
    )
    session_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Associated chat session ID",
    )

    # Execution details
    arguments = models.JSONField(
        help_text="Arguments passed to the tool",
    )
    status = models.CharField(
        max_length=20,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.PENDING,
        help_text="Current execution status",
    )

    # Results
    result = models.JSONField(
        null=True,
        blank=True,
        help_text="Tool output (if successful)",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message (if failed)",
    )

    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When execution completed (success or failure)",
    )
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Execution duration in milliseconds",
    )

    class Meta:
        """Model metadata."""

        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["session_id", "status"]),
            models.Index(fields=["tool", "status"]),
        ]

    def __str__(self):
        """String representation."""
        return f"{self.tool.name} - {self.status} ({self.started_at})"

    def mark_running(self):
        """Mark execution as running."""
        self.status = self.ExecutionStatus.RUNNING
        self.save(update_fields=["status"])

    def mark_success(self, result: dict):
        """Mark execution as successful."""

        now = timezone.now()
        self.status = self.ExecutionStatus.SUCCESS
        self.result = result
        self.completed_at = now
        if self.started_at:
            self.duration_ms = int((now - self.started_at).total_seconds() * 1000)
        self.save()

    def mark_error(self, error_message: str):
        """Mark execution as failed."""

        now = timezone.now()
        self.status = self.ExecutionStatus.ERROR
        self.error_message = error_message
        self.completed_at = now
        if self.started_at:
            self.duration_ms = int((now - self.started_at).total_seconds() * 1000)
        self.save()

    def mark_timeout(self):
        """Mark execution as timed out."""

        now = timezone.now()
        self.status = self.ExecutionStatus.TIMEOUT
        self.error_message = "Execution timed out"
        self.completed_at = now
        if self.started_at:
            self.duration_ms = int((now - self.started_at).total_seconds() * 1000)
        self.save()

    def mark_cancelled(self):
        """Mark execution as cancelled."""

        now = timezone.now()
        self.status = self.ExecutionStatus.CANCELLED
        self.error_message = "Execution cancelled by user"
        self.completed_at = now
        if self.started_at:
            self.duration_ms = int((now - self.started_at).total_seconds() * 1000)
        self.save()


class MCPDiscoverySearch(models.Model):
    """User's AI discovery search history.

    Stores recent searches so users can quickly revisit past results
    without re-running the AI search.
    """

    # Who searched
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mcp_discovery_searches",
        help_text="User who performed the search",
    )

    # Search query
    query = models.CharField(
        max_length=500,
        help_text="The search query/description",
    )

    # Results (stored as JSON)
    preconfigured_results = models.JSONField(
        default=list,
        help_text="Matching preconfigured servers from our catalog",
    )
    external_results = models.JSONField(
        default=list,
        help_text="External servers discovered from web search",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Model metadata."""

        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        """String representation."""
        return f"{self.query[:50]} ({self.user.email})"

    @property
    def total_results(self) -> int:
        """Get total number of results."""
        return len(self.preconfigured_results) + len(self.external_results)


