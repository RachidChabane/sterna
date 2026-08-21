import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sparks', '0004_spark_generated_r2_key'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SparkDeployment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('scaffolding', 'Scaffolding'), ('deploying', 'Deploying'), ('deployed', 'Deployed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('preview_url', models.URLField(blank=True)),
                ('claim_url', models.URLField(blank=True)),
                ('deployment_id', models.CharField(blank=True, max_length=255)),
                ('project_id', models.CharField(blank=True, max_length=255)),
                ('error_message', models.TextField(blank=True)),
                ('coding_agent_job_id', models.CharField(blank=True, max_length=255)),
                ('cost_usd', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('spark', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deployments', to='sparks.spark')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spark_deployments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['spark', '-created_at'], name='sparks_spark_spark_i_idx'),
                    models.Index(fields=['user', 'status'], name='sparks_spark_user_id_idx'),
                ],
            },
        ),
    ]
