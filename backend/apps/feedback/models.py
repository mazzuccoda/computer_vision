from django.db import models


class ConfiguracionReentrenamiento(models.Model):
    """
    Configuración singleton (pk=1) del ciclo de reentrenamiento activo.

    Acumula cuántas correcciones manuales se hicieron desde el último
    reentrenamiento; cuando llega a ``umbral_correcciones`` y
    ``auto_reentrenar`` está activo, se encola un ciclo automáticamente.
    """

    auto_reentrenar = models.BooleanField(
        default=True,
        help_text="Encolar un reentrenamiento al alcanzar el umbral.",
    )
    umbral_correcciones = models.IntegerField(default=50)
    # Si está activo, al terminar el entrenamiento se compara el mAP50 del
    # modelo nuevo con el del activo y solo se activa si es igual o mejor
    # (propuesta superadora). El disparo manual puede saltarse este gate.
    auto_activar_modelo = models.BooleanField(default=True)
    margen_map50 = models.FloatField(
        default=0.0,
        help_text="mAP50 nuevo debe superar al activo por este margen.",
    )
    epochs = models.IntegerField(default=50)
    base_model = models.CharField(max_length=20, default="yolov8n.pt")

    correcciones_acumuladas = models.IntegerField(default=0)
    ultimo_reentrenamiento = models.DateTimeField(null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de reentrenamiento"
        verbose_name_plural = "Configuración de reentrenamiento"

    def __str__(self) -> str:
        return (
            f"Config reentrenamiento (umbral={self.umbral_correcciones}, "
            f"acumuladas={self.correcciones_acumuladas})"
        )

    @classmethod
    def get_solo(cls) -> "ConfiguracionReentrenamiento":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CicloReentrenamiento(models.Model):
    """Una corrida de reentrenamiento disparada por correcciones manuales."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONSTRUYENDO = "construyendo", "Construyendo dataset"
        ENTRENANDO = "entrenando", "Entrenando"
        EVALUANDO = "evaluando", "Evaluando mejora"
        ACTIVADO = "activado", "Completado y activado"
        COMPLETADO = "completado", "Completado (no activado)"
        ERROR = "error", "Error"

    class Disparador(models.TextChoices):
        AUTO = "auto", "Automático (umbral)"
        MANUAL = "manual", "Manual"

    disparador = models.CharField(
        max_length=10, choices=Disparador.choices, default=Disparador.MANUAL
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    num_correcciones = models.IntegerField(default=0)
    num_imagenes = models.IntegerField(default=0)
    num_anotaciones = models.IntegerField(default=0)

    dataset = models.ForeignKey(
        "training.DatasetEntrenamiento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ciclos",
    )
    modelo = models.ForeignKey(
        "training.ModeloEntrenado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ciclos",
    )

    map50_anterior = models.FloatField(null=True, blank=True)
    map50_nuevo = models.FloatField(null=True, blank=True)
    activado = models.BooleanField(default=False)
    mensaje = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    completado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "Ciclo de reentrenamiento"
        verbose_name_plural = "Ciclos de reentrenamiento"

    def __str__(self) -> str:
        return f"Ciclo {self.id} ({self.disparador}) — {self.estado}"
