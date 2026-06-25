from django.contrib import admin

from .models import CicloReentrenamiento, ConfiguracionReentrenamiento


@admin.register(ConfiguracionReentrenamiento)
class ConfiguracionReentrenamientoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "auto_reentrenar",
        "umbral_correcciones",
        "correcciones_acumuladas",
        "auto_activar_modelo",
        "ultimo_reentrenamiento",
    )


@admin.register(CicloReentrenamiento)
class CicloReentrenamientoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "disparador",
        "estado",
        "num_correcciones",
        "num_imagenes",
        "map50_anterior",
        "map50_nuevo",
        "activado",
        "creado_en",
    )
    list_filter = ("estado", "disparador", "activado")
