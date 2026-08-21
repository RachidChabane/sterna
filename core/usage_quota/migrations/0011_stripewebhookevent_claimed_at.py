"""Add ``claimed_at`` to StripeWebhookEvent (crash-stuck claim recovery).

Forward: add the nullable timestamp column, then backfill it with
``created_at`` for rows currently stuck in 'processing' so the new
stale-claim CAS (claims older than PROCESSING_CLAIM_TTL become
claimable again) can recover them instead of leaving them stuck
forever.

Reverse: drop the column (backfill needs no undo — the values live
only in the dropped column).
"""

from django.db import migrations, models


def _backfill_processing_claims(apps, schema_editor):
    StripeWebhookEvent = apps.get_model('usage_quota', 'StripeWebhookEvent')
    for row in StripeWebhookEvent.objects.filter(
        processed_status='processing', claimed_at__isnull=True,
    ).iterator():
        row.claimed_at = row.created_at
        row.save(update_fields=['claimed_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0010_stripewebhookevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='stripewebhookevent',
            name='claimed_at',
            field=models.DateTimeField(
                blank=True, null=True,
                help_text=(
                    "When the current 'processing' claim was taken. "
                    "Claims older than PROCESSING_CLAIM_TTL are treated "
                    "as abandoned and become claimable again."
                ),
            ),
        ),
        migrations.RunPython(
            _backfill_processing_claims,
            migrations.RunPython.noop,
        ),
    ]
