# Generated migration for adding endpoint features

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('llm', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelcatalog',
            name='supports_structured_outputs',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='supports_reasoning',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='modality',
            field=models.CharField(blank=True, help_text="Model modality (e.g., 'text->text', 'text+image->text')", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='input_modalities',
            field=models.JSONField(blank=True, default=list, help_text="List of supported input modalities (e.g., ['text', 'image'])"),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='output_modalities',
            field=models.JSONField(blank=True, default=list, help_text="List of supported output modalities (e.g., ['text'])"),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='tokenizer',
            field=models.CharField(blank=True, help_text="Tokenizer type (e.g., 'Llama3', 'Gemini')", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='max_completion_tokens',
            field=models.IntegerField(blank=True, help_text='Maximum completion tokens from top provider', null=True),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='is_moderated',
            field=models.BooleanField(default=False, help_text='Whether content moderation is enabled by top provider'),
        ),
        migrations.AddField(
            model_name='modelcatalog',
            name='default_parameters',
            field=models.JSONField(blank=True, default=dict, help_text='Default generation parameters (temperature, top_p, etc.)'),
        ),
    ]
