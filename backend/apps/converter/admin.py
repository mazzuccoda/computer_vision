from django.contrib import admin

from .models import SesionConversion


@admin.register(SesionConversion)
class SesionConversionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre",
        "fuente",
        "estado",
        "total_tiles",
        "tiles_procesados",
        "creado_en",
    )
    list_filter = ("estado", "fuente")
    search_fields = ("nombre",)
