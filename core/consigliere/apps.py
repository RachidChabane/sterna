"""
Django app configuration for Consigliere module.
"""

from django.apps import AppConfig


class ConsigliereConfig(AppConfig):
    """Configuration for Consigliere app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "consigliere"
    verbose_name = "Consigliere AI Advisor"

    def ready(self):
        """
        Perform initialization when Django starts.
        """
        # Import signals or perform startup tasks here if needed
        pass
