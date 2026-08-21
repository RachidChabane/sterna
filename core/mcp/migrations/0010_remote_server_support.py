# Generated migration for remote MCP server support

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add support for remote HTTP/SSE MCP servers."""

    dependencies = [
        ('mcp', '0009_add_npm_package_and_env_vars'),
    ]

    operations = [
        # Add remote_url field for HTTP-based remote servers
        migrations.AddField(
            model_name='mcpserver',
            name='remote_url',
            field=models.URLField(
                blank=True,
                null=True,
                help_text='URL for remote MCP servers (HTTP/SSE transport)',
            ),
        ),

        # Add auth_type field for remote server authentication
        migrations.AddField(
            model_name='mcpserver',
            name='auth_type',
            field=models.CharField(
                choices=[
                    ('none', 'No Auth'),
                    ('api_key', 'API Key'),
                    ('bearer', 'Bearer Token'),
                    ('oauth', 'OAuth 2.0'),
                ],
                default='none',
                max_length=20,
                help_text='Authentication type for remote servers',
            ),
        ),

        # Add auth_header_name for custom auth header names
        migrations.AddField(
            model_name='mcpserver',
            name='auth_header_name',
            field=models.CharField(
                default='Authorization',
                max_length=100,
                help_text='HTTP header name for authentication (e.g., Authorization, X-API-Key)',
            ),
        ),

        # Update transport_type choices to include new types
        migrations.AlterField(
            model_name='mcpserver',
            name='transport_type',
            field=models.CharField(
                choices=[
                    ('websocket', 'WebSocket'),
                    ('stdio', 'Standard I/O'),
                    ('http', 'HTTP/SSE (Remote)'),
                    ('sandboxed', 'Sandboxed NPM'),
                ],
                default='sandboxed',
                max_length=20,
                help_text='Transport protocol to use',
            ),
        ),
    ]
