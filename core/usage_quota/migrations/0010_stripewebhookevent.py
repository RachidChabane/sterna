"""Add StripeWebhookEvent table (task 13).

Forward: create table for idempotent webhook handling. PK = event.id
so duplicate deliveries collide at the DB level.

Reverse: drop table. Webhook delivery history is recoverable from
Stripe dashboard if needed, so a downgrade does not lose authoritative
data.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0009_subscription_period_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='StripeWebhookEvent',
            fields=[
                ('id', models.CharField(max_length=255, primary_key=True,
                                        serialize=False)),
                ('type', models.CharField(db_index=True, max_length=255)),
                ('payload', models.JSONField()),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('processed_status', models.CharField(
                    blank=True, null=True, db_index=True,
                    max_length=16,
                    choices=[('ok', 'OK'), ('error', 'Error'),
                             ('skipped', 'Skipped'),
                             ('processing', 'Processing')],
                )),
                ('error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Stripe Webhook Event',
                'verbose_name_plural': 'Stripe Webhook Events',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='stripewebhookevent',
            index=models.Index(fields=['type', 'processed_status'],
                               name='swh_type_status_idx'),
        ),
        migrations.AddIndex(
            model_name='stripewebhookevent',
            index=models.Index(fields=['processed_at'],
                               name='swh_processed_at_idx'),
        ),
    ]
