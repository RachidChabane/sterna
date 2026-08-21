"""
Migration to add indexes for message content search.
Requires PostgreSQL with pg_trgm extension.
"""
from django.db import migrations


def add_search_indexes_forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    schema_editor.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS conversations_message_content_trgm_idx "
        "ON conversations_message USING gin ((content::text) gin_trgm_ops);"
    )
    schema_editor.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS conversations_message_chat_created_idx "
        "ON conversations_message (chat_id, created_at DESC);"
    )


def add_search_indexes_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS conversations_message_content_trgm_idx;")
    schema_editor.execute("DROP INDEX IF EXISTS conversations_message_chat_created_idx;")
    schema_editor.execute("DROP EXTENSION IF EXISTS pg_trgm;")


class Migration(migrations.Migration):
    # atomic=False required for CREATE INDEX CONCURRENTLY on PostgreSQL
    atomic = False

    dependencies = [
        ('conversations', '0003_remove_branch_index'),
    ]

    operations = [
        migrations.RunPython(
            add_search_indexes_forward,
            add_search_indexes_reverse,
        ),
    ]
