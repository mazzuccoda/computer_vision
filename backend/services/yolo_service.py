import logging
import tempfile
from pathlib import Path

from django.conf import settings
from ultralytics import YOLO

logger = logging.getLogger(__name__)

TIFF_EXTENSIONS = {".tif", ".tiff"}

# Debe coincidir con el tamaño de tile usado durante el ENTRENAMIENTO del
# modelo. Si el modelo se reentrena con otro tamaño, actualizar este valor.
# Configurables por settings/env para poder ajustar sin tocar código.
TILE_SIZE_INFERENCIA = getattr(settings, "YOLO_TILE_SIZE", 640)
# Mayor overlap reduce plantas perdidas en los bordes entre tiles (a costa de
# más tiles/tiempo); el NMS entre tiles luego elimina los duplicados del borde.
TILE_OVERLAP_INFERENCIA = getattr(settings, "YOLO_TILE_OVERLAP", 64)

# IoU del NMS interno de YOLO en cada inferencia. El default de Ultralytics
# (0.7) es permisivo y deja boxes duplicados sobre la misma planta; bajarlo los
# elimina. Si plantas muy juntas se fusionan/pierden, subirlo.
NMS_IOU_INFERENCIA = getattr(settings, "YOLO_IOU_INFERENCIA", 0.5)

# IoU para deduplicar detecciones repetidas en las zonas de solapamiento entre
# tiles vecinos (evita contar la misma planta 2-4 veces).
NMS_IOU_TILES = getattr(settings, "YOLO_IOU_TILES", 0.45)

# Intersección sobre el área del box MÁS CHICO (IoS). El NMS por IoU no elimina
# un box contenido dentro de otro más grande (su IoU = inter/union es bajo por
# la diferencia de tamaño), así que la misma planta queda con un box grande y
# otros chicos anidados. Si un box queda mayormente dentro de otro de más
# confianza (IoS >= umbral) se suprime. Poner 0 para desactivar; bajarlo es más
# agresivo (puede fusionar plantas muy juntas).
NMS_IOS_DEDUP = getattr(settings, "YOLO_IOS_DEDUP", 0.6)

# Test-Time Augmentation: infiere sobre variantes (flips/escala) y combina;
# mejora el recall (menos plantas no detectadas) a costa de ~2-3x de tiempo.
TTA_INFERENCIA = getattr(settings, "YOLO_TTA", False)

# NMS agnóstico de clase: suprime solapamientos aunque sean de clases distintas
# (útil si una misma planta se detecta como 'planta' y otra clase a la vez).
AGNOSTIC_NMS = getattr(settings, "YOLO_AGNOSTIC_NMS", False)


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
        """Procesa una imagen y retorna detecciones.

        JPG/PNG: inferencia directa (comportamiento sin cambios).

        TIFF: SIEMPRE se trocea primero en tiles de TILE_SIZE_INFERENCIA con
        TiffService (el mismo servicio del módulo Convertir TIFF) y se infiere
        tile por tile. Esto reproduce el tamaño relativo de planta visto durante
        el entrenamiento; sin trocear, YOLO reescala el TIFF completo y las
        plantas quedan en 2-3 píxeles (0 detecciones).
        """
        ext = Path(image_path).suffix.lower()
        try:
            if ext in TIFF_EXTENSIONS:
                detecciones = self._detecciones_tiff_por_tiles(image_path, confidence)
            else:
                detecciones = self._detecciones_estandar(image_path, confidence)

            return {
                "total_detecciones": len(detecciones),
                "detecciones": detecciones,
                "modelo_usado": self._model_path,
                "modelo_activo_id": self._active_model_id,
            }

        except Exception as exc:
            logger.error("Error procesando imagen %s: %s", image_path, exc)
            raise

    def _inferir(self, source, confidence: float):
        """Llama al modelo con los parámetros de NMS/TTA centralizados, para que
        la inferencia directa (JPG/PNG) y la de cada tile sean consistentes."""
        return self.model(
            source,
            conf=confidence,
            iou=NMS_IOU_INFERENCIA,
            augment=TTA_INFERENCIA,
            agnostic_nms=AGNOSTIC_NMS,
        )

    def _detecciones_estandar(self, image_path: str, confidence: float) -> list[dict]:
        """JPG/PNG: inferencia directa con NMS más estricto para evitar boxes
        duplicados sobre la misma planta.

        Además del NMS interno de YOLO (por IoU) se aplica una pasada propia que
        también suprime boxes anidados (por IoS), que el IoU no elimina.
        """
        results = self._inferir(image_path, confidence)
        return self._nms(
            self._parsear_resultados(results), NMS_IOU_TILES, NMS_IOS_DEDUP
        )

    def _detecciones_tiff_por_tiles(self, image_path: str, confidence: float) -> list[dict]:
        """Trocea el TIFF, infiere en cada tile y combina las detecciones sumando
        el offset de píxel de cada tile para devolver coordenadas en el sistema
        de la imagen TIFF original."""
        from services.tiff_service import TiffService

        todas_detecciones: list[dict] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            logger.info(
                "Troceando TIFF para inferencia (tile_size=%s, overlap=%s): %s",
                TILE_SIZE_INFERENCIA,
                TILE_OVERLAP_INFERENCIA,
                image_path,
            )

            resultado_tiles = TiffService.generar_tiles(
                tiff_path=image_path,
                output_dir=tmp_path,
                tile_size=TILE_SIZE_INFERENCIA,
                overlap_px=TILE_OVERLAP_INFERENCIA,
                calidad_jpg=95,
                saltar_vacios=True,
            )

            tiles_meta = resultado_tiles["metadatos_geo"]["tiles"]
            logger.info("TIFF troceado en %s tiles. Infiriendo...", len(tiles_meta))

            for tile_meta in tiles_meta:
                tile_path = tmp_path / tile_meta["nombre"]
                offset_x = tile_meta["pixel_x"]
                offset_y = tile_meta["pixel_y"]

                for det in self._parsear_resultados(self._inferir(str(tile_path), confidence)):
                    det["x_min"] += offset_x
                    det["x_max"] += offset_x
                    det["y_min"] += offset_y
                    det["y_max"] += offset_y
                    todas_detecciones.append(det)

        deduplicadas = self._nms(
            todas_detecciones, NMS_IOU_TILES, NMS_IOS_DEDUP
        )
        logger.info(
            "TIFF procesado por tiles: %s tiles, %s detecciones (%s tras "
            "deduplicar solapamientos) en %s",
            len(tiles_meta),
            len(todas_detecciones),
            len(deduplicadas),
            image_path,
        )
        return deduplicadas

    @staticmethod
    def _nms(
        detecciones: list[dict],
        iou_threshold: float,
        ios_threshold: float = 0.0,
    ) -> list[dict]:
        """Non-Max Suppression por clase para fusionar detecciones duplicadas.

        Suprime un box (de menor confianza) si contra alguno ya conservado de la
        misma clase: su IoU >= ``iou_threshold`` (solapamiento clásico entre
        tiles) O su IoS >= ``ios_threshold`` (queda mayormente contenido en el
        otro, p. ej. boxes anidados sobre la misma planta). Conserva el de mayor
        confianza.
        """
        if not detecciones:
            return []

        def _inter(a: dict, b: dict) -> float:
            iw = max(0.0, min(a["x_max"], b["x_max"]) - max(a["x_min"], b["x_min"]))
            ih = max(0.0, min(a["y_max"], b["y_max"]) - max(a["y_min"], b["y_min"]))
            return iw * ih

        def _area(d: dict) -> float:
            return (d["x_max"] - d["x_min"]) * (d["y_max"] - d["y_min"])

        def iou(a: dict, b: dict) -> float:
            inter = _inter(a, b)
            if inter <= 0:
                return 0.0
            union = _area(a) + _area(b) - inter
            return inter / union if union > 0 else 0.0

        def ios(a: dict, b: dict) -> float:
            inter = _inter(a, b)
            if inter <= 0:
                return 0.0
            menor = min(_area(a), _area(b))
            return inter / menor if menor > 0 else 0.0

        ordenadas = sorted(detecciones, key=lambda d: d["confianza"], reverse=True)
        conservadas: list[dict] = []
        for det in ordenadas:
            duplicado = any(
                det["clase"] == keep["clase"]
                and (
                    iou(det, keep) >= iou_threshold
                    or (ios_threshold > 0 and ios(det, keep) >= ios_threshold)
                )
                for keep in conservadas
            )
            if not duplicado:
                conservadas.append(det)
        return conservadas

    @staticmethod
    def _parsear_resultados(results) -> list[dict]:
        """Extrae la lista de detecciones desde la salida de Ultralytics."""
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
        return detecciones
