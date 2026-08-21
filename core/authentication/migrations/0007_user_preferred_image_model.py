# Generated migration for preferred_image_model field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0006_user_openrouter_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='preferred_image_model',
            field=models.CharField(
                choices=[
                    ('google/gemini-2.5-flash-image', 'Gemini 2.5 Flash Image (Fast)'),
                    ('google/gemini-3-pro-image-preview', 'Gemini 3 Pro Image (Quality)'),
                ],
                default='google/gemini-2.5-flash-image',
                help_text='Preferred model for image generation',
                max_length=255,
            ),
        ),
    ]
