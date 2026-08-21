"""Schema-only migration adding per-feature count limits + Stripe placeholders.

Adds 10 nullable IntegerField/CharField columns to SubscriptionPlan and 1
nullable CharField to UserSubscription. All fields are nullable so the
migration is non-blocking for existing rows; default values are populated
by migration 0007 (data migration).

[MEM: sqlite-test-infra-cascade] All fields are plain Django field types
(IntegerField/CharField), no PG-only operators, no pgvector, no RunSQL.
Runs identically on SQLite (test DB) and Postgres (staging/prod).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usage_quota", "0005_seed_service_pricing"),
    ]

    operations = [
        # --- SubscriptionPlan: per-feature count limits ---
        migrations.AddField(
            model_name="subscriptionplan",
            name="voice_room_sessions_weekly_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text="Max voice-room sessions per 7-day window. None = unlimited; 0 = feature disabled.",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="voice_room_minutes_per_session_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text="Max minutes per single voice-room session. None = unlimited.",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="code_session_weekly_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text=(
                    "Max code-session count per 7-day window. None = unlimited; 0 = feature disabled. "
                    "Distinct from code_session_weekly_limit_usd which is a $-budget (advisory until task 10)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="kb_storage_mb_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text="Total knowledge-base storage in MB. None = unlimited.",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="kb_docs_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text="Max documents in knowledge base. None = unlimited.",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="image_gen_weekly_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text="Max image generations per 7-day window. None = unlimited; 0 = feature disabled.",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="video_gen_seconds_weekly_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text="Max seconds of generated video per 7-day window. None = unlimited; 0 = feature disabled.",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="mcp_invocations_weekly_limit",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text="Max MCP tool invocations per 7-day window. None = unlimited; 0 = feature disabled.",
            ),
        ),
        # --- SubscriptionPlan: Stripe linkage placeholders (task 11 wires) ---
        migrations.AddField(
            model_name="subscriptionplan",
            name="stripe_price_id_monthly",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                help_text="Stripe price ID for monthly billing. Filled by task 11.",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="stripe_price_id_yearly",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                help_text="Stripe price ID for yearly billing. Filled by task 11.",
            ),
        ),
        # --- UserSubscription: Stripe linkage placeholder (task 11 wires) ---
        migrations.AddField(
            model_name="usersubscription",
            name="stripe_subscription_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=255,
                null=True,
                help_text="Stripe subscription ID (sub_…). Filled by task 11.",
            ),
        ),
    ]
