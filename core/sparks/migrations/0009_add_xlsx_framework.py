# Generated migration to add xlsx framework choice

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sparks', '0008_app'),
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
                    ('xlsx', 'Excel Spreadsheet'),
                ],
                default='react',
                max_length=20,
            ),
        ),
    ]
