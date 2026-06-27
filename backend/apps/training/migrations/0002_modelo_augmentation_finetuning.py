from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="modeloentrenado",
            name="parametros_augmentation",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Augmentations YOLO usadas (flipud, degrees, hsv_v, "
                    "mosaic, mixup, ...). Vacío = defaults de Ultralytics."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="modeloentrenado",
            name="base_model",
            field=models.CharField(
                choices=[
                    ("yolov8n.pt", "YOLOv8 Nano (más rápido, CPU)"),
                    ("yolov8s.pt", "YOLOv8 Small (mejor recall)"),
                    ("yolov8m.pt", "YOLOv8 Medium"),
                    ("activo", "Modelo activo actual (fine-tuning)"),
                ],
                default="yolov8n.pt",
                max_length=20,
            ),
        ),
    ]
