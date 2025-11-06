from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('learning_logs', '0007_attachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='attachment',
            name='comment',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, to='learning_logs.comment'),
        ),
        migrations.AddField(
            model_name='attachment',
            name='topic',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, to='learning_logs.topic'),
        ),
    ]
