import logging
import shutil
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def ejecutar_entrenamiento(modelo) -> dict:
    """
    Núcleo del entrenamiento (sin lógica de Celery/retry): valida el dataset,
    entrena, guarda los artefactos y deja el modelo en COMPLETADO o ERROR.

    Reutilizado por ``train_model_task`` y por el ciclo de reentrenamiento
    activo (apps.feedback). Devuelve {status, modelo_id, metricas}.
    Levanta la excepción original si el entrenamiento falla.
    """
    from apps.training.models import ModeloEntrenado
    from services.dataset_service import DatasetValidationError, DatasetService
    from services.training_service import TrainingService

    modelo_id = modelo.id
    try:
        # Fase 1: preparar dataset
        modelo.estado = ModeloEntrenado.Estado.PREPARANDO
        modelo.save(update_fields=["estado"])

        result_ds = DatasetService.validar_y_preparar(modelo.dataset)

        modelo.dataset.num_imagenes = result_ds["num_imagenes"]
        modelo.dataset.clases = result_ds["clases"]
        modelo.dataset.reporte_validacion = result_ds["reporte"]
        modelo.dataset.estado = "valido"
        modelo.dataset.save()

        # Fase 2: entrenar
        modelo.estado = ModeloEntrenado.Estado.ENTRENANDO
        modelo.save(update_fields=["estado"])

        def on_epoch_end(trainer):
            ModeloEntrenado.objects.filter(id=modelo_id).update(
                epoca_actual=trainer.epoch + 1
            )

        result = TrainingService.entrenar(
            base=modelo.base_model,
            data_yaml=result_ds["data_yaml_path"],
            epochs=modelo.epochs,
            imgsz=modelo.img_size,
            patience=modelo.patience,
            output_name=f"modelo_{modelo_id}_{modelo.version}",
            on_epoch_end=on_epoch_end,
        )

        # Fase 3: guardar artefactos
        dest_dir = Path(settings.MEDIA_ROOT) / "modelos"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"modelo_{modelo_id}_{modelo.version}_best.pt"
        shutil.copy2(result.best_pt_path, dest)

        # Copiar el data.yaml junto al run para incluirlo en el entregable.
        run_dir = (
            Path(settings.MEDIA_ROOT)
            / "training_runs"
            / f"modelo_{modelo_id}_{modelo.version}"
        )
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result_ds["data_yaml_path"], run_dir / "data.yaml")
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo copiar data.yaml al run: %s", e)

        modelo.archivo_pesos = str(dest.relative_to(settings.MEDIA_ROOT))
        modelo.metricas = result.metrics
        modelo.estado = ModeloEntrenado.Estado.COMPLETADO
        modelo.epoca_actual = modelo.epochs
        modelo.completado_en = timezone.now()
        modelo.save()

        return {
            "status": "completado",
            "modelo_id": modelo_id,
            "metricas": result.metrics,
        }

    except DatasetValidationError as e:
        modelo.estado = ModeloEntrenado.Estado.ERROR
        modelo.error_mensaje = f"Dataset inválido: {e}"
        modelo.save(update_fields=["estado", "error_mensaje"])
        raise

    except Exception as exc:
        modelo.estado = ModeloEntrenado.Estado.ERROR
        modelo.error_mensaje = str(exc)
        modelo.save(update_fields=["estado", "error_mensaje"])
        raise


@shared_task(bind=True, max_retries=1, queue="training")
def train_model_task(self, modelo_id: int) -> dict:
    from apps.training.models import ModeloEntrenado
    from services.dataset_service import DatasetValidationError

    modelo = ModeloEntrenado.objects.get(id=modelo_id)

    try:
        return ejecutar_entrenamiento(modelo)
    except DatasetValidationError:
        raise  # No reintentar errores de validación
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
