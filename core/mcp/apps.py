"""Django app configuration for MCP module."""

from django.apps import AppConfig


class McpConfig(AppConfig):
    """Configuration for the MCP Django app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "mcp"
    verbose_name = "Model Context Protocol"

    def ready(self):
        """Import signals and perform app initialization."""
        # Import signals here if needed in the future
        pass
