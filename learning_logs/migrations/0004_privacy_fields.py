from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('learning_logs', '0003_topic_owner'),
    ]

    operations = [
        migrations.AddField(
            model_name='topic',
            name='is_public',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='entry',
            name='is_public',
            field=models.BooleanField(default=False),
        ),
    ]
