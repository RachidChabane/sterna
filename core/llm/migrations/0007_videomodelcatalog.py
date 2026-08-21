# Generated migration for VideoModelCatalog

from decimal import Decimal
from django.db import migrations, models
import uuid


def seed_video_models(apps, schema_editor):
    """
    Seed the VideoModelCatalog with all available video generation models.

    This includes:
    - OpenAI Sora models (text-to-video)
    - Runway Veo models (text-to-video)
    - Runway Gen-4 models (image-to-video)
    - Runway upscaling model
    - Runway Act Two (character animation)
    """
    VideoModelCatalog = apps.get_model('llm', 'VideoModelCatalog')

    models_data = [
        # =================================================================
        # Runway Text-to-Video Models (Primary - Fast & Affordable)
        # =================================================================
        {
            'model_id': 'veo3.1_fast',
            'canonical_id': 'runway/veo3.1-fast',
            'provider': 'runway',
            'display_name': 'Veo 3.1 Fast',
            'description': 'Fast text-to-video generation, optimized for rapid prototyping and iterations.',
            'best_for': 'Quick iterations, drafts, testing ideas, cost-conscious users',
            'input_type': 'text',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 8,
                'min_duration': 4,
                'valid_durations': [4, 6, 8],
                'supported_resolutions': ['720p', '1080p'],
                'supported_aspect_ratios': ['16:9', '9:16', '1:1', '4:3', '3:4'],
                'supported_fps': [24],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.15'),
            'is_active': True,
            'is_pro': False,
            'is_default': True,
            'sort_order': 1,
        },
        {
            'model_id': 'veo3.1',
            'canonical_id': 'runway/veo3.1',
            'provider': 'runway',
            'display_name': 'Veo 3.1',
            'description': 'High quality text-to-video with optional audio generation and lip-sync support.',
            'best_for': 'Marketing content, professional videos, content requiring audio/lip-sync',
            'input_type': 'text',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 8,
                'min_duration': 4,
                'valid_durations': [4, 6, 8],
                'supported_resolutions': ['720p', '1080p'],
                'supported_aspect_ratios': ['16:9', '9:16', '1:1', '4:3', '3:4'],
                'supported_fps': [24],
                'supports_audio': True,
                'supports_lip_sync': True,
                'output_format': 'mp4',
                'price_with_audio_per_second': '0.40',  # Double price with audio
            },
            'current_price_per_second': Decimal('0.20'),
            'is_active': True,
            'is_pro': True,
            'is_default': False,
            'sort_order': 2,
        },
        {
            'model_id': 'veo3',
            'canonical_id': 'runway/veo3',
            'provider': 'runway',
            'display_name': 'Veo 3',
            'description': 'Previous generation text-to-video model, still available for compatibility.',
            'best_for': 'General purpose video generation, legacy workflows',
            'input_type': 'text',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 8,
                'min_duration': 4,
                'valid_durations': [4, 6, 8],
                'supported_resolutions': ['720p', '1080p'],
                'supported_aspect_ratios': ['16:9', '9:16'],
                'supported_fps': [24],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.15'),
            'is_active': True,
            'is_pro': False,
            'is_default': False,
            'sort_order': 3,
        },

        # =================================================================
        # OpenAI Sora Models (Text-to-Video)
        # =================================================================
        {
            'model_id': 'sora-2',
            'canonical_id': 'openai/sora-2',
            'provider': 'openai',
            'display_name': 'Sora 2 (Standard)',
            'description': 'Fast video generation from OpenAI, good for iterations and drafts.',
            'best_for': 'Quick iterations, social media clips, drafts',
            'input_type': 'text',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 12,
                'min_duration': 4,
                'valid_durations': [4, 8, 12],
                'supported_resolutions': ['720p'],
                'supported_aspect_ratios': ['16:9', '9:16'],
                'supported_fps': [24, 30],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.12'),
            'is_active': True,
            'is_pro': False,
            'is_default': False,
            'sort_order': 10,
        },
        {
            'model_id': 'sora-2-pro',
            'canonical_id': 'openai/sora-2-pro',
            'provider': 'openai',
            'display_name': 'Sora 2 Pro',
            'description': 'Highest quality cinematic output from OpenAI with 4K support.',
            'best_for': 'Marketing assets, cinematic footage, production content',
            'input_type': 'text',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 12,
                'min_duration': 4,
                'valid_durations': [4, 8, 12],
                'supported_resolutions': ['720p', '4K'],
                'supported_aspect_ratios': ['16:9', '9:16'],
                'supported_fps': [24, 30, 60],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.50'),
            'is_active': True,
            'is_pro': True,
            'is_default': False,
            'sort_order': 11,
        },

        # =================================================================
        # Runway Image-to-Video Models
        # =================================================================
        {
            'model_id': 'gen4_turbo',
            'canonical_id': 'runway/gen4-turbo',
            'provider': 'runway',
            'display_name': 'Gen-4 Turbo',
            'description': 'Fast image-to-video generation. Animates still images into video.',
            'best_for': 'Animating images, quick video from stills, social media content',
            'input_type': 'image',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 10,
                'min_duration': 5,
                'valid_durations': [5, 10],
                'supported_resolutions': ['720p', '1080p'],
                'supported_aspect_ratios': ['16:9', '9:16', '1:1'],
                'supported_fps': [24],
                'max_input_size_mb': 16,
                'supported_input_formats': ['jpeg', 'png', 'webp'],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.05'),
            'is_active': True,
            'is_pro': False,
            'is_default': False,
            'sort_order': 20,
        },
        {
            'model_id': 'gen4_aleph',
            'canonical_id': 'runway/gen4-aleph',
            'provider': 'runway',
            'display_name': 'Gen-4 Aleph',
            'description': 'High quality image or video transformation. Supports style transfer and video extension.',
            'best_for': 'Video transformation, style transfer, video extension, high-end productions',
            'input_type': 'image_video',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 10,
                'min_duration': 5,
                'valid_durations': [5, 10],
                'supported_resolutions': ['720p', '1080p'],
                'supported_aspect_ratios': ['16:9', '9:16', '1:1'],
                'supported_fps': [24],
                'max_input_size_mb': 32,
                'supported_input_formats': ['jpeg', 'png', 'webp', 'mp4', 'webm', 'mov'],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.15'),
            'is_active': True,
            'is_pro': True,
            'is_default': False,
            'sort_order': 21,
        },

        # =================================================================
        # Runway Video Upscaling
        # =================================================================
        {
            'model_id': 'upscale_v1',
            'canonical_id': 'runway/upscale-v1',
            'provider': 'runway',
            'display_name': 'Video Upscaler (4x)',
            'description': '4x video resolution upscaling. Enhances low-res videos to higher quality.',
            'best_for': 'Enhancing low-res videos, improving quality of old footage',
            'input_type': 'video',
            'output_type': 'upscaled',
            'capabilities': {
                'upscale_factor': 4,
                'max_input_duration': 30,
                'max_input_size_mb': 32,
                'supported_input_formats': ['mp4', 'webm', 'mov'],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.02'),
            'is_active': True,
            'is_pro': False,
            'is_default': False,
            'sort_order': 30,
        },

        # =================================================================
        # Runway Character Animation (Act Two)
        # =================================================================
        {
            'model_id': 'act_two',
            'canonical_id': 'runway/act-two',
            'provider': 'runway',
            'display_name': 'Act Two',
            'description': 'Character animation from image + audio. Creates talking head videos with lip-sync.',
            'best_for': 'Character lip-sync, avatar animation, talking heads, virtual presenters',
            'input_type': 'image_audio',
            'output_type': 'video',
            'capabilities': {
                'max_duration': 20,
                'max_audio_duration': 20,
                'supported_resolutions': ['720p', '1080p'],
                'max_input_size_mb': 16,
                'max_audio_size_mb': 32,
                'supported_input_formats': ['jpeg', 'png', 'webp'],
                'supported_audio_formats': ['mp3', 'wav', 'flac', 'm4a', 'aac'],
                'output_format': 'mp4',
            },
            'current_price_per_second': Decimal('0.05'),
            'is_active': True,
            'is_pro': False,
            'is_default': False,
            'sort_order': 40,
        },
    ]

    for model_data in models_data:
        VideoModelCatalog.objects.create(**model_data)


def remove_video_models(apps, schema_editor):
    """Reverse migration: remove all seeded video models."""
    VideoModelCatalog = apps.get_model('llm', 'VideoModelCatalog')
    VideoModelCatalog.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('llm', '0006_openrouterusagelog'),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoModelCatalog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('model_id', models.CharField(db_index=True, help_text="API model identifier (e.g., 'veo3.1_fast', 'sora-2')", max_length=100, unique=True)),
                ('canonical_id', models.CharField(db_index=True, help_text="Full canonical ID with provider prefix (e.g., 'runway/veo3.1-fast')", max_length=255, unique=True)),
                ('provider', models.CharField(db_index=True, help_text="Provider name (e.g., 'runway', 'openai')", max_length=50)),
                ('display_name', models.CharField(help_text='User-friendly display name', max_length=255)),
                ('description', models.TextField(blank=True, help_text="Description of the model's capabilities")),
                ('best_for', models.CharField(blank=True, help_text="Use case description (e.g., 'Quick iterations, social media clips')", max_length=500)),
                ('input_type', models.CharField(choices=[('text', 'Text Only'), ('image', 'Image Required'), ('video', 'Video Required'), ('image_video', 'Image or Video'), ('text_image', 'Text + Optional Image'), ('image_audio', 'Image + Audio')], db_index=True, default='text', help_text='Type of input the model requires', max_length=20)),
                ('output_type', models.CharField(choices=[('video', 'Generated Video'), ('upscaled', 'Upscaled Video')], default='video', help_text='Type of output the model produces', max_length=20)),
                ('capabilities', models.JSONField(blank=True, default=dict, help_text='Flexible capabilities dict with model-specific features')),
                ('current_price_per_second', models.DecimalField(blank=True, decimal_places=4, help_text='Current price per second of video in USD', max_digits=10, null=True)),
                ('current_price_per_request', models.DecimalField(blank=True, decimal_places=4, help_text='Current price per request in USD (for non-duration-based pricing)', max_digits=10, null=True)),
                ('is_active', models.BooleanField(db_index=True, default=True, help_text='Whether this model is currently available for use')),
                ('is_pro', models.BooleanField(default=False, help_text='Whether this is a premium/pro tier model')),
                ('is_default', models.BooleanField(default=False, help_text='Whether this is the default model for its input type')),
                ('sort_order', models.PositiveIntegerField(default=0, help_text='Display order (lower numbers shown first)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Video Model',
                'verbose_name_plural': 'Video Models',
                'ordering': ['sort_order', 'provider', 'display_name'],
            },
        ),
        migrations.AddIndex(
            model_name='videomodelcatalog',
            index=models.Index(fields=['provider'], name='llm_videomo_provide_4e5e3c_idx'),
        ),
        migrations.AddIndex(
            model_name='videomodelcatalog',
            index=models.Index(fields=['is_active'], name='llm_videomo_is_acti_f5e8d3_idx'),
        ),
        migrations.AddIndex(
            model_name='videomodelcatalog',
            index=models.Index(fields=['input_type'], name='llm_videomo_input_t_8a7c2f_idx'),
        ),
        migrations.AddIndex(
            model_name='videomodelcatalog',
            index=models.Index(fields=['sort_order'], name='llm_videomo_sort_or_d9e1a4_idx'),
        ),
        # Seed data
        migrations.RunPython(seed_video_models, remove_video_models),
    ]
