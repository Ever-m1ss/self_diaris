from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('learning_logs', '0008_attachment_links'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attachment',
            name='entry',
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                to='learning_logs.entry',
                null=True,
                blank=True,
            ),
        ),
    ]
