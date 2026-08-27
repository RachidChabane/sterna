"""
Admin configuration for audit logging.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import AuditLog, AuditLogRetentionPolicy, AuditLogArchive


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog model."""

    list_display = [
        "timestamp",
        "user_display",
        "action",
        "action_category",
        "resource_link",
        "success_icon",
        "duration_ms",
    ]
    list_filter = [
        "timestamp",
        "action_category",
        "success",
    ]
    search_fields = [
        "user__email",
        "user_email",
        "action",
        "resource_str",
        "user_ip",
        "request_id",
        "session_id",
    ]
    readonly_fields = [
        "id",
        "timestamp",
        "user",
        "user_email",
        "user_ip",
        "user_agent",
        "action",
        "action_category",
        "resource_type",
        "resource_id",
        "resource_str",
        "extra_data",
        "request_id",
        "session_id",
        "success",
        "error_message",
        "duration_ms",
    ]
    date_hierarchy = "timestamp"
    ordering = ["-timestamp"]

    @admin.display(description="User")
    def user_display(self, obj):
        """Display user with email."""
        if obj.user:
            return f"{obj.user.email}"
        elif obj.user_email:
            return f"{obj.user_email} (deleted)"
        return "Anonymous"

    @admin.display(description="Resource")
    def resource_link(self, obj):
        """Display resource with admin link if available."""
        if obj.resource_str:
            return obj.resource_str
        elif obj.resource_type and obj.resource_id:
            # Try to generate admin link
            try:
                app_label = obj.resource_type.app_label
                model_name = obj.resource_type.model
                url = reverse(
                    f"admin:{app_label}_{model_name}_change", args=[obj.resource_id]
                )
                return format_html(
                    '<a href="{}">{}</a>', url, f"{model_name}:{obj.resource_id}"
                )
            except Exception:
                return f"{obj.resource_type}:{obj.resource_id}"
        return "-"

    @admin.display(description="Success")
    def success_icon(self, obj):
        """Display success/failure with icon."""
        if obj.success:
            return format_html('<span style="color: green;">✓</span>')
        else:
            return format_html('<span style="color: red;">✗</span>')

    def has_add_permission(self, request):
        """Prevent manual addition of audit logs."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent modification of audit logs."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete audit logs."""
        return request.user.is_superuser


@admin.register(AuditLogRetentionPolicy)
class AuditLogRetentionPolicyAdmin(admin.ModelAdmin):
    """Admin for AuditLogRetentionPolicy model."""

    list_display = [
        "name",
        "retention_display",
        "action_category",
        "archive_before_deletion",
        "is_active",
        "updated_at",
    ]
    list_filter = [
        "is_active",
        "archive_before_deletion",
        "action_category",
        "retention_unit",
    ]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at"]

    @admin.display(description="Retention Period")
    def retention_display(self, obj):
        """Display retention period."""
        return f"{obj.retention_value} {obj.retention_unit}"


@admin.register(AuditLogArchive)
class AuditLogArchiveAdmin(admin.ModelAdmin):
    """Admin for AuditLogArchive model."""

    list_display = [
        "original_id",
        "archived_at",
        "archived_by_policy",
        "storage_location",
    ]
    list_filter = [
        "archived_at",
        "archived_by_policy",
    ]
    search_fields = [
        "original_id",
        "storage_location",
    ]
    readonly_fields = [
        "id",
        "original_id",
        "archived_data",
        "archived_at",
        "archived_by_policy",
        "storage_location",
    ]
    date_hierarchy = "archived_at"
    ordering = ["-archived_at"]

    def has_add_permission(self, request):
        """Prevent manual addition of archives."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent modification of archives."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete archives."""
        return request.user.is_superuser
