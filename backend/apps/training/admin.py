from django.contrib import admin

from .models import DatasetEntrenamiento, ModeloEntrenado


@admin.register(DatasetEntrenamiento)
class DatasetEntrenamientoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre",
        "formato",
        "estado",
        "num_imagenes",
        "creado_en",
    )
    list_filter = ("formato", "estado")
    search_fields = ("nombre",)


@admin.register(ModeloEntrenado)
class ModeloEntrenadoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre",
        "version",
        "dataset",
        "base_model",
        "estado",
        "activo",
        "creado_en",
    )
    list_filter = ("estado", "activo", "base_model")
    search_fields = ("nombre", "version")
