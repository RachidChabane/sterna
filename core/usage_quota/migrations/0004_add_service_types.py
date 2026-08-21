"""Add CODE_SESSION, MCP_TOOL_INVOCATION, GOOGLE_MAPS to ServiceType choices.

Pure choices-only migration: AlterField on UsageLog.service and
ServicePricing.service. No data change.
"""

from django.db import migrations, models


SERVICE_CHOICES = [
    ('openrouter', 'OpenRouter LLM'),
    ('elevenlabs_tts', 'ElevenLabs TTS'),
    ('openai_tts', 'OpenAI TTS'),
    ('deepgram_stt', 'Deepgram STT'),
    ('brave_search', 'Brave Search'),
    ('image_generation', 'Image Generation'),
    ('video_generation', 'Video Generation'),
    ('kb_embedding', 'Knowledge Base Embedding'),
    ('kb_query', 'Knowledge Base Query'),
    ('code_session', 'Code Session (Claude CLI)'),
    ('mcp_tool_invocation', 'MCP Tool Invocation'),
    ('google_maps', 'Google Maps Platform'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0003_load_initial_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='servicepricing',
            name='service',
            field=models.CharField(
                choices=SERVICE_CHOICES,
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='usagelog',
            name='service',
            field=models.CharField(
                choices=SERVICE_CHOICES,
                db_index=True,
                max_length=50,
            ),
        ),
    ]
