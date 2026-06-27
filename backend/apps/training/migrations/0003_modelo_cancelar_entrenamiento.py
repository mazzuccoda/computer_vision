from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0002_modelo_augmentation_finetuning"),
    ]

    operations = [
        migrations.AddField(
            model_name="modeloentrenado",
            name="celery_task_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="modeloentrenado",
            name="estado",
            field=models.CharField(
                choices=[
                    ("pendiente", "Pendiente"),
                    ("preparando", "Preparando dataset"),
                    ("entrenando", "Entrenando"),
                    ("completado", "Completado"),
                    ("error", "Error"),
                    ("cancelado", "Cancelado"),
                ],
                default="pendiente",
                max_length=20,
            ),
        ),
    ]
