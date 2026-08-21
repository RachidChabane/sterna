# Generated manually to remove orphaned branch_index column
from django.db import migrations


def drop_branch_index_forward(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS conv_msg_branch_idx;")
        schema_editor.execute("ALTER TABLE conversations_message DROP COLUMN IF EXISTS branch_index;")


def drop_branch_index_reverse(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("ALTER TABLE conversations_message ADD COLUMN branch_index integer NOT NULL DEFAULT 0;")
        schema_editor.execute("CREATE INDEX conv_msg_branch_idx ON conversations_message (chat_id, parent_id, branch_index);")


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0002_add_chat_position'),
    ]

    operations = [
        migrations.RunPython(
            drop_branch_index_forward,
            drop_branch_index_reverse,
        ),
    ]
