"""Usage Quota app configuration."""

from django.apps import AppConfig


class UsageQuotaConfig(AppConfig):
    """Configuration for the Usage & Quota app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'usage_quota'
    verbose_name = 'Usage & Quota Management'

    def ready(self):
        """App initialization - register signals if needed."""
        pass
