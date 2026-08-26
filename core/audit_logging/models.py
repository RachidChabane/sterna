"""
Audit log models for tracking all significant actions.
"""

import uuid
from typing import TYPE_CHECKING, Optional
from django.conf import settings
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.db.models import JSONField

if TYPE_CHECKING:
    from authentication.models import User


class AuditLogManager(models.Manager):
    """Manager for AuditLog model with helper methods."""

    def log(
        self,
        action,
        user=None,
        resource=None,
        resource_type=None,
        resource_id=None,
        **extra_data,
    ):
        """Create a new audit log entry."""
        # Remove any fields that shouldn't go in extra_data
        fields_to_exclude = [
            "user_ip",
            "user_agent",
            "request_id",
            "session_id",
            "success",
            "duration_ms",
            "error_message",
        ]
        create_kwargs = {
            "action": action,
            "user": user,
            "resource_object": resource,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }

        # Move specific fields from extra_data to create_kwargs
        for field in fields_to_exclude:
            if field in extra_data:
                create_kwargs[field] = extra_data.pop(field)

        # Set extra_data
        create_kwargs["extra_data"] = extra_data.get("extra_data", extra_data)

        audit_log = self.create(**create_kwargs)
        return audit_log

    def get_for_user(self, user):
        """Get audit logs for a specific user."""
        return self.filter(user=user).order_by("-timestamp")

    def get_for_resource(self, resource):
        """Get audit logs for a specific resource."""
        content_type = ContentType.objects.get_for_model(resource)
        return self.filter(
            resource_type=content_type, resource_id=resource.pk
        ).order_by("-timestamp")


class AuditLog(models.Model):
    """
    Model for storing audit log entries.

    Tracks all significant actions in the system with:
    - Who performed the action (user)
    - When it was performed (timestamp)
    - What action was performed (action)
    - On what resource (resource via GenericForeignKey)
    - Additional details (extra_data)
    """

    # Action categories
    ACTION_CATEGORIES = {
        "AUTH": "Authentication",
        "PROJECT": "Project Management",
        "DATASET": "Dataset Operations",
        "EVALUATION": "Evaluations",
        "RUBRIC": "Rubrics",
        "USER": "User Management",
        "PERMISSION": "Permissions",
        "SYSTEM": "System Operations",
        "API": "API Access",
        "EXPORT": "Data Export",
        "IMPORT": "Data Import",
        "CONFIG": "Configuration",
    }

    # Common action types
    ACTION_TYPES = {
        # Authentication
        "AUTH_LOGIN": "User logged in",
        "AUTH_LOGOUT": "User logged out",
        "AUTH_TOKEN_REFRESH": "Token refreshed",
        "AUTH_PASSWORD_RESET": "Password reset requested",
        "AUTH_PASSWORD_CHANGED": "Password changed",
        "AUTH_EMAIL_VERIFIED": "Email verified",
        # CRUD operations
        "CREATE": "Created resource",
        "UPDATE": "Updated resource",
        "DELETE": "Deleted resource",
        "VIEW": "Viewed resource",
        # Project operations
        "PROJECT_MEMBER_ADDED": "Added project member",
        "PROJECT_MEMBER_REMOVED": "Removed project member",
        "PROJECT_ROLE_CHANGED": "Changed member role",
        "PROJECT_SETTINGS_UPDATED": "Updated project settings",
        # Dataset operations
        "DATASET_IMPORTED": "Dataset imported",
        "DATASET_EXPORTED": "Dataset exported",
        "DATASET_VERSION_CREATED": "Dataset version created",
        "DATASET_ROLLBACK": "Dataset rolled back",
        # Evaluation operations
        "RUN_STARTED": "Evaluation run started",
        "RUN_COMPLETED": "Evaluation run completed",
        "RUN_FAILED": "Evaluation run failed",
        "RUN_CANCELLED": "Evaluation run cancelled",
        # Permission operations
        "PERMISSION_GRANTED": "Permission granted",
        "PERMISSION_REVOKED": "Permission revoked",
        "PERMISSION_DELEGATED": "Permission delegated",
        # System operations
        "SYSTEM_BACKUP": "System backup performed",
        "SYSTEM_RESTORE": "System restore performed",
        "SYSTEM_CONFIG_CHANGED": "System configuration changed",
    }

    if TYPE_CHECKING:
        # Shadow attribute Django generates for the `user` ForeignKey;
        # not otherwise visible to mypy without the django-stubs plugin.
        user_id: Optional[uuid.UUID]

    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    # When
    timestamp: models.DateTimeField = models.DateTimeField(
        default=timezone.now, db_index=True
    )

    # Who
    user: "models.ForeignKey[Optional[User], Optional[User]]" = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    # User information snapshot (in case user is deleted)
    user_email: models.EmailField = models.EmailField(null=True, blank=True)
    user_ip: models.GenericIPAddressField = models.GenericIPAddressField(
        null=True, blank=True
    )
    user_agent: models.TextField = models.TextField(null=True, blank=True)

    # What
    action: models.CharField = models.CharField(max_length=100, db_index=True)
    action_category: models.CharField = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in ACTION_CATEGORIES.items()],
        null=True,
        blank=True,
        db_index=True,
    )

    # On what (generic relation to any model)
    resource_type: "models.ForeignKey[Optional[ContentType], Optional[ContentType]]" = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    resource_id: models.CharField = models.CharField(
        max_length=255, null=True, blank=True
    )
    resource_object = GenericForeignKey("resource_type", "resource_id")
    resource_str: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="String representation of the resource at time of action",
    )

    # Additional context
    extra_data = JSONField(default=dict, blank=True)

    # Request information
    request_id: models.CharField = models.CharField(
        max_length=100, null=True, blank=True, help_text="Request ID for correlation"
    )
    session_id: models.CharField = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Session ID for grouping related actions",
    )

    # Success/failure tracking
    success: models.BooleanField = models.BooleanField(default=True)
    error_message: models.TextField = models.TextField(null=True, blank=True)

    # Performance tracking
    duration_ms: models.IntegerField = models.IntegerField(
        null=True, blank=True, help_text="Duration of the action in milliseconds"
    )

    objects = AuditLogManager()

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["action_category", "-timestamp"]),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        user_str = self.user_email or (self.user.email if self.user else "Anonymous")
        resource_str = (
            self.resource_str or f"{self.resource_type}:{self.resource_id}"
            if self.resource_type
            else "N/A"
        )
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {user_str} - {self.action} on {resource_str}"

    def save(self, *args, **kwargs):
        """Override save to capture resource string representation and set category."""
        # Capture resource string representation
        if self.resource_object and not self.resource_str:
            try:
                self.resource_str = str(self.resource_object)[:255]
            except Exception:
                self.resource_str = f"{self.resource_type}:{self.resource_id}"

        # Auto-set category based on action prefix
        if not self.action_category and self.action:
            for category in self.ACTION_CATEGORIES.keys():
                if self.action.startswith(category + "_"):
                    self.action_category = category
                    break

        # Store user email snapshot
        if self.user and not self.user_email:
            self.user_email = self.user.email

        super().save(*args, **kwargs)


class AuditLogRetentionPolicy(models.Model):
    """
    Model for defining audit log retention policies.
    """

    RETENTION_UNITS = [
        ("days", "Days"),
        ("months", "Months"),
        ("years", "Years"),
    ]

    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    name: models.CharField = models.CharField(max_length=100, unique=True)
    description: models.TextField = models.TextField(blank=True)

    # Retention period
    retention_value: models.PositiveIntegerField = models.PositiveIntegerField(
        help_text="How long to keep audit logs"
    )
    retention_unit: models.CharField = models.CharField(
        max_length=10, choices=RETENTION_UNITS, default="days"
    )

    # What to apply this policy to
    action_category: models.CharField = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in AuditLog.ACTION_CATEGORIES.items()],
        null=True,
        blank=True,
        help_text="Apply to specific category, or null for all",
    )

    # Archive before deletion
    archive_before_deletion: models.BooleanField = models.BooleanField(
        default=True, help_text="Archive logs to cold storage before deletion"
    )

    is_active: models.BooleanField = models.BooleanField(default=True)

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Audit Log Retention Policy"
        verbose_name_plural = "Audit Log Retention Policies"

    def __str__(self):
        category = self.action_category or "All"
        return (
            f"{self.name} - {self.retention_value} {self.retention_unit} ({category})"
        )

    def get_retention_days(self):
        """Get retention period in days."""
        if self.retention_unit == "days":
            return self.retention_value
        elif self.retention_unit == "months":
            return self.retention_value * 30
        elif self.retention_unit == "years":
            return self.retention_value * 365
        return self.retention_value


class AuditLogArchive(models.Model):
    """
    Model for storing archived audit logs.

    Older logs are moved here based on retention policies.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    # Original audit log ID
    original_id: models.UUIDField = models.UUIDField(db_index=True)

    # Archived data (full JSON dump of original log)
    archived_data = JSONField()

    # Archive metadata
    archived_at: models.DateTimeField = models.DateTimeField(default=timezone.now)
    archived_by_policy: (
        "models.ForeignKey[Optional[AuditLogRetentionPolicy], "
        "Optional[AuditLogRetentionPolicy]]"
    ) = models.ForeignKey(
        AuditLogRetentionPolicy, on_delete=models.SET_NULL, null=True, blank=True
    )

    # Storage location (for external archives)
    storage_location: models.CharField = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="S3 key or other storage location",
    )

    class Meta:
        ordering = ["-archived_at"]
        indexes = [
            models.Index(fields=["original_id"]),
            models.Index(fields=["-archived_at"]),
        ]
        verbose_name = "Audit Log Archive"
        verbose_name_plural = "Audit Log Archives"

    def __str__(self):
        return f"Archive of {self.original_id} at {self.archived_at}"
