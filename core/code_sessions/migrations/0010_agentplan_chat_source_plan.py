"""Add chat and source_plan FKs to AgentPlan."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("code_sessions", "0009_agentplan_implementation_branch"),
        ("conversations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentplan",
            name="chat",
            field=models.ForeignKey(
                blank=True,
                help_text="Chat this plan belongs to",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agent_plans",
                to="conversations.chat",
            ),
        ),
        migrations.AddField(
            model_name="agentplan",
            name="source_plan",
            field=models.ForeignKey(
                blank=True,
                help_text="Original plan this was imported from",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="copies",
                to="code_sessions.agentplan",
            ),
        ),
        migrations.AddIndex(
            model_name="agentplan",
            index=models.Index(
                fields=["chat", "-created_at"],
                name="code_sessio_chat_id_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="agentplan",
            index=models.Index(
                fields=["chat", "repo_full_name"],
                name="code_sessio_chat_id_repo_idx",
            ),
        ),
    ]
