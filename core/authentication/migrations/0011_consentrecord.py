"""Add ConsentRecord for cookie consent / analytics opt-in audit.

Forward: creates ``auth_consent_record`` with a unique constraint on
``session_id`` and an index on ``(user, created_at)``.

Reverse: drops the table. Reverse is DESTRUCTIVE — all stored
consent decisions are lost. Only run the reverse to roll back the
schema wholesale; the banner will re-show for every visitor on next
page load (correct, since there is no remembered choice).
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0010_user_tos_accepted_at"),
        ("authentication", "0010_user_stripe_customer_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsentRecord",
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
                (
                    "session_id",
                    models.CharField(
                        db_index=True,
                        help_text="Client-minted UUIDv4 identifying the browser session",
                        max_length=255,
                    ),
                ),
                (
                    "categories",
                    models.JSONField(
                        default=dict,
                        help_text='Map of category → enabled. e.g. {"essential": true, "analytics": false, "marketing": false}',
                    ),
                ),
                (
                    "version",
                    models.CharField(
                        help_text="Cookie policy version the consent was given against",
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "ip_anonymized",
                    models.CharField(
                        blank=True,
                        help_text="IPv4 with last octet zeroed, or IPv6 with last 80 bits zeroed",
                        max_length=64,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Set when the visitor signs up or logs in; NULL for anonymous visitors",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consent_records",
                        to="authentication.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "consent record",
                "verbose_name_plural": "consent records",
                "db_table": "auth_consent_record",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="consentrecord",
            constraint=models.UniqueConstraint(
                fields=("session_id",),
                name="auth_consent_record_session_id_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="consentrecord",
            index=models.Index(
                fields=["user", "created_at"], name="auth_consen_user_id_b8e707_idx"
            ),
        ),
    ]
