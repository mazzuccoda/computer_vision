import logging
import tempfile
from pathlib import Path

from celery import shared_task
from django.core.files import File
from django.utils import timezone

logger = logging.getLogger(__name__)


def _modelo_activo():
    from apps.training.models import ModeloEntrenado

    return ModeloEntrenado.objects.filter(activo=True).first()


def _activar_modelo(modelo) -> None:
    """Hot-swap: marca el modelo activo y recarga el YOLOService (igual que
    el endpoint manual de activación en apps.training)."""
    from django.core.cache import cache

    modelo.activo = True
    modelo.save()
    cache.set("yolo_model_reload", modelo.id, timeout=60)
    from services.yolo_service import YOLOService

    YOLOService.get_instance().reload_model()


@shared_task(bind=True, max_retries=0, queue="training")
def retrain_from_corrections_task(self, ciclo_id: int) -> dict:
    from apps.feedback.models import (
        CicloReentrenamiento,
        ConfiguracionReentrenamiento,
    )
    from apps.training.models import DatasetEntrenamiento, ModeloEntrenado
    from apps.training.tasks import ejecutar_entrenamiento
    from apps.vision.models import Imagen
    from services.correction_dataset_service import (
        CorrectionDatasetError,
        CorrectionDatasetService,
    )

    ciclo = CicloReentrenamiento.objects.get(id=ciclo_id)
    config = ConfiguracionReentrenamiento.get_solo()

    try:
        # 1) Construir dataset desde las imágenes revisadas
        ciclo.estado = CicloReentrenamiento.Estado.CONSTRUYENDO
        ciclo.save(update_fields=["estado"])

        imagenes = list(
            Imagen.objects.filter(revisada=True)
            .prefetch_related("detecciones")
            .order_by("id")
        )
        ts = timezone.now().strftime("%Y%m%d_%H%M%S")
        tmp_zip = Path(tempfile.gettempdir()) / f"correcciones_{ts}.zip"
        info = CorrectionDatasetService.construir_zip(imagenes, tmp_zip)

        dataset = DatasetEntrenamiento(
            nombre=f"Correcciones {ts}",
            formato=DatasetEntrenamiento.Formato.YOLO,
        )
        with open(tmp_zip, "rb") as fh:
            dataset.archivo.save(f"correcciones_{ts}.zip", File(fh), save=False)
        dataset.num_imagenes = info["num_imagenes"]
        dataset.clases = info["clases"]
        dataset.save()
        tmp_zip.unlink(missing_ok=True)

        ciclo.dataset = dataset
        ciclo.num_imagenes = info["num_imagenes"]
        ciclo.num_anotaciones = info["num_anotaciones"]
        ciclo.save(update_fields=["dataset", "num_imagenes", "num_anotaciones"])

        # 2) Crear y entrenar el modelo
        ciclo.estado = CicloReentrenamiento.Estado.ENTRENANDO
        ciclo.save(update_fields=["estado"])

        modelo = ModeloEntrenado.objects.create(
            nombre=f"Reentrenado {ts}",
            dataset=dataset,
            base_model=config.base_model,
            epochs=config.epochs,
        )
        ciclo.modelo = modelo
        ciclo.save(update_fields=["modelo"])

        activo = _modelo_activo()
        map50_anterior = None
        if activo and activo.metricas:
            map50_anterior = activo.metricas.get("map50")

        ejecutar_entrenamiento(modelo)
        modelo.refresh_from_db()

        # 3) Evaluar mejora (gate por mAP50)
        ciclo.estado = CicloReentrenamiento.Estado.EVALUANDO
        map50_nuevo = (modelo.metricas or {}).get("map50")
        ciclo.map50_anterior = map50_anterior
        ciclo.map50_nuevo = map50_nuevo
        ciclo.save(
            update_fields=["estado", "map50_anterior", "map50_nuevo"]
        )

        debe_activar = False
        motivo = ""
        if not config.auto_activar_modelo:
            motivo = "auto-activación desactivada en configuración."
        elif activo is None:
            debe_activar = True
            motivo = "no había modelo activo previo."
        elif map50_anterior is None:
            debe_activar = True
            motivo = "el modelo activo no tenía mAP50 registrado."
        elif map50_nuevo is not None and (
            map50_nuevo >= map50_anterior + config.margen_map50
        ):
            debe_activar = True
            motivo = (
                f"mAP50 {map50_nuevo:.4f} >= "
                f"{map50_anterior:.4f} + {config.margen_map50}."
            )
        else:
            motivo = (
                f"mAP50 nuevo {map50_nuevo} no supera al activo "
                f"{map50_anterior} (+{config.margen_map50}); no se activa."
            )

        if debe_activar:
            _activar_modelo(modelo)
            ciclo.activado = True
            ciclo.estado = CicloReentrenamiento.Estado.ACTIVADO
        else:
            ciclo.estado = CicloReentrenamiento.Estado.COMPLETADO

        ciclo.mensaje = motivo
        ciclo.completado_en = timezone.now()
        ciclo.save()

        # 4) Resetear contador de correcciones acumuladas
        config.correcciones_acumuladas = 0
        config.ultimo_reentrenamiento = timezone.now()
        config.save(
            update_fields=["correcciones_acumuladas", "ultimo_reentrenamiento"]
        )

        return {
            "status": ciclo.estado,
            "ciclo_id": ciclo.id,
            "modelo_id": modelo.id,
            "activado": ciclo.activado,
            "map50_anterior": map50_anterior,
            "map50_nuevo": map50_nuevo,
        }

    except CorrectionDatasetError as e:
        ciclo.estado = CicloReentrenamiento.Estado.ERROR
        ciclo.mensaje = str(e)
        ciclo.completado_en = timezone.now()
        ciclo.save()
        return {"status": "error", "ciclo_id": ciclo.id, "error": str(e)}

    except Exception as exc:  # noqa: BLE001
        ciclo.estado = CicloReentrenamiento.Estado.ERROR
        ciclo.mensaje = str(exc)
        ciclo.completado_en = timezone.now()
        ciclo.save()
        logger.exception("Fallo el ciclo de reentrenamiento %s", ciclo_id)
        return {"status": "error", "ciclo_id": ciclo.id, "error": str(exc)}
