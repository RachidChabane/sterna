# Generated migration for adding performance stats fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('llm', '0004_add_first_seen_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelcatalog',
            name='latency_p50',
            field=models.IntegerField(
                blank=True,
                help_text='Median latency (time-to-first-token) in milliseconds',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='latency_p90',
            field=models.IntegerField(
                blank=True,
                help_text='90th percentile latency in milliseconds',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='throughput_p50',
            field=models.FloatField(
                blank=True,
                help_text='Median throughput in tokens per second',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='throughput_p90',
            field=models.FloatField(
                blank=True,
                help_text='90th percentile throughput in tokens per second',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='stats_updated_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When performance stats were last updated',
                null=True,
            ),
        ),
    ]
