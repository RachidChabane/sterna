# Generated migration for MCP OAuth dynamic fields

from django.db import migrations, models
import mcp.fields


class Migration(migrations.Migration):
    """Add OAuth 2.1 dynamic discovery fields to MCPServer."""

    dependencies = [
        ('mcp', '0010_remote_server_support'),
    ]

    operations = [
        # OAuth server metadata (cached from discovery)
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_metadata',
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text='Cached OAuth server metadata from /.well-known/oauth-authorization-server',
            ),
        ),
        # Client credentials (from dynamic registration or manual)
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_client_id',
            field=models.CharField(
                max_length=500,
                blank=True,
                help_text='OAuth client ID (from dynamic registration or manual)',
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_client_secret',
            field=mcp.fields.EncryptedTextField(
                blank=True,
                default='',
                help_text='OAuth client secret (encrypted at rest)',
            ),
        ),
        # Access and refresh tokens
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_access_token',
            field=mcp.fields.EncryptedTextField(
                blank=True,
                default='',
                help_text='OAuth access token (encrypted at rest)',
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_refresh_token',
            field=mcp.fields.EncryptedTextField(
                blank=True,
                default='',
                help_text='OAuth refresh token (encrypted at rest)',
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_token_expires_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='When the OAuth access token expires',
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_scopes',
            field=models.JSONField(
                default=list,
                blank=True,
                help_text='OAuth scopes granted during authorization',
            ),
        ),
        # Temporary fields for OAuth flow
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_state',
            field=models.CharField(
                max_length=100,
                blank=True,
                help_text='Temporary state parameter for OAuth flow (CSRF protection)',
            ),
        ),
        migrations.AddField(
            model_name='mcpserver',
            name='oauth_pkce_verifier',
            field=mcp.fields.EncryptedTextField(
                blank=True,
                default='',
                help_text='Temporary PKCE code verifier (encrypted at rest)',
            ),
        ),
    ]
