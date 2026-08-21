"""Add current_period_end + cancel_at_period_end to UserSubscription (task 12).

Forward: AddField on both columns. ``current_period_end`` is nullable
(free-plan users have no Stripe subscription). ``cancel_at_period_end``
defaults to False so existing rows pick up a sane value implicitly via
the DEFAULT clause.

Reverse: drop columns. Both fields are recoverable from Stripe via
``sync_from_session`` (task 12) or the eventual webhook handler
(task 13), so a downgrade does not lose data permanently.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0008_usage_log_billing_origin'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersubscription',
            name='current_period_end',
            field=models.BigIntegerField(
                null=True, blank=True,
                help_text=(
                    "Unix seconds when the current Stripe billing period "
                    "ends."
                ),
            ),
        ),
        migrations.AddField(
            model_name='usersubscription',
            name='cancel_at_period_end',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True iff the user has cancelled and the sub ends at "
                    "period end."
                ),
            ),
        ),
    ]
