from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('learning_logs', '0009_alter_attachment_entry_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='attachment',
            name='relative_path',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
