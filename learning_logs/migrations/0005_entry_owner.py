from django.db import migrations, models
from django.conf import settings


def set_entry_owner_from_topic(apps, schema_editor):
    Entry = apps.get_model('learning_logs', 'Entry')
    for e in Entry.objects.all():
        if not e.owner:
            e.owner = e.topic.owner
            e.save(update_fields=['owner'])


class Migration(migrations.Migration):

    dependencies = [
        ('learning_logs', '0004_privacy_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='entry',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(set_entry_owner_from_topic, migrations.RunPython.noop),
    ]
