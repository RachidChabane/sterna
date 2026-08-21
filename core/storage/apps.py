from django.apps import AppConfig


class StorageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "storage"
    verbose_name = "Storage (R2 backups + restore)"
