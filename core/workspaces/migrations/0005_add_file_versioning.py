"""
Add file versioning models.

Creates FileVersionContent (deduplicated content storage) and FileVersion
(version metadata with source tracking).
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('conversations', '0001_initial'),
        ('workspaces', '0004_workspace_chat_asset_chat'),
    ]

    operations = [
        # Create FileVersionContent first (referenced by FileVersion)
        migrations.CreateModel(
            name='FileVersionContent',
            fields=[
                ('sha256_hash', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('storage_type', models.CharField(
                    choices=[('inline', 'Inline (PostgreSQL)'), ('r2', 'R2 (Cloudflare)')],
                    default='inline',
                    max_length=10
                )),
                ('content', models.BinaryField(blank=True, null=True)),
                ('r2_key', models.CharField(blank=True, max_length=1024)),
                ('size_bytes', models.BigIntegerField()),
                ('reference_count', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'File Version Content',
                'verbose_name_plural': 'File Version Contents',
                'db_table': 'workspaces_file_version_content',
            },
        ),
        # Create FileVersion
        migrations.CreateModel(
            name='FileVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('path', models.CharField(db_index=True, max_length=1024)),
                ('version_number', models.PositiveIntegerField()),
                ('source_type', models.CharField(
                    choices=[
                        ('user_edit', 'User Edit'),
                        ('file_tool', 'File Tool'),
                        ('coding_agent', 'Coding Agent'),
                        ('upload', 'Upload'),
                        ('restore', 'Restore'),
                        ('initial', 'Initial'),
                    ],
                    max_length=20
                )),
                ('source_job_id', models.CharField(blank=True, max_length=50)),
                ('source_tool_name', models.CharField(blank=True, max_length=50)),
                ('size_bytes', models.BigIntegerField()),
                ('is_deleted', models.BooleanField(default=False)),
                ('is_binary', models.BooleanField(default=False)),
                ('mime_type', models.CharField(blank=True, max_length=127)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('content_ref', models.ForeignKey(
                    db_column='sha256_hash',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='versions',
                    to='workspaces.fileversioncontent',
                    to_field='sha256_hash',
                )),
                ('workspace', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='file_versions',
                    to='workspaces.workspace',
                )),
                ('source_message', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='file_versions',
                    to='conversations.message',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='file_versions_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'workspaces_file_version',
                'ordering': ['path', '-version_number'],
            },
        ),
        # Add indexes
        migrations.AddIndex(
            model_name='fileversion',
            index=models.Index(fields=['workspace', 'path', 'created_at'], name='ws_fv_path_created_idx'),
        ),
        migrations.AddIndex(
            model_name='fileversion',
            index=models.Index(fields=['workspace', 'created_at'], name='ws_fv_workspace_created_idx'),
        ),
        migrations.AddIndex(
            model_name='fileversion',
            index=models.Index(fields=['source_type'], name='ws_fv_source_type_idx'),
        ),
        migrations.AddIndex(
            model_name='fileversion',
            index=models.Index(fields=['source_message'], name='ws_fv_source_msg_idx'),
        ),
        # Add unique constraint
        migrations.AddConstraint(
            model_name='fileversion',
            constraint=models.UniqueConstraint(
                fields=['workspace', 'path', 'version_number'],
                name='unique_workspace_path_version',
            ),
        ),
    ]
