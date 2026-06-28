from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vision", "0004_deteccion_origen_imagen_revisada_imagen_revisada_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="vuelo",
            name="tiles_total",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="vuelo",
            name="tiles_procesados",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
