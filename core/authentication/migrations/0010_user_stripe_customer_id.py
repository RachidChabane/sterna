"""Add User.stripe_customer_id (task 11).

Forward: AddField with nullable CharField. No data migration needed —
existing users get NULL and will be populated either lazily on first
authenticated Stripe-touching request, or by an ops backfill script.

Reverse: drops the column. Safe for staging rollback; in prod this
would lose the cus_… ↔ user.id mapping. Document the backfill plan
before rolling back in prod.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0009_update_video_model_choices_veo"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="stripe_customer_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Stripe Customer object ID (cus_…). Set asynchronously after signup.",
                max_length=255,
                null=True,
                verbose_name="Stripe customer ID",
            ),
        ),
    ]
