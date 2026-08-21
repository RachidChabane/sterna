"""Add repo_full_name to AgentPlan for cross-conversation persistence."""

from django.db import migrations, models


def backfill_repo_full_name(apps, schema_editor):
    """Backfill repo_full_name from conversation's cloned repository."""
    AgentPlan = apps.get_model("code_sessions", "AgentPlan")
    ClonedRepository = apps.get_model("code_sessions", "ClonedRepository")

    for plan in AgentPlan.objects.filter(repo_full_name=""):
        try:
            cloned_repo = ClonedRepository.objects.get(
                conversation_id=plan.conversation_id
            )
            plan.repo_full_name = cloned_repo.full_name
            plan.save(update_fields=["repo_full_name"])
        except ClonedRepository.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("code_sessions", "0007_add_github_issue_fields_to_agentplan"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentplan",
            name="repo_full_name",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="GitHub repo full name (owner/repo) for cross-conversation persistence",
                max_length=255,
            ),
        ),
        migrations.RunPython(
            backfill_repo_full_name,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
