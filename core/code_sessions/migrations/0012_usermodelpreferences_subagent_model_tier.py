# Generated migration for model tier system

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_model_id_to_tier(apps, schema_editor):
    """Data migration: convert model_id to model_tier using substring matching."""
    SubAgent = apps.get_model('code_sessions', 'SubAgent')
    for agent in SubAgent.objects.all():
        model_lower = (agent.model_id or "").lower()
        if "opus" in model_lower:
            agent.model_tier = "powerful"
        elif "haiku" in model_lower:
            agent.model_tier = "fast"
        else:
            agent.model_tier = "balanced"  # sonnet, non-Anthropic, empty, anything else
        agent.save(update_fields=["model_tier"])


class Migration(migrations.Migration):

    dependencies = [
        ('code_sessions', '0011_add_subagent'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create UserModelPreferences model
        migrations.CreateModel(
            name='UserModelPreferences',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fast_model_id', models.CharField(blank=True, default='', help_text="OpenRouter model ID for the 'fast' tier (empty = latest haiku)", max_length=255)),
                ('balanced_model_id', models.CharField(blank=True, default='', help_text="OpenRouter model ID for the 'balanced' tier (empty = latest sonnet)", max_length=255)),
                ('powerful_model_id', models.CharField(blank=True, default='', help_text="OpenRouter model ID for the 'powerful' tier (empty = latest opus)", max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(help_text='User who owns these preferences', on_delete=django.db.models.deletion.CASCADE, related_name='model_preferences', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'User Model Preferences',
                'verbose_name_plural': 'User Model Preferences',
            },
        ),
        # 2. Add model_tier field (with default)
        migrations.AddField(
            model_name='subagent',
            name='model_tier',
            field=models.CharField(
                choices=[('fast', 'Fast'), ('balanced', 'Balanced'), ('powerful', 'Powerful'), ('inherit', 'Inherit from Chat')],
                default='balanced',
                help_text='Model tier for this sub-agent (fast/balanced/powerful/inherit)',
                max_length=20,
            ),
        ),
        # 3. Data migration: convert existing model_id values to tiers
        migrations.RunPython(
            migrate_model_id_to_tier,
            reverse_code=migrations.RunPython.noop,
        ),
        # 4. Remove old model_id field
        migrations.RemoveField(
            model_name='subagent',
            name='model_id',
        ),
    ]
