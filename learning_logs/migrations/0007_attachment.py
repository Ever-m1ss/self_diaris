from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('learning_logs', '0006_comment'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='attachments/%Y/%m/%d/')),
                ('original_name', models.CharField(max_length=255)),
                ('content_type', models.CharField(blank=True, max_length=100)),
                ('size', models.BigIntegerField(default=0)),
                ('is_public', models.BooleanField(default=False)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('entry', models.ForeignKey(on_delete=models.deletion.CASCADE, to='learning_logs.entry')),
                ('owner', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-uploaded_at']},
        ),
    ]
