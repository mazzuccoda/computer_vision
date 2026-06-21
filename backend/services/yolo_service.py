import logging
from pathlib import Path

from django.conf import settings
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class YOLOService:
    """Singleton wrapper around an Ultralytics YOLO model."""

    _instance = None
    _model = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self):
        custom_model = Path(settings.MODELS_PATH) / "best.pt"
        fallback_model = "yolov8n.pt"

        model_path = str(custom_model) if custom_model.exists() else fallback_model

        if custom_model.exists():
            logger.info("Cargando modelo YOLO activo desde: %s", model_path)
        else:
            logger.warning(
                "No se encontró modelo activo en %s. Usando fallback: %s",
                custom_model,
                fallback_model,
            )

        return YOLO(model_path)

    @property
    def model(self):
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def reload_model(self):
        logger.info("Recargando modelo YOLO activo")
        self._model = None
        return self.model

    def process_image_with_yolo(
        self,
        image_path: str,
        confidence: float = 0.5,
    ) -> dict:
        try:
            results = self.model(image_path, conf=confidence)
            detecciones = []

            for result in results:
                for box in result.boxes:
                    detecciones.append(
                        {
                            "confianza": float(box.conf[0]),
                            "x_min": float(box.xyxy[0][0]),
                            "y_min": float(box.xyxy[0][1]),
                            "x_max": float(box.xyxy[0][2]),
                            "y_max": float(box.xyxy[0][3]),
                            "clase": result.names[int(box.cls[0])],
                        }
                    )

            return {
                "total_detecciones": len(detecciones),
                "detecciones": detecciones,
            }

        except Exception as exc:
            logger.error("Error procesando imagen %s: %s", image_path, exc)
            raise
