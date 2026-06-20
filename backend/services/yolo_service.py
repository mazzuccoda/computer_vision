python
import logging
from pathlib import Path

import numpy as np
from django.conf import settings
from ultralytics import YOLO

logger = logging.getLogger(__name__)

TIFF_EXTENSIONS = {".tif", ".tiff"}

# Por encima de esta dimensión (en px), un TIFF se procesa por tiles en vez
# de redimensionarlo de una sola vez. Evita que YOLO reciba una imagen tan
# grande que las plantas queden como manchas de 1-2 px tras el resize interno.
MAX_DIMENSION_SIN_TILING = 2000
TILE_SIZE_INFERENCIA = 640
TILE_OVERLAP_INFERENCIA = 64


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

    # ------------------------------------------------------------------
    # Lectura y normalización de TIFF
    # ------------------------------------------------------------------

    @staticmethod
    def _normalizar_a_uint8(arr: np.ndarray) -> np.ndarray:
        """Normaliza cualquier rango (incluido 16-bit) a 0-255 uint8."""
        arr_min, arr_max = float(arr.min()), float(arr.max())
        if arr_max == arr_min:
            return np.zeros_like(arr, dtype=np.uint8)
        return ((arr - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8)

    @staticmethod
    def _leer_tiff_como_rgb(image_path: str) -> np.ndarray:
        """
        Lee un GeoTIFF con rasterio (igual estrategia que tiff_service.py
        del módulo converter, que ya funciona correctamente) y lo convierte
        a un array RGB uint8 apto para YOLO.

        Raises:
            ValueError: si rasterio no puede abrir el archivo.
        """
        import rasterio

        try:
            with rasterio.open(image_path) as src:
                data = src.read()  # shape: (bandas, alto, ancho)
                num_bandas = src.count

                if num_bandas == 1:
                    banda = YOLOService._normalizar_a_uint8(data[0].astype(np.float32))
                    img_rgb = np.stack([banda, banda, banda], axis=-1)
                elif num_bandas >= 3:
                    r = YOLOService._normalizar_a_uint8(data[0].astype(np.float32))
                    g = YOLOService._normalizar_a_uint8(data[1].astype(np.float32))
                    b = YOLOService._normalizar_a_uint8(data[2].astype(np.float32))
                    img_rgb = np.stack([r, g, b], axis=-1)
                else:  # 2 bandas, caso raro
                    banda = YOLOService._normalizar_a_uint8(data[0].astype(np.float32))
                    img_rgb = np.stack([banda, banda, banda], axis=-1)

            return img_rgb

        except rasterio.errors.RasterioIOError as exc:
            raise ValueError(f"rasterio no pudo abrir el TIFF: {exc}") from exc

    @staticmethod
    def _dimensiones_tiff(image_path: str) -> tuple[int, int]:
        """Devuelve (ancho, alto) sin cargar la imagen completa en memoria."""
        import rasterio

        with rasterio.open(image_path) as src:
            return src.width, src.height

    # ------------------------------------------------------------------
    # Inferencia
    # ------------------------------------------------------------------

    def process_image_with_yolo(
        self,
        image_path: str,
        confidence: float = 0.5,
    ) -> dict:
        """
        Procesa una imagen y retorna detecciones.

        Para JPG/PNG: se pasa el path directo a Ultralytics (comportamiento
        original, sin cambios).

        Para TIFF: se lee con rasterio, se normaliza a RGB uint8, y se pasa
        el array resultante a Ultralytics. Si el TIFF excede
        MAX_DIMENSION_SIN_TILING en cualquier dimensión, se trocea en tiles
        antes de inferir y los resultados se combinan con offset de
        coordenadas para quedar en el sistema de la imagen original.

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
        ext = Path(image_path).suffix.lower()

        try:
            if ext in TIFF_EXTENSIONS:
                return self._process_tiff(image_path, confidence)
            return self._process_estandar(image_path, confidence)

        except Exception as exc:
            logger.error("Error procesando imagen %s: %s", image_path, exc)
            raise

    def _process_estandar(self, image_path: str, confidence: float) -> dict:
        """JPG/PNG: comportamiento original, sin cambios."""
        results = self.model(image_path, conf=confidence)
        return self._parsear_resultados(results)

    def _process_tiff(self, image_path: str, confidence: float) -> dict:
        """TIFF: lectura con rasterio + normalización, con tiling si es grande."""
        ancho, alto = self._dimensiones_tiff(image_path)

        if max(ancho, alto) > MAX_DIMENSION_SIN_TILING:
            logger.info(
                "TIFF grande (%sx%s px): %s. Procesando por tiles.",
                ancho, alto, image_path,
            )
            return self._process_tiff_por_tiles(image_path, confidence)

        logger.info("TIFF estándar (%sx%s px): %s", ancho, alto, image_path)
        img_rgb = self._leer_tiff_como_rgb(image_path)

        if img_rgb.max() == 0:
            logger.warning(
                "TIFF leído pero la imagen resultante es completamente negra: %s",
                image_path,
            )

        results = self.model(img_rgb, conf=confidence)
        return self._parsear_resultados(results)

    def _process_tiff_por_tiles(self, image_path: str, confidence: float) -> dict:
        """
        Trocea un GeoTIFF grande con TiffService (mismo servicio del módulo
        converter), corre inferencia tile por tile, y combina las detecciones
        sumando el offset de píxel de cada tile para devolver coordenadas en
        el sistema de la imagen original completa.
        """
        import tempfile
        from services.tiff_service import TiffService

        todas_detecciones: list[dict] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            resultado_tiles = TiffService.generar_tiles(
                tiff_path=image_path,
                output_dir=tmp_path,
                tile_size=TILE_SIZE_INFERENCIA,
                overlap_px=TILE_OVERLAP_INFERENCIA,
                calidad_jpg=95,
                saltar_vacios=True,
            )

            for tile_meta in resultado_tiles["metadatos_geo"]["tiles"]:
                tile_path = tmp_path / tile_meta["nombre"]
                offset_x = tile_meta["pixel_x"]
                offset_y = tile_meta["pixel_y"]

                results = self.model(str(tile_path), conf=confidence)
                for result in results:
                    for box in result.boxes:
                        todas_detecciones.append(
                            {
                                "confianza": float(box.conf[0]),
                                "x_min": float(box.xyxy[0][0]) + offset_x,
                                "y_min": float(box.xyxy[0][1]) + offset_y,
                                "x_max": float(box.xyxy[0][2]) + offset_x,
                                "y_max": float(box.xyxy[0][3]) + offset_y,
                                "clase": result.names[int(box.cls[0])],
                            }
                        )

        logger.info(
            "TIFF por tiles: %s tiles generados, %s detecciones totales.",
            len(resultado_tiles["metadatos_geo"]["tiles"]),
            len(todas_detecciones),
        )

        return {
            "total_detecciones": len(todas_detecciones),
            "detecciones": todas_detecciones,
        }

    @staticmethod
    def _parsear_resultados(results) -> dict:
        """Extrae el dict de detecciones desde la salida de Ultralytics."""
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

    # TODO FASE 3: Agregar método process_ndvi() para análisis de índice de vegetación
    # TODO FASE 4: Agregar método retrain_model() para reentrenamiento con correcciones manuales
