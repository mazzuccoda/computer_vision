yolo.py (import logging
from pathlib import Path

from django.conf import settings
from ultralytics import YOLO

logger = logging.getLogger(_name_)


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
        # 1. Modelo activo entrenado desde la DB (módulo de entrenamiento).
        try:
            from apps.training.models import ModeloEntrenado

            activo = ModeloEntrenado.objects.filter(
                activo=True, estado="completado"
            ).first()
            if activo and activo.archivo_pesos:
                p = Path(settings.MEDIA_ROOT) / activo.archivo_pesos.name
                if p.exists():
                    logger.info("Cargando modelo YOLO activo: %s", p)
                    return YOLO(str(p))
        except Exception:
            pass

        # 2. best.pt local en MODELS_PATH.
        custom_model = Path(settings.MODELS_PATH) / "best.pt"
        if custom_model.exists():
            logger.info("Cargando modelo YOLO desde: %s", custom_model)
            return YOLO(str(custom_model))

        # 3. Fallback genérico.
        logger.info("Cargando modelo YOLO fallback: yolov8n.pt")
        return YOLO("yolov8n.pt")

    def reload_model(self) -> None:
        """Fuerza la recarga del modelo en el próximo acceso a .model."""
        self._model = None

    def check_reload_signal(self) -> None:
        """Verifica la señal de recarga en Redis (otro proceso activó un modelo)."""
        try:
            from django.core.cache import cache

            if cache.get("yolo_model_reload"):
                cache.delete("yolo_model_reload")
                self.reload_model()
        except Exception:
            pass

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
            self.check_reload_signal()
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
    # TODO FASE 4: Agregar método retrain_model() para reentrenamiento con correcciones manuales)
