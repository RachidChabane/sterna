"""Add ``stripe_event_created`` to UserSubscription (out-of-order guard).

Forward: add the nullable unix-seconds marker of the newest Stripe
subscription event applied to the row. Webhook handlers skip writes
from events older than this marker, so a late-delivered
``customer.subscription.created`` can no longer overwrite a newer
plan change.

Reverse: drop the column. Losing the marker only re-opens the
out-of-order window; no authoritative data is lost.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0011_stripewebhookevent_claimed_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersubscription',
            name='stripe_event_created',
            field=models.BigIntegerField(
                blank=True, null=True,
                help_text=(
                    "Unix seconds `created` of the newest Stripe "
                    "subscription event applied to this row. Webhook "
                    "handlers skip writes from events older than this "
                    "marker (out-of-order delivery guard)."
                ),
            ),
        ),
    ]
