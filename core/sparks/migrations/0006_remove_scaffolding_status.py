from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sparks', '0005_sparkdeployment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sparkdeployment',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('deploying', 'Deploying'),
                    ('deployed', 'Deployed'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
