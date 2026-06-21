import logging
from pathlib import Path

from django.conf import settings
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class YOLOService:
    """Carga el modelo YOLO activo seleccionado desde la base de datos."""

    _instance = None
    _model = None
    _model_path = None
    _active_model_id = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_active_model(self):
        from apps.training.models import ModeloEntrenado

        return (
            ModeloEntrenado.objects
            .filter(
                activo=True,
                estado=ModeloEntrenado.Estado.COMPLETADO,
                archivo_pesos__isnull=False,
            )
            .exclude(archivo_pesos="")
            .first()
        )

    def _get_active_model_path(self):
        modelo = self._get_active_model()

        if modelo and modelo.archivo_pesos:
            model_path = Path(settings.MEDIA_ROOT) / modelo.archivo_pesos.name

            if model_path.exists():
                return modelo.id, str(model_path)

            logger.error(
                "El modelo activo %s apunta a un archivo inexistente: %s",
                modelo.id,
                model_path,
            )

        fallback_model = "yolov8n.pt"
        logger.warning("No hay modelo activo válido. Usando fallback: %s", fallback_model)
        return None, fallback_model

    def _load_model(self):
        active_model_id, model_path = self._get_active_model_path()

        logger.info("Cargando YOLO desde: %s", model_path)

        self._active_model_id = active_model_id
        self._model_path = model_path
        return YOLO(model_path)

    @property
    def model(self):
        active_model_id, model_path = self._get_active_model_path()

        if (
            self._model is None
            or self._active_model_id != active_model_id
            or self._model_path != model_path
        ):
            logger.info("Cambio de modelo detectado. Recargando YOLO.")
            self._model = None
            self._active_model_id = active_model_id
            self._model_path = model_path
            self._model = YOLO(model_path)

        return self._model

    def reload_model(self):
        logger.info("Forzando recarga del modelo YOLO activo")
        self._model = None
        self._model_path = None
        self._active_model_id = None
        return self.model

    def process_image_with_yolo(self, image_path: str, confidence: float = 0.5) -> dict:
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
                "modelo_usado": self._model_path,
                "modelo_activo_id": self._active_model_id,
            }

        except Exception as exc:
            logger.error("Error procesando imagen %s: %s", image_path, exc)
            raise
