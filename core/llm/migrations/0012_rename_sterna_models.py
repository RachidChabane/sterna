# Hand-written: renames the internal routing-engine models away from the
# "Sterna" name, freeing it as the product's public auto-router brand.
# See .oss-prep/notes/naming-map.md. Table names change via Django's
# default naming (no db_table was ever pinned), documented explicitly here
# rather than left implicit.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('llm', '0011_remove_supports_web_search'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='SternaRoutingPool',
            new_name='RoutingPool',
        ),
        migrations.RenameModel(
            old_name='SternaConversationScore',
            new_name='RoutingConversationScore',
        ),
        migrations.RenameModel(
            old_name='SternaRoutingLog',
            new_name='RoutingLog',
        ),
        migrations.RenameIndex(
            model_name='routingpool',
            new_name='llm_routing_is_acti_4ebcc0_idx',
            old_name='llm_sternar_is_acti_a8afbf_idx',
        ),
        migrations.AlterModelOptions(
            name='routingpool',
            options={'ordering': ['cost_tier', 'priority'], 'verbose_name': 'Routing Pool Entry', 'verbose_name_plural': 'Routing Pool'},
        ),
        migrations.AlterModelOptions(
            name='routingconversationscore',
            options={'verbose_name': 'Routing Conversation Score', 'verbose_name_plural': 'Routing Conversation Scores'},
        ),
        migrations.AlterModelOptions(
            name='routinglog',
            options={'ordering': ['-timestamp'], 'verbose_name': 'Routing Log', 'verbose_name_plural': 'Routing Logs'},
        ),
        migrations.AlterField(
            model_name='routingpool',
            name='model',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routing_pool_entries', to='llm.modelcatalog'),
        ),
        migrations.AlterField(
            model_name='routingconversationscore',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routing_conversation_scores', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='routinglog',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routing_logs', to=settings.AUTH_USER_MODEL),
        ),
    ]
