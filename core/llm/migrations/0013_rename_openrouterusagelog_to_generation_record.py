# Scopes OpenRouterUsageLog as OpenRouterGenerationRecord, a
# provider-analytics model distinct from the billing ledger of record
# (usage_quota.UsageLog). RenameModel issues an ALTER TABLE RENAME (no
# db_table was ever pinned, so the table follows the class name), which
# is a metadata-only operation and preserves existing rows.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('llm', '0012_rename_sterna_models'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='OpenRouterUsageLog',
            new_name='OpenRouterGenerationRecord',
        ),
        migrations.RenameIndex(
            model_name='openroutergenerationrecord',
            new_name='llm_openrou_user_id_927633_idx',
            old_name='llm_openrou_user_id_2eb5d4_idx',
        ),
        migrations.RenameIndex(
            model_name='openroutergenerationrecord',
            new_name='llm_openrou_user_id_a4db24_idx',
            old_name='llm_openrou_user_id_23fb72_idx',
        ),
        migrations.RenameIndex(
            model_name='openroutergenerationrecord',
            new_name='llm_openrou_request_95be61_idx',
            old_name='llm_openrou_request_f78aa3_idx',
        ),
        migrations.AlterModelOptions(
            name='openroutergenerationrecord',
            options={'ordering': ['-timestamp'], 'verbose_name': 'OpenRouter Generation Record', 'verbose_name_plural': 'OpenRouter Generation Records'},
        ),
        migrations.AlterField(
            model_name='openroutergenerationrecord',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='openrouter_generation_records', to=settings.AUTH_USER_MODEL),
        ),
    ]
