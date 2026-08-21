# Generated manually for OpenRouter API key fields

from django.db import migrations, models
import mcp.fields


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0005_populate_social_accounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='openrouter_api_key',
            field=mcp.fields.EncryptedTextField(blank=True, help_text="User's personal OpenRouter API key (encrypted at rest)", null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='openrouter_key_hash',
            field=models.CharField(blank=True, db_index=True, help_text='Hash identifier from OpenRouter for key management API', max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='openrouter_key_provisioned_at',
            field=models.DateTimeField(blank=True, help_text='When the OpenRouter key was provisioned', null=True),
        ),
    ]
