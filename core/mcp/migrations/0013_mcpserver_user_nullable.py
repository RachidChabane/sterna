# Migration to make MCPServer.user nullable for preconfigured servers

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Allow null user for preconfigured MCP servers.

    Preconfigured servers (is_preconfigured=True) are system-wide templates
    available to all users and don't belong to any specific user.
    """

    dependencies = [
        ('mcp', '0012_remove_connectors_add_server_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='mcpserver',
            name='user',
            field=models.ForeignKey(
                blank=True,
                help_text='User who owns this server configuration (null for preconfigured servers)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='mcp_servers',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
