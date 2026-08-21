"""Add ``User.tos_accepted_at`` to record ToS / Privacy Policy acceptance.

Forward: additive ``AddField`` (nullable). Forward-compatible — existing
rows simply carry ``NULL`` until the user re-accepts (R1 in task-15
plan; not forced in v1).

Reverse: drops the column. **Reverse path deletes data** (the captured
acceptance timestamp). Acceptable because acceptance can be re-captured
on next login if the column is reintroduced, and no other table FKs to
it.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0009_update_video_model_choices_veo"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="tos_accepted_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Timestamp when the user accepted the Terms of Service "
                    "and Privacy Policy."
                ),
                null=True,
                verbose_name="terms accepted at",
            ),
        ),
    ]
