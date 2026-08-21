"""App configuration for code_sessions."""

from django.apps import AppConfig


class CodeSessionsConfig(AppConfig):
    """Configuration for the code_sessions app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "code_sessions"
    verbose_name = "Code Sessions"

    def ready(self):
        """Import signals when app is ready."""
        pass
