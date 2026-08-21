"""Drop Skill / SkillFile tables.

Skills was archived to ``archive/skills-feature`` (snapshot tag
``archive/skills-feature/snapshot-2026-05-20``) as part of task 2.
The implementation, including migrations 0014_add_skill ->
0020_skill_spec_compliance, lives on that branch. To restore
Skills, check out the archive branch and run ``migrate`` on a
fresh database.

This migration is reversible at the migration-graph level only:
the reverse path re-creates empty stub tables so Django can record
the rollback, but it does NOT restore data or schema fidelity.
For a real restore, use the archive branch.

For staging/production databases that already have 0014-0020
applied: the deploy procedure runs ``manage.py migrate code_sessions
0013 --fake`` to roll back the migration history pointer to 0013
before applying this migration. That deploy step is not encoded in
this file; the file itself is safe on a fresh DB (DROP IF EXISTS
no-ops) and on a properly fake-rolled DB (drops the live tables).

[MEM: sqlite-test-infra-cascade] The DROP / CREATE statements use
PG-only ``CASCADE`` syntax which SQLite's parser rejects. We wrap
them in a vendor-guarded RunPython so the migration is a no-op on
SQLite (test DB — the Skill tables never existed there) and runs
the original SQL on Postgres.
"""

from django.db import migrations


_DROP_SQL = (
    'DROP TABLE IF EXISTS "code_sessions_skillfile" CASCADE;\n'
    'DROP TABLE IF EXISTS "code_sessions_skill" CASCADE;'
)

_CREATE_SQL = (
    'CREATE TABLE IF NOT EXISTS "code_sessions_skill" '
    '("id" uuid PRIMARY KEY);\n'
    'CREATE TABLE IF NOT EXISTS "code_sessions_skillfile" '
    '("id" uuid PRIMARY KEY);'
)


def _drop_skill_tables(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        # SQLite (tests) and other vendors: tables never existed here,
        # so dropping them is a no-op. Skipping avoids the CASCADE
        # syntax error from SQLite's DROP TABLE parser.
        return
    schema_editor.execute(_DROP_SQL)


def _recreate_skill_stub_tables(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CREATE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("code_sessions", "0013_alter_subagent_model_tier_and_more"),
    ]

    operations = [
        migrations.RunPython(_drop_skill_tables, _recreate_skill_stub_tables),
    ]
