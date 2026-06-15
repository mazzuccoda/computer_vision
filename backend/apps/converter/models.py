from django.db import models

from apps.vision.models import Imagen


class SesionConversion(models.Model):
    """
    Representa una sesión de conversión: un GeoTIFF de entrada
    que se fragmenta en tiles JPG listos para CVAT.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "Procesando"
        COMPLETADO = "completado", "Completado"
        ERROR = "error", "Error"

    class FuenteTiff(models.TextChoices):
        UPLOAD = "upload", "Upload directo"
        VUELO = "vuelo", "Imagen de vuelo existente"

    nombre = models.CharField(max_length=200)
    fuente = models.CharField(
        max_length=10, choices=FuenteTiff.choices, default=FuenteTiff.UPLOAD
    )

    # Fuente A: upload directo
    archivo_tiff = models.FileField(
        upload_to="tiff_uploads/%Y/%m/", null=True, blank=True
    )

    # Fuente B: imagen de vuelo existente
    imagen_vuelo = models.ForeignKey(
        Imagen,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sesiones_conversion",
    )

    # Parámetros de conversión
    tile_size = models.IntegerField(
        default=640, help_text="Tamaño del tile en píxeles (ancho y alto)"
    )
    overlap_px = models.IntegerField(
        default=64, help_text="Solapamiento entre tiles en píxeles"
    )
    calidad_jpg = models.IntegerField(
        default=85, help_text="Calidad JPEG (1-100)"
    )
    saltar_vacios = models.BooleanField(
        default=True,
        help_text="Ignorar tiles sin contenido (fondo negro > 80%)",
    )

    # Estado y progreso
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    total_tiles = models.IntegerField(default=0)
    tiles_procesados = models.IntegerField(default=0)
    error_mensaje = models.TextField(blank=True)

    # Artefactos generados
    directorio_tiles = models.CharField(max_length=500, blank=True)
    archivo_zip = models.FileField(
        upload_to="zips_tiles/%Y/%m/", null=True, blank=True
    )
    metadatos_geo = models.JSONField(default=dict)
    # Estructura: {crs, bounds: {west, south, east, north}, ancho_px, alto_px,
    #             bandas, res_m_per_px, tile_size, overlap_px, tiles: [...]}

    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    completado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    @property
    def porcentaje(self) -> float:
        if self.total_tiles == 0:
            return 0.0
        return round(self.tiles_procesados / self.total_tiles * 100, 1)

    @property
    def nombre_archivo_fuente(self) -> str:
        if self.fuente == self.FuenteTiff.UPLOAD and self.archivo_tiff:
            return self.archivo_tiff.name.split("/")[-1]
        if self.fuente == self.FuenteTiff.VUELO and self.imagen_vuelo:
            return self.imagen_vuelo.nombre_original
        return "desconocido"

    def __str__(self) -> str:
        return f"{self.nombre} — {self.total_tiles} tiles — {self.estado}"
