from django.db import models


class DatasetEntrenamiento(models.Model):
    class Formato(models.TextChoices):
        YOLO = "yolo", "YOLO Ultralytics (recomendado)"
        CVAT_XML = "cvat_xml", "CVAT for Images 1.1 XML"
        COCO = "coco", "COCO JSON"

    class Estado(models.TextChoices):
        SUBIDO = "subido", "Subido"
        VALIDANDO = "validando", "Validando"
        VALIDO = "valido", "Válido"
        INVALIDO = "invalido", "Inválido"

    nombre = models.CharField(max_length=200)
    archivo = models.FileField(upload_to="datasets/%Y/%m/")
    formato = models.CharField(
        max_length=20, choices=Formato.choices, default=Formato.YOLO
    )
    num_imagenes = models.IntegerField(default=0)
    clases = models.JSONField(default=list)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.SUBIDO
    )
    reporte_validacion = models.JSONField(default=dict)
    # Estructura: {total_imagenes, total_anotaciones,
    #              distribucion_por_clase: {clase: count}, warnings: []}
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.num_imagenes} imgs)"


class ModeloEntrenado(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PREPARANDO = "preparando", "Preparando dataset"
        ENTRENANDO = "entrenando", "Entrenando"
        COMPLETADO = "completado", "Completado"
        ERROR = "error", "Error"
        CANCELADO = "cancelado", "Cancelado"

    # Estados en los que el entrenamiento sigue en curso (se puede cancelar).
    ESTADOS_EN_PROGRESO = ("pendiente", "preparando", "entrenando")

    class ModeloBase(models.TextChoices):
        NANO = "yolov8n.pt", "YOLOv8 Nano (más rápido, CPU)"
        SMALL = "yolov8s.pt", "YOLOv8 Small (mejor recall)"
        MEDIUM = "yolov8m.pt", "YOLOv8 Medium"
        ACTIVO = "activo", "Modelo activo actual (fine-tuning)"

    nombre = models.CharField(max_length=200)
    version = models.CharField(max_length=20, blank=True)  # v1, v2, ... (auto)
    dataset = models.ForeignKey(
        DatasetEntrenamiento,
        on_delete=models.PROTECT,
        related_name="modelos",
    )
    base_model = models.CharField(
        max_length=20, choices=ModeloBase.choices, default=ModeloBase.NANO
    )
    epochs = models.IntegerField(default=50)
    img_size = models.IntegerField(default=640)
    patience = models.IntegerField(default=10)
    parametros_augmentation = models.JSONField(
        default=dict,
        blank=True,
        help_text="Augmentations YOLO usadas (flipud, degrees, hsv_v, "
        "mosaic, mixup, ...). Vacío = defaults de Ultralytics.",
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    epoca_actual = models.IntegerField(default=0)
    metricas = models.JSONField(default=dict)
    # Estructura: {map50, map50_95, precision, recall, fitness}
    archivo_pesos = models.FileField(
        upload_to="modelos/", null=True, blank=True
    )
    activo = models.BooleanField(default=False)
    notas = models.TextField(blank=True)
    error_mensaje = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    completado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    @property
    def porcentaje(self) -> float:
        if self.epochs == 0:
            return 0.0
        return round(self.epoca_actual / self.epochs * 100, 1)

    def save(self, *args, **kwargs):
        if not self.version:
            count = ModeloEntrenado.objects.filter(dataset=self.dataset).count()
            self.version = f"v{count + 1}"
        if self.activo:
            ModeloEntrenado.objects.exclude(pk=self.pk).update(activo=False)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.nombre} {self.version} — {self.estado}"
