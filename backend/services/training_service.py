import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# TODO FASE 3: soporte GPU (device='0'), multi-GPU
# TODO FASE 4: auto-activar si mAP50 supera al modelo activo actual


class TrainingResult:
    def __init__(self, best_pt_path: str, metrics: dict):
        self.best_pt_path = best_pt_path
        self.metrics = metrics


class TrainingService:
    # Augmentations por defecto pensadas para fotos aéreas de drones: el aparato
    # vuela en cualquier dirección, así que rotación/flips ayudan, y la
    # variación de brillo (hsv_v) cubre distintas horas/sombras. Sólo se usan si
    # el modelo no trae parámetros explícitos.
    DEFAULT_AUGMENTATION = {
        "flipud": 0.5,
        "fliplr": 0.5,
        "degrees": 45.0,
        "translate": 0.1,
        "scale": 0.3,
        "hsv_h": 0.015,
        "hsv_s": 0.5,
        "hsv_v": 0.3,
        "mosaic": 1.0,
        "mixup": 0.1,
    }

    @staticmethod
    def entrenar(
        base: str,
        data_yaml: str,
        epochs: int,
        imgsz: int,
        patience: int,
        output_name: str,
        on_epoch_end=None,
        augmentation_params: dict | None = None,
    ) -> TrainingResult:
        """
        Ejecuta YOLO.train() con callback de progreso por época.

        ``base`` puede ser un modelo preentrenado (``yolov8s.pt``) o la ruta a un
        ``best.pt`` existente para fine-tuning (transfer learning).

        ``augmentation_params`` sobrescribe los augmentations por defecto; las
        claves no provistas usan ``DEFAULT_AUGMENTATION``.

        Returns TrainingResult con path a best.pt y métricas.
        """
        from ultralytics import YOLO

        model = YOLO(base)
        output_dir = Path(settings.MEDIA_ROOT) / "training_runs" / output_name

        if on_epoch_end:
            model.add_callback("on_train_epoch_end", on_epoch_end)

        aug = {**TrainingService.DEFAULT_AUGMENTATION, **(augmentation_params or {})}

        results = model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            patience=patience,
            project=str(output_dir),
            name="train",
            exist_ok=True,
            verbose=False,
            plots=True,
            **aug,
        )

        best_pt = output_dir / "train" / "weights" / "best.pt"
        if not best_pt.exists():
            raise FileNotFoundError(f"No se encontró best.pt en {best_pt}")

        metrics = {}
        try:
            rd = results.results_dict
            metrics = {
                "map50": float(rd.get("metrics/mAP50(B)", 0)),
                "map50_95": float(rd.get("metrics/mAP50-95(B)", 0)),
                "precision": float(rd.get("metrics/precision(B)", 0)),
                "recall": float(rd.get("metrics/recall(B)", 0)),
                "fitness": float(rd.get("fitness", 0)),
            }
        except Exception as e:
            logger.warning(f"No se pudieron parsear métricas: {e}")

        return TrainingResult(str(best_pt), metrics)
