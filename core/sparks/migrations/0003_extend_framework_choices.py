# Generated migration to add new framework choices

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sparks', '0002_add_assets_to_spark'),
    ]

    operations = [
        migrations.AlterField(
            model_name='spark',
            name='framework',
            field=models.CharField(
                choices=[
                    ('react', 'React'),
                    ('html', 'HTML'),
                    ('svg', 'SVG'),
                    ('markdown', 'Markdown'),
                    ('mermaid', 'Mermaid'),
                    ('pdf', 'PDF'),
                    ('docx', 'DOCX'),
                    ('ics', 'ICS'),
                    ('csv', 'CSV'),
                ],
                default='react',
                max_length=20,
            ),
        ),
    ]
