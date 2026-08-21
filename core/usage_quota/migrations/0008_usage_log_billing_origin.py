"""Add billing_origin to UsageLog.

Forward: AddField with default='platform' implicitly fills all existing
rows with 'platform' via the DEFAULT clause on PostgreSQL (and SQLite).
No RunPython backfill needed — the field default IS the backfill.

Reverse: Django drops the column (reversible by AddField semantics).
Note: the reverse path will permanently delete the BYOK/platform split,
so downgrading after BYOK rows exist destroys analytics data.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0007_seed_tiers'),
    ]

    operations = [
        migrations.AddField(
            model_name='usagelog',
            name='billing_origin',
            field=models.CharField(
                max_length=16,
                choices=[('platform', 'Platform'), ('byok', 'BYOK')],
                default='platform',
                db_index=True,
                help_text=(
                    "Who pays for this usage: 'platform' (Sterna) or "
                    "'byok' (user-uploaded OpenRouter key). BYOK rows have "
                    "cost_usd=0 because the user's OpenRouter account is "
                    "billed directly."
                ),
            ),
        ),
        migrations.AddIndex(
            model_name='usagelog',
            index=models.Index(
                fields=['user', 'billing_origin', 'timestamp'],
                name='usage_user_billorg_ts_idx',
            ),
        ),
    ]
