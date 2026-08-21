# Generated migration for adding npm_package, env_vars, and allowed_domains fields

from django.db import migrations, models
import mcp.fields


class Migration(migrations.Migration):

    dependencies = [
        ('mcp', '0008_add_connection_id_to_existing_servers'),
    ]

    operations = [
        migrations.AddField(
            model_name='mcpserver',
            name='npm_package',
            field=models.CharField(
                blank=True,
                help_text="NPM package name (e.g., '@modelcontextprotocol/server-github'). Required for stdio transport.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='env_vars',
            field=mcp.fields.EncryptedJSONField(
                blank=True,
                default=dict,
                help_text='Environment variables to pass to the MCP server (encrypted at rest). Use for API keys, tokens, etc.',
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='allowed_domains',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Custom domains to allow for network egress (in addition to defaults like npm registry)',
            ),
        ),
        migrations.AlterField(
            model_name='mcpserver',
            name='command',
            field=models.CharField(
                blank=True,
                help_text='Command to run for stdio transport (legacy, use npm_package instead)',
                max_length=500,
            ),
        ),
    ]
