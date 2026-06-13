from django.contrib import admin

from .models import Campo, Deteccion, Imagen, Modulo, Vuelo


@admin.register(Campo)
class CampoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "ubicacion", "creado_en")
    search_fields = ("nombre", "ubicacion")


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "campo", "creado_en")
    list_filter = ("campo",)
    search_fields = ("nombre",)


@admin.register(Vuelo)
class VueloAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre",
        "modulo",
        "estado",
        "total_plantas",
        "total_imagenes",
        "imagenes_procesadas",
        "fecha_vuelo",
    )
    list_filter = ("estado", "fecha_vuelo")
    search_fields = ("nombre",)


@admin.register(Imagen)
class ImagenAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre_original", "vuelo", "procesada", "conteo_plantas")
    list_filter = ("procesada",)


@admin.register(Deteccion)
class DeteccionAdmin(admin.ModelAdmin):
    list_display = ("id", "imagen", "clase", "confianza")
    list_filter = ("clase",)
