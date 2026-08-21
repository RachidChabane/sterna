# Generated manually for OpenRouter Usage Log model

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('llm', '0005_add_performance_stats'),
    ]

    operations = [
        migrations.CreateModel(
            name='OpenRouterUsageLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('model_id', models.CharField(db_index=True, max_length=128)),
                ('prompt_tokens', models.IntegerField(default=0)),
                ('completion_tokens', models.IntegerField(default=0)),
                ('total_tokens', models.IntegerField(default=0)),
                ('cost_usd', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('endpoint', models.CharField(default='chat/completions', max_length=64)),
                ('request_source', models.CharField(db_index=True, help_text="Where the request originated (e.g., 'chat', 'voice_room', 'mcp_discovery')", max_length=64)),
                ('openrouter_request_id', models.CharField(blank=True, max_length=128, null=True)),
                ('extra_data', models.JSONField(blank=True, default=dict, help_text='Additional request metadata (project_id, etc.)')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='openrouter_usage_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'OpenRouter Usage Log',
                'verbose_name_plural': 'OpenRouter Usage Logs',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='openrouterusagelog',
            index=models.Index(fields=['user', 'timestamp'], name='llm_openrou_user_id_d5d64c_idx'),
        ),
        migrations.AddIndex(
            model_name='openrouterusagelog',
            index=models.Index(fields=['user', 'model_id'], name='llm_openrou_user_id_29c0c0_idx'),
        ),
        migrations.AddIndex(
            model_name='openrouterusagelog',
            index=models.Index(fields=['request_source', 'timestamp'], name='llm_openrou_request_4dbc67_idx'),
        ),
    ]
