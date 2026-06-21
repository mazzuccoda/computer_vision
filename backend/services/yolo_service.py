import logging
from pathlib import Path

from django.conf import settings
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class YOLOService:
    """Singleton wrapper around an Ultralytics YOLO model."""

    _instance: "YOLOService | None" = None
    _model: YOLO | None = None

    @classmethod
    def get_instance(cls) -> "YOLOService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self) -> YOLO:
        custom_model = Path(settings.MODELS_PATH) / "best.pt"
        fallback_model = "yolov8n.pt"

        model_path = str(custom_model) if custom_model.exists() else fallback_model
        logger.info("Cargando modelo YOLO desde: %s", model_path)

        return YOLO(model_path)

    @property
    def model(self) -> YOLO:
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def process_image_with_yolo(
        self,
        image_path: str,
        confidence: float = 0.5,
    ) -> dict:
        """
        Procesa una imagen y retorna detecciones.

        Returns:
            {
                'total_detecciones': int,
                'detecciones': [
                    {
                        'confianza': float,
                        'x_min': float, 'y_min': float,
                        'x_max': float, 'y_max': float,
                        'clase': str
                    }
                ]
            }
        """
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

    # TODO FASE 3: Agregar método process_ndvi() para análisis de índice de vegetación
    # TODO FASE 4: Agregar método retrain_model() para reentrenamiento con correcciones manuales
