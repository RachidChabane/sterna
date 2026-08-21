from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"

    def ready(self):
        """Register signals when app is ready."""
        # Import signals to register them
        from . import signals  # noqa: F401
