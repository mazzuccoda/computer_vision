import logging

from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)


def _hay_ciclo_en_curso() -> bool:
    from .models import CicloReentrenamiento

    en_curso = [
        CicloReentrenamiento.Estado.PENDIENTE,
        CicloReentrenamiento.Estado.CONSTRUYENDO,
        CicloReentrenamiento.Estado.ENTRENANDO,
        CicloReentrenamiento.Estado.EVALUANDO,
    ]
    return CicloReentrenamiento.objects.filter(estado__in=en_curso).exists()


def lanzar_ciclo(disparador: str):
    """Crea un CicloReentrenamiento y encola la task. Devuelve el ciclo o
    None si ya hay uno en curso."""
    from .models import (
        CicloReentrenamiento,
        ConfiguracionReentrenamiento,
    )
    from .tasks import retrain_from_corrections_task

    if _hay_ciclo_en_curso():
        return None

    config = ConfiguracionReentrenamiento.get_solo()
    ciclo = CicloReentrenamiento.objects.create(
        disparador=disparador,
        num_correcciones=config.correcciones_acumuladas,
    )
    retrain_from_corrections_task.apply_async(
        args=[ciclo.id], queue="training"
    )
    return ciclo


def registrar_correccion(n: int = 1) -> None:
    """
    Suma ``n`` al contador de correcciones acumuladas. Si está activo el
    auto-reentrenamiento y se alcanza el umbral (y no hay un ciclo en curso),
    dispara automáticamente un ciclo de reentrenamiento.
    """
    from .models import ConfiguracionReentrenamiento

    if n <= 0:
        return

    with transaction.atomic():
        config = ConfiguracionReentrenamiento.get_solo()
        ConfiguracionReentrenamiento.objects.filter(pk=config.pk).update(
            correcciones_acumuladas=F("correcciones_acumuladas") + n
        )
        config.refresh_from_db()

    if (
        config.auto_reentrenar
        and config.correcciones_acumuladas >= config.umbral_correcciones
    ):
        ciclo = lanzar_ciclo("auto")
        if ciclo:
            logger.info(
                "Auto-reentrenamiento disparado (ciclo %s) tras %s correcciones",
                ciclo.id,
                config.correcciones_acumuladas,
            )
