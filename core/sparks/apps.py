from django.apps import AppConfig


class SparksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sparks'
    verbose_name = 'Sparks - Interactive Components'

    def ready(self):
        self._register_spark_serializer()
        self._cleanup_stale_deployments()

    def _register_spark_serializer(self):
        """Nest spark data under conversation messages/chats.

        Sparks owns this dependency: conversations exposes the
        registration point and never imports from sparks itself.
        """
        from conversations.serializers import register_spark_serializer
        from .serializers import MessageSparkSerializer

        register_spark_serializer(MessageSparkSerializer)

    def _cleanup_stale_deployments(self):
        """Mark stale in-progress deployments as failed on startup."""
        from django.db import connection

        try:
            if 'sparks_sparkdeployment' not in connection.introspection.table_names():
                return
        except Exception:
            return

        try:
            import datetime
            from django.db.models import Q
            from django.utils import timezone
            from .models import SparkDeployment

            cutoff = timezone.now() - datetime.timedelta(minutes=10)
            count = SparkDeployment.objects.filter(
                Q(status__in=['pending', 'deploying']),
                updated_at__lt=cutoff,
            ).update(
                status='failed',
                error_message='Deployment interrupted by server restart',
            )
            if count:
                import logging
                logging.getLogger(__name__).info(
                    f"Cleaned up {count} stale spark deployment(s)"
                )
        except Exception:
            pass
