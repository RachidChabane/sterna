"""
Creates support_request table.
Reversible: reverse deletes the table and all support request data.
"""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                ("subject", models.CharField(max_length=255)),
                ("message", models.TextField()),
                ("context", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("in_progress", "In Progress"),
                            ("resolved", "Resolved"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to={"is_staff": True},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_support_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="support_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Support Request",
                "verbose_name_plural": "Support Requests",
                "ordering": ["-created_at"],
            },
        ),
    ]
