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
    @staticmethod
    def entrenar(
        base: str,
        data_yaml: str,
        epochs: int,
        imgsz: int,
        patience: int,
        output_name: str,
        on_epoch_end=None,
    ) -> TrainingResult:
        """
        Ejecuta YOLO.train() con callback de progreso por época.
        Returns TrainingResult con path a best.pt y métricas.
        """
        from ultralytics import YOLO

        model = YOLO(base)
        output_dir = Path(settings.MEDIA_ROOT) / "training_runs" / output_name

        if on_epoch_end:
            model.add_callback("on_train_epoch_end", on_epoch_end)

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
