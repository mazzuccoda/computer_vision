import logging
from pathlib import Path

import numpy as np
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

# Confianza mínima por defecto: descarta detecciones flojas (suelen ser cajas
# duplicadas sobre la misma planta). Configurable por env sin redeploy.
CONFIDENCE_INFERENCIA = getattr(settings, "YOLO_CONFIDENCE", 0.5)


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

    def process_image_with_yolo(
        self,
        image_path: str,
        confidence: float | None = None,
        progress_callback=None,
    ) -> dict:
        """Procesa una imagen y retorna detecciones.

        JPG/PNG: inferencia directa (comportamiento sin cambios).

        TIFF: se recorre por ventanas (rasterio) e se infiere tile por tile en
        STREAMING, sin volcar miles de JPG a disco. Esto reproduce el tamaño
        relativo de planta visto durante el entrenamiento; sin trocear, YOLO
        reescala el TIFF completo y las plantas quedan en 2-3 píxeles (0
        detecciones). ``progress_callback(procesados, total)`` se invoca durante
        el recorrido del TIFF para reportar avance por tile.
        """
        if confidence is None:
            confidence = CONFIDENCE_INFERENCIA
        ext = Path(image_path).suffix.lower()
        try:
            if ext in TIFF_EXTENSIONS:
                detecciones = self._detecciones_tiff_por_tiles(
                    image_path, confidence, progress_callback
                )
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

    def _detecciones_tiff_por_tiles(
        self,
        image_path: str,
        confidence: float,
        progress_callback=None,
    ) -> list[dict]:
        """Infiere un GeoTIFF gigapíxel en STREAMING.

        Recorre el TIFF por ventanas (sin escribir tiles a disco), infiere cada
        tile y deduplica las detecciones contra sus vecinas con una grilla
        espacial (IoU + IoS) en O(n): así no se cuelga con decenas de miles de
        cajas (el NMS global era O(n²)) y se eliminan los duplicados de los
        bordes entre tiles y los boxes anidados sobre la misma planta.
        """
        from services.tiff_service import TiffService

        logger.info(
            "Inferencia TIFF en streaming (tile_size=%s, overlap=%s): %s",
            TILE_SIZE_INFERENCIA,
            TILE_OVERLAP_INFERENCIA,
            image_path,
        )

        dedup = _GrillaDedup(
            NMS_IOU_TILES, NMS_IOS_DEDUP, celda=TILE_SIZE_INFERENCIA
        )
        tiles_con_datos = 0
        crudas = 0
        ultimo_reporte = 0

        for indice, total, off_x, off_y, img_rgb in (
            TiffService.iter_tiles_para_inferencia(
                image_path,
                tile_size=TILE_SIZE_INFERENCIA,
                overlap_px=TILE_OVERLAP_INFERENCIA,
                saltar_vacios=True,
            )
        ):
            if img_rgb is not None:
                tiles_con_datos += 1
                # Ultralytics interpreta los ndarray como BGR (igual que cv2 al
                # leer un archivo), así que pasamos BGR para igualar el camino
                # basado en JPG y no alterar las detecciones.
                tile_bgr = np.ascontiguousarray(img_rgb[:, :, ::-1])
                for det in self._parsear_resultados(
                    self._inferir(tile_bgr, confidence)
                ):
                    det["x_min"] += off_x
                    det["x_max"] += off_x
                    det["y_min"] += off_y
                    det["y_max"] += off_y
                    crudas += 1
                    dedup.add(det)

            # Reportar progreso cada ~1% (o cada 25 tiles) para no saturar la BD.
            if progress_callback and (
                indice - ultimo_reporte >= max(25, total // 100)
                or indice == total
            ):
                ultimo_reporte = indice
                progress_callback(indice, total)

        deduplicadas = dedup.resultado()
        logger.info(
            "TIFF procesado en streaming: %s tiles con datos, %s detecciones "
            "(%s tras deduplicar) en %s",
            tiles_con_datos,
            crudas,
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

        ordenadas = sorted(detecciones, key=lambda d: d["confianza"], reverse=True)
        conservadas: list[dict] = []
        for det in ordenadas:
            duplicado = any(
                _es_duplicado(det, keep, iou_threshold, ios_threshold)
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


def _area(d: dict) -> float:
    return (d["x_max"] - d["x_min"]) * (d["y_max"] - d["y_min"])


def _interseccion(a: dict, b: dict) -> float:
    iw = max(0.0, min(a["x_max"], b["x_max"]) - max(a["x_min"], b["x_min"]))
    ih = max(0.0, min(a["y_max"], b["y_max"]) - max(a["y_min"], b["y_min"]))
    return iw * ih


def _es_duplicado(
    a: dict, b: dict, iou_threshold: float, ios_threshold: float
) -> bool:
    """True si ``a`` y ``b`` (misma clase) son la misma detección: por IoU
    (solapamiento clásico) o por IoS (uno contenido en el otro)."""
    if a["clase"] != b["clase"]:
        return False
    inter = _interseccion(a, b)
    if inter <= 0:
        return False
    union = _area(a) + _area(b) - inter
    if union > 0 and inter / union >= iou_threshold:
        return True
    if ios_threshold > 0:
        menor = min(_area(a), _area(b))
        if menor > 0 and inter / menor >= ios_threshold:
            return True
    return False


class _GrillaDedup:
    """Deduplicación espacial incremental para inferencia en streaming.

    Mantiene las detecciones conservadas indexadas en una grilla de celdas de
    lado ``celda`` px. Al agregar una detección sólo se compara contra las que
    caen en su celda y las vecinas (donde puede haber un duplicado de un tile
    contiguo), por lo que el costo es O(n) en vez del O(n²) del NMS global.
    Conserva siempre la de mayor confianza.
    """

    def __init__(self, iou_threshold: float, ios_threshold: float, celda: int):
        self.iou_threshold = iou_threshold
        self.ios_threshold = ios_threshold
        self.celda = max(1, int(celda))
        self._grilla: dict[tuple[int, int], list[int]] = {}
        self._dets: list[dict | None] = []

    def _celdas(self, det: dict):
        cx0 = int(det["x_min"] // self.celda)
        cx1 = int(det["x_max"] // self.celda)
        cy0 = int(det["y_min"] // self.celda)
        cy1 = int(det["y_max"] // self.celda)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                yield (cx, cy)

    def add(self, det: dict) -> None:
        candidatos: set[int] = set()
        for celda in self._celdas(det):
            candidatos.update(self._grilla.get(celda, ()))

        solapados: list[int] = []
        for i in candidatos:
            keep = self._dets[i]
            if keep is None:
                continue
            if _es_duplicado(
                det, keep, self.iou_threshold, self.ios_threshold
            ):
                # Si ya hay una igual o mejor, descartamos la nueva.
                if keep["confianza"] >= det["confianza"]:
                    return
                solapados.append(i)

        # La nueva es mejor que las solapadas: las quitamos.
        for i in solapados:
            self._dets[i] = None

        idx = len(self._dets)
        self._dets.append(det)
        for celda in self._celdas(det):
            self._grilla.setdefault(celda, []).append(idx)

    def resultado(self) -> list[dict]:
        return [d for d in self._dets if d is not None]
