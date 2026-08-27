from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"

    def ready(self):
        """Register signals and attach OpenAPI schema annotations."""
        # Import signals to register them
        from . import signals  # noqa: F401
        from .openapi_schema import apply_auth_schema

        apply_auth_schema()
