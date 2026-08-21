"""Django admin configuration for MCP models."""

from django.contrib import admin
from django.utils.html import format_html

from .models import MCPServer, MCPTool, MCPToolApproval, MCPToolExecution


@admin.register(MCPServer)
class MCPServerAdmin(admin.ModelAdmin):
    """Admin interface for MCP servers."""

    list_display = [
        "name",
        "user",
        "transport_type",
        "is_active",
        "connection_status",
        "created_at",
    ]
    list_filter = ["transport_type", "is_active", "created_at"]
    search_fields = ["name", "description", "user__email"]
    readonly_fields = ["created_at", "updated_at", "last_connected", "last_error"]
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("user", "name", "description"),
            },
        ),
        (
            "Connection",
            {
                "fields": (
                    "transport_type",
                    "url",
                    "command",
                    "working_directory",
                    "auth_config",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                    "last_connected",
                    "last_error",
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    def connection_status(self, obj):
        """Display connection status with color coding."""
        if not obj.is_active:
            return format_html('<span style="color: gray;">Inactive</span>')
        if obj.last_connected:
            return format_html('<span style="color: green;">Connected</span>')
        if obj.last_error:
            return format_html('<span style="color: red;">Error</span>')
        return format_html('<span style="color: orange;">Never Connected</span>')

    connection_status.short_description = "Status"


@admin.register(MCPTool)
class MCPToolAdmin(admin.ModelAdmin):
    """Admin interface for MCP tools."""

    list_display = ["name", "server", "discovered_at", "last_refreshed"]
    list_filter = ["server", "discovered_at"]
    search_fields = ["name", "description", "server__name"]
    readonly_fields = ["discovered_at", "last_refreshed"]
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("server", "name", "description"),
            },
        ),
        (
            "Schema",
            {
                "fields": ("input_schema", "metadata"),
            },
        ),
        (
            "Cache",
            {
                "fields": ("discovered_at", "last_refreshed"),
            },
        ),
    )


@admin.register(MCPToolApproval)
class MCPToolApprovalAdmin(admin.ModelAdmin):
    """Admin interface for tool approvals."""

    list_display = [
        "tool",
        "user",
        "status",
        "scope",
        "requested_at",
        "decided_at",
        "is_valid_status",
    ]
    list_filter = ["status", "scope", "requested_at"]
    search_fields = ["tool__name", "user__email", "session_id"]
    readonly_fields = ["requested_at", "decided_at"]
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("user", "tool", "session_id"),
            },
        ),
        (
            "Request",
            {
                "fields": ("proposed_arguments", "requested_at"),
            },
        ),
        (
            "Decision",
            {
                "fields": ("status", "scope", "decided_at", "expires_at"),
            },
        ),
    )

    def is_valid_status(self, obj):
        """Display whether approval is currently valid."""
        if obj.is_valid():
            return format_html('<span style="color: green;">Valid</span>')
        return format_html('<span style="color: red;">Invalid</span>')

    is_valid_status.short_description = "Valid"


@admin.register(MCPToolExecution)
class MCPToolExecutionAdmin(admin.ModelAdmin):
    """Admin interface for tool executions."""

    list_display = [
        "tool",
        "status",
        "started_at",
        "duration_display",
        "session_id",
    ]
    list_filter = ["status", "started_at"]
    search_fields = ["tool__name", "session_id"]
    readonly_fields = [
        "started_at",
        "completed_at",
        "duration_ms",
        "duration_display",
    ]
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("tool", "approval", "session_id"),
            },
        ),
        (
            "Execution",
            {
                "fields": ("arguments", "status"),
            },
        ),
        (
            "Results",
            {
                "fields": ("result", "error_message"),
            },
        ),
        (
            "Timing",
            {
                "fields": (
                    "started_at",
                    "completed_at",
                    "duration_ms",
                    "duration_display",
                ),
            },
        ),
    )

    def duration_display(self, obj):
        """Display duration in human-readable format."""
        if obj.duration_ms is None:
            return "-"
        if obj.duration_ms < 1000:
            return f"{obj.duration_ms}ms"
        return f"{obj.duration_ms / 1000:.2f}s"

    duration_display.short_description = "Duration"
