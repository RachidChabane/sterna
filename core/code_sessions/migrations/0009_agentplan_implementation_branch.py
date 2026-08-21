"""Add implementation_branch to AgentPlan."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("code_sessions", "0008_agentplan_repo_full_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentplan",
            name="implementation_branch",
            field=models.CharField(
                blank=True,
                help_text="Git branch created for implementation",
                max_length=200,
            ),
        ),
    ]
