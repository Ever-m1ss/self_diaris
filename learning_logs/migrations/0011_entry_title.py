from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('learning_logs', '0010_attachment_extra_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='entry',
            name='title',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
