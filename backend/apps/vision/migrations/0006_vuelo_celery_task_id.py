from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vision", "0005_vuelo_tiles_progreso"),
    ]

    operations = [
        migrations.AddField(
            model_name="vuelo",
            name="celery_task_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
