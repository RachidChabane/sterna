"""Add Sterna intelligent routing models and seed initial routing pool."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_routing_pool(apps, schema_editor):
    """Seed the initial routing pool. Skips models not in catalog."""
    ModelCatalog = apps.get_model('llm', 'ModelCatalog')
    SternaRoutingPool = apps.get_model('llm', 'SternaRoutingPool')

    pool_config = [
        {"model_id": "google/gemini-2.0-flash-001", "cost_tier": "budget", "min": 0, "max": 30, "priority": 10},
        {"model_id": "google/gemini-2.5-flash-lite", "cost_tier": "budget", "min": 0, "max": 40, "priority": 5},
        {"model_id": "anthropic/claude-haiku-4.5", "cost_tier": "balanced", "min": 15, "max": 65, "priority": 10},
        {"model_id": "anthropic/claude-sonnet-4.5", "cost_tier": "premium", "min": 40, "max": 100, "priority": 10},
    ]

    for entry in pool_config:
        catalog_model = ModelCatalog.objects.filter(model_id=entry["model_id"]).first()
        if not catalog_model:
            continue
        SternaRoutingPool.objects.get_or_create(
            model=catalog_model,
            defaults={
                "is_active": True,
                "cost_tier": entry["cost_tier"],
                "min_complexity_score": entry["min"],
                "max_complexity_score": entry["max"],
                "priority": entry["priority"],
            },
        )


def reverse_seed(apps, schema_editor):
    SternaRoutingPool = apps.get_model('llm', 'SternaRoutingPool')
    SternaRoutingPool.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("llm", "0009_remove_upscale_video_model"),
    ]

    operations = [
        migrations.CreateModel(
            name="SternaRoutingPool",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("cost_tier", models.CharField(choices=[("budget", "Budget"), ("balanced", "Balanced"), ("premium", "Premium")], max_length=20)),
                ("min_complexity_score", models.IntegerField(default=0, help_text="Minimum complexity score (0-100) for this model")),
                ("max_complexity_score", models.IntegerField(default=100, help_text="Maximum complexity score (0-100) for this model")),
                ("priority", models.IntegerField(default=0, help_text="Tiebreaker within same cost tier (higher = preferred)")),
                ("model", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sterna_pool_entries", to="llm.modelcatalog")),
            ],
            options={
                "ordering": ["cost_tier", "priority"],
                "verbose_name": "Sterna Routing Pool Entry",
                "verbose_name_plural": "Sterna Routing Pool",
            },
        ),
        migrations.AddIndex(
            model_name="sternaroutingpool",
            index=models.Index(fields=["is_active", "cost_tier"], name="llm_sternaro_is_acti_idx"),
        ),
        migrations.CreateModel(
            name="SternaConversationScore",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("conversation_id", models.CharField(db_index=True, max_length=255)),
                ("current_score", models.IntegerField(default=0)),
                ("max_score", models.IntegerField(default=0)),
                ("turn_count", models.IntegerField(default=0)),
                ("last_model_id", models.CharField(blank=True, max_length=255, null=True)),
                ("consecutive_simple_turns", models.IntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sterna_conversation_scores", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "unique_together": {("conversation_id", "user")},
                "verbose_name": "Sterna Conversation Score",
                "verbose_name_plural": "Sterna Conversation Scores",
            },
        ),
        migrations.CreateModel(
            name="SternaRoutingLog",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("conversation_id", models.CharField(max_length=255)),
                ("tier_used", models.IntegerField(help_text="1 = heuristic only, 2 = LLM classification")),
                ("heuristic_score", models.IntegerField()),
                ("llm_score", models.IntegerField(blank=True, null=True)),
                ("final_score", models.IntegerField()),
                ("resolved_model_id", models.CharField(max_length=255)),
                ("prompt_length", models.IntegerField()),
                ("has_images", models.BooleanField(default=False)),
                ("has_code", models.BooleanField(default=False)),
                ("classification_cost_usd", models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True)),
                ("classification_latency_ms", models.IntegerField(blank=True, null=True)),
                ("is_reroute", models.BooleanField(default=False)),
                ("rerouted_from_model", models.CharField(blank=True, max_length=255, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sterna_routing_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-timestamp"],
                "verbose_name": "Sterna Routing Log",
                "verbose_name_plural": "Sterna Routing Logs",
            },
        ),
        migrations.RunPython(seed_routing_pool, reverse_seed),
    ]
