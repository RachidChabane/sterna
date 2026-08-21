"""Remove the deprecated Video Upscaler model from VideoModelCatalog.

Runway no longer offers an upscale API endpoint, so this model is unusable.
"""

from django.db import migrations


def remove_upscale_model(apps, schema_editor):
    VideoModelCatalog = apps.get_model('llm', 'VideoModelCatalog')
    VideoModelCatalog.objects.filter(model_id='upscale_v1').delete()


def restore_upscale_model(apps, schema_editor):
    from decimal import Decimal
    VideoModelCatalog = apps.get_model('llm', 'VideoModelCatalog')
    VideoModelCatalog.objects.create(
        model_id='upscale_v1',
        canonical_id='runway/upscale-v1',
        provider='runway',
        display_name='Video Upscaler (4x)',
        description='4x video resolution upscaling. Enhances low-res videos to higher quality.',
        best_for='Enhancing low-res videos, improving quality of old footage',
        input_type='video',
        output_type='upscaled',
        capabilities={
            'upscale_factor': 4,
            'max_input_duration': 30,
            'max_input_size_mb': 32,
            'supported_input_formats': ['mp4', 'webm', 'mov'],
            'output_format': 'mp4',
        },
        current_price_per_second=Decimal('0.02'),
        is_active=True,
        is_pro=False,
        is_default=False,
        sort_order=30,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('llm', '0008_imagemodelcatalog'),
    ]

    operations = [
        migrations.RunPython(remove_upscale_model, restore_upscale_model),
    ]
