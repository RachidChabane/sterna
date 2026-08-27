"""
Initial migration for Knowledge Base app.
Creates pgVector extension and all models.
"""

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from pgvector.django import VectorExtension, VectorField, HnswIndex  # type: ignore[import-untyped]


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Enable pgVector extension
        VectorExtension(),

        # KnowledgeBaseSettings model
        migrations.CreateModel(
            name='KnowledgeBaseSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=True)),
                ('auto_query', models.BooleanField(default=True, help_text='Automatically query KB when relevant')),
                ('similarity_threshold', models.FloatField(default=0.7)),
                ('max_chunks_per_query', models.PositiveIntegerField(default=5)),
                ('storage_limit_mb', models.PositiveIntegerField(default=100)),
                ('total_documents', models.PositiveIntegerField(default=0)),
                ('total_chunks', models.PositiveIntegerField(default=0)),
                ('total_storage_bytes', models.BigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='knowledge_base_settings',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Knowledge Base Settings',
                'verbose_name_plural': 'Knowledge Base Settings',
            },
        ),

        # KnowledgeDocument model
        migrations.CreateModel(
            name='KnowledgeDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('filename', models.CharField(max_length=500)),
                ('original_filename', models.CharField(max_length=500)),
                ('document_type', models.CharField(
                    choices=[
                        ('pdf', 'PDF'),
                        ('docx', 'Word Document'),
                        ('txt', 'Plain Text'),
                        ('md', 'Markdown'),
                        ('csv', 'CSV'),
                        ('html', 'HTML'),
                        ('json', 'JSON'),
                    ],
                    max_length=20
                )),
                ('mime_type', models.CharField(max_length=100)),
                ('file_size_bytes', models.BigIntegerField()),
                ('storage_type', models.CharField(
                    choices=[('inline', 'Inline'), ('r2', 'R2')],
                    default='inline',
                    max_length=20
                )),
                ('content', models.BinaryField(blank=True, null=True)),
                ('r2_bucket', models.CharField(blank=True, max_length=255)),
                ('r2_key', models.CharField(blank=True, max_length=500)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('processing', 'Processing'),
                        ('indexing', 'Indexing'),
                        ('ready', 'Ready'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=20
                )),
                ('error_message', models.TextField(blank=True)),
                ('extracted_text', models.TextField(blank=True)),
                ('page_count', models.PositiveIntegerField(null=True)),
                ('word_count', models.PositiveIntegerField(null=True)),
                ('chunk_count', models.PositiveIntegerField(default=0)),
                ('content_hash', models.CharField(db_index=True, max_length=64)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(null=True)),
                ('last_queried_at', models.DateTimeField(null=True)),
                ('tags', models.JSONField(default=list)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='knowledge_documents',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'ordering': ['-uploaded_at'],
            },
        ),

        # Indexes for KnowledgeDocument
        migrations.AddIndex(
            model_name='knowledgedocument',
            index=models.Index(fields=['user', '-uploaded_at'], name='knowledge_b_user_id_abc123_idx'),
        ),
        migrations.AddIndex(
            model_name='knowledgedocument',
            index=models.Index(fields=['user', 'status'], name='knowledge_b_user_id_status_idx'),
        ),
        migrations.AddIndex(
            model_name='knowledgedocument',
            index=models.Index(fields=['user', 'content_hash'], name='knowledge_b_user_id_hash_idx'),
        ),

        # KnowledgeChunk model
        migrations.CreateModel(
            name='KnowledgeChunk',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('chunk_index', models.PositiveIntegerField()),
                ('start_char', models.PositiveIntegerField(null=True)),
                ('end_char', models.PositiveIntegerField(null=True)),
                ('page_number', models.PositiveIntegerField(null=True)),
                ('embedding', VectorField(dimensions=1536, null=True)),
                ('embedding_model', models.CharField(max_length=100)),
                ('token_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='chunks',
                    to='knowledge_base.knowledgedocument'
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='knowledge_chunks',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'ordering': ['document', 'chunk_index'],
            },
        ),

        # Indexes for KnowledgeChunk
        migrations.AddIndex(
            model_name='knowledgechunk',
            index=models.Index(fields=['user', 'document'], name='knowledge_b_user_doc_idx'),
        ),
        migrations.AddIndex(
            model_name='knowledgechunk',
            index=models.Index(fields=['document', 'chunk_index'], name='knowledge_b_doc_chunk_idx'),
        ),

        # HNSW index for vector similarity search
        migrations.AddIndex(
            model_name='knowledgechunk',
            index=HnswIndex(
                name='chunk_embedding_hnsw_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ),

        # KnowledgeQueryLog model
        migrations.CreateModel(
            name='KnowledgeQueryLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('query_text', models.TextField()),
                ('query_embedding_model', models.CharField(max_length=100)),
                ('chunks_searched', models.PositiveIntegerField()),
                ('chunks_returned', models.PositiveIntegerField()),
                ('top_similarity_score', models.FloatField(null=True)),
                ('conversation_id', models.UUIDField(null=True)),
                ('chat_id', models.UUIDField(null=True)),
                ('invocation_type', models.CharField(
                    choices=[
                        ('auto', 'Automatic'),
                        ('explicit', 'Explicit (@kb)'),
                        ('ui', 'UI Search'),
                    ],
                    max_length=20
                )),
                ('embedding_cost_usd', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('latency_ms', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='knowledge_query_logs',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
        ),

        # Indexes for KnowledgeQueryLog
        migrations.AddIndex(
            model_name='knowledgequerylog',
            index=models.Index(fields=['user', '-created_at'], name='knowledge_b_user_created_idx'),
        ),
        migrations.AddIndex(
            model_name='knowledgequerylog',
            index=models.Index(fields=['user', 'invocation_type', '-created_at'], name='knowledge_b_user_inv_idx'),
        ),
    ]
