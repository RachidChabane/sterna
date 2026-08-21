# Generated migration to remove MCPConnector, MCPConnection, MCPAuthorizationToken
# and add icon_url, is_preconfigured fields to MCPServer

from django.db import migrations, models


class Migration(migrations.Migration):
    """Remove connector models and add preconfigured server fields.

    This migration:
    1. Adds icon_url and is_preconfigured fields to MCPServer
    2. Removes MCPConnector, MCPConnection, MCPAuthorizationToken models

    All MCP integrations are now unified under MCPServer. Preconfigured
    integrations (GitHub, Notion, etc.) are MCPServer records with
    is_preconfigured=True.
    """

    dependencies = [
        ('mcp', '0011_oauth_dynamic_fields'),
    ]

    operations = [
        # Add new fields to MCPServer for preconfigured server support
        migrations.AddField(
            model_name='mcpserver',
            name='icon_url',
            field=models.URLField(
                blank=True,
                null=True,
                help_text='URL for the server icon (for display in UI)',
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='is_preconfigured',
            field=models.BooleanField(
                default=False,
                help_text='Whether this is a system-wide preconfigured server (not user-created)',
            ),
        ),

        # Remove connector-related models (order matters: dependent models first)
        # MCPConnection has FK to MCPConnector, so delete it first
        migrations.DeleteModel(
            name='MCPConnection',
        ),
        migrations.DeleteModel(
            name='MCPConnector',
        ),
        migrations.DeleteModel(
            name='MCPAuthorizationToken',
        ),
    ]
