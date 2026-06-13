from django.db import models


class Campo(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    ubicacion = models.CharField(max_length=300, blank=True)
    # TODO FASE 2: Reemplazar latitud/longitud por PointField de PostGIS
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return self.nombre


class Modulo(models.Model):
    campo = models.ForeignKey(
        Campo, on_delete=models.CASCADE, related_name="modulos"
    )
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return self.nombre


class Vuelo(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "Procesando"
        COMPLETADO = "completado", "Completado"
        ERROR = "error", "Error"

    modulo = models.ForeignKey(
        Modulo, on_delete=models.CASCADE, related_name="vuelos"
    )
    nombre = models.CharField(max_length=200)
    fecha_vuelo = models.DateField()
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    total_plantas = models.IntegerField(default=0)
    total_imagenes = models.IntegerField(default=0)
    imagenes_procesadas = models.IntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return self.nombre

    @property
    def porcentaje_procesado(self) -> float:
        if self.total_imagenes == 0:
            return 0.0
        return round((self.imagenes_procesadas / self.total_imagenes) * 100, 1)


class Imagen(models.Model):
    vuelo = models.ForeignKey(
        Vuelo, on_delete=models.CASCADE, related_name="imagenes"
    )
    archivo = models.ImageField(upload_to="imagenes/%Y/%m/%d/")
    nombre_original = models.CharField(max_length=255)
    procesada = models.BooleanField(default=False)
    conteo_plantas = models.IntegerField(default=0)
    # TODO FASE 3: Agregar campo geotiff_path para archivos GeoTIFF georreferenciados
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en"]

    def __str__(self) -> str:
        return self.nombre_original


class Deteccion(models.Model):
    imagen = models.ForeignKey(
        Imagen, on_delete=models.CASCADE, related_name="detecciones"
    )
    confianza = models.FloatField()
    x_min = models.FloatField()
    y_min = models.FloatField()
    x_max = models.FloatField()
    y_max = models.FloatField()
    clase = models.CharField(max_length=100, default="planta")

    def __str__(self) -> str:
        return f"{self.clase} ({self.confianza:.2f})"


# TODO FASE 4: Agregar modelo HistorialVuelo para comparación entre vuelos
