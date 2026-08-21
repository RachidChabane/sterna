from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sparks', '0003_extend_framework_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='spark',
            name='generated_r2_key',
            field=models.CharField(
                blank=True,
                default='',
                help_text='R2 key for generated binary output (PDF/DOCX)',
                max_length=500,
            ),
        ),
    ]
