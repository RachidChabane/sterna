# Generated migration for token optimization metrics

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add optimization metrics fields to CodeJob model.

    These fields support the two-phase Scout/Editor architecture:
    - scout_tokens/cost: Metrics for cheap model exploration phase
    - editor_tokens/cost: Metrics for expensive model editing phase
    - used_two_phase: Whether optimization was used
    - optimization_metrics: Detailed JSON metrics
    """

    dependencies = [
        ("code_sessions", "0004_add_enable_reasoning_to_codejob"),
    ]

    operations = [
        migrations.AddField(
            model_name="codejob",
            name="scout_tokens",
            field=models.IntegerField(
                default=0,
                help_text="Tokens used by scout (cheap) model for exploration",
            ),
        ),
        migrations.AddField(
            model_name="codejob",
            name="scout_cost",
            field=models.DecimalField(
                decimal_places=6,
                default=0,
                help_text="Cost of scout phase in USD",
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name="codejob",
            name="editor_tokens",
            field=models.IntegerField(
                default=0,
                help_text="Tokens used by editor model for modifications",
            ),
        ),
        migrations.AddField(
            model_name="codejob",
            name="editor_cost",
            field=models.DecimalField(
                decimal_places=6,
                default=0,
                help_text="Cost of editor phase in USD",
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name="codejob",
            name="used_two_phase",
            field=models.BooleanField(
                default=False,
                help_text="Whether two-phase Scout/Editor architecture was used",
            ),
        ),
        migrations.AddField(
            model_name="codejob",
            name="optimization_metrics",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Detailed optimization metrics (compression ratio, savings, etc.)",
            ),
        ),
    ]
