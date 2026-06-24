import json
import logging
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from django.conf import settings
from PIL import Image
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import Window

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(settings.MEDIA_ROOT)


class TiffInfo:
    """Metadata extraída de un GeoTIFF antes de procesar."""

    def __init__(
        self,
        ancho: int,
        alto: int,
        bandas: int,
        crs: str,
        bounds_geo: dict,
        res_m_per_px: float,
    ):
        self.ancho = ancho
        self.alto = alto
        self.bandas = bandas
        self.crs = crs
        self.bounds_geo = bounds_geo
        self.res_m_per_px = res_m_per_px


class TiffService:
    @staticmethod
    def leer_info(tiff_path: str) -> TiffInfo:
        """
        Lee metadatos del GeoTIFF sin procesar la imagen completa.
        Útil para mostrar info antes de lanzar la tarea Celery.
        """
        with rasterio.open(tiff_path) as src:
            crs_str = str(src.crs) if src.crs else "desconocido"

            # Convertir bounds a WGS84 (lat/lon) para visualización
            if src.crs:
                bounds = transform_bounds(
                    src.crs,
                    CRS.from_epsg(4326),
                    src.bounds.left,
                    src.bounds.bottom,
                    src.bounds.right,
                    src.bounds.top,
                )
                bounds_geo = {
                    "west": bounds[0],
                    "south": bounds[1],
                    "east": bounds[2],
                    "north": bounds[3],
                }
            else:
                bounds_geo = {}

            # Resolución: metros por píxel
            res = src.res  # (pixel_size_x, pixel_size_y) en unidades del CRS
            res_m = (
                abs(res[0])
                if src.crs and "metre" in str(src.crs).lower()
                else 0.0
            )

            return TiffInfo(
                ancho=src.width,
                alto=src.height,
                bandas=src.count,
                crs=crs_str,
                bounds_geo=bounds_geo,
                res_m_per_px=res_m,
            )

    @staticmethod
    def generar_preview_web(
        tiff_path: str,
        out_path: Path,
        max_dim: int = 2048,
        calidad_jpg: int = 85,
    ) -> dict | None:
        """
        Genera un preview JPG reescalado de un GeoTIFF para superponerlo en el
        mapa (imageOverlay de Leaflet) y devuelve sus bounds WGS84.

        Lee una versión submuestreada con `out_shape`, por lo que funciona con
        GeoTIFF pesados (100MB–2GB) sin cargarlos enteros en memoria.

        Returns:
            {"bounds": {west, south, east, north}, "ancho": w, "alto": h}
            o None si el archivo no es un GeoTIFF georreferenciado.
        """
        try:
            with rasterio.open(tiff_path) as src:
                if not src.crs:
                    return None

                escala = min(1.0, max_dim / max(src.width, src.height))
                out_w = max(1, int(round(src.width * escala)))
                out_h = max(1, int(round(src.height * escala)))
                bandas = min(src.count, 3)

                data = src.read(
                    indexes=list(range(1, bandas + 1)),
                    out_shape=(bandas, out_h, out_w),
                    resampling=Resampling.bilinear,
                )
                img_rgb = TiffService._bandas_a_rgb(data, bandas)
                if img_rgb is None:
                    return None

                bounds = transform_bounds(
                    src.crs,
                    CRS.from_epsg(4326),
                    src.bounds.left,
                    src.bounds.bottom,
                    src.bounds.right,
                    src.bounds.top,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo generar preview del TIFF: {e}")
            return None

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img_rgb).save(
            str(out_path), "JPEG", quality=calidad_jpg, optimize=True
        )

        return {
            "bounds": {
                "west": bounds[0],
                "south": bounds[1],
                "east": bounds[2],
                "north": bounds[3],
            },
            "ancho": out_w,
            "alto": out_h,
        }

    @staticmethod
    def calcular_total_tiles(
        tiff_path: str, tile_size: int, overlap_px: int
    ) -> int:
        """Calcula cuántos tiles se generarán sin procesar."""
        with rasterio.open(tiff_path) as src:
            paso = tile_size - overlap_px
            cols = max(1, (src.width + paso - 1) // paso)
            rows = max(1, (src.height + paso - 1) // paso)
            return rows * cols

    @staticmethod
    def generar_tiles(
        tiff_path: str,
        output_dir: Path,
        tile_size: int = 640,
        overlap_px: int = 64,
        calidad_jpg: int = 85,
        saltar_vacios: bool = True,
        on_tile_done=None,
    ) -> dict:
        """
        Genera tiles JPG a partir del GeoTIFF.

        Args:
            tiff_path:     Path al archivo GeoTIFF
            output_dir:    Directorio donde guardar los tiles
            tile_size:     Tamaño de cada tile en píxeles
            overlap_px:    Solapamiento entre tiles
            calidad_jpg:   Calidad JPEG (1-100)
            saltar_vacios: Si True, omite tiles con más del 80% negro
            on_tile_done:  Callback(tiles_procesados) para polling de progreso

        Returns:
            {total_tiles, tiles_guardados, tiles_omitidos, metadatos_geo}
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        paso = tile_size - overlap_px
        tiles_meta = []
        tiles_guardados = 0
        tiles_omitidos = 0

        with rasterio.open(tiff_path) as src:
            total_cols = max(1, (src.width + paso - 1) // paso)
            total_rows = max(1, (src.height + paso - 1) // paso)
            total_tiles = total_rows * total_cols

            crs_str = str(src.crs) if src.crs else "desconocido"
            if src.crs:
                bounds_wgs84 = transform_bounds(
                    src.crs,
                    CRS.from_epsg(4326),
                    src.bounds.left,
                    src.bounds.bottom,
                    src.bounds.right,
                    src.bounds.top,
                )
            else:
                bounds_wgs84 = (0, 0, 0, 0)

            for row in range(total_rows):
                for col in range(total_cols):
                    x_off = col * paso
                    y_off = row * paso

                    # Ajustar ventana al borde del raster
                    w = min(tile_size, src.width - x_off)
                    h = min(tile_size, src.height - y_off)
                    if w <= 0 or h <= 0:
                        continue

                    window = Window(x_off, y_off, w, h)

                    # Leer bandas (GeoTIFF multiespectral y RGB)
                    data = src.read(window=window)

                    # Convertir a imagen RGB de 8 bits
                    img_rgb = TiffService._bandas_a_rgb(data, src.count)
                    if img_rgb is None:
                        tiles_omitidos += 1
                        if on_tile_done:
                            on_tile_done(tiles_guardados + tiles_omitidos)
                        continue

                    # Rellenar hasta tile_size si el tile es de borde
                    if (
                        img_rgb.shape[0] < tile_size
                        or img_rgb.shape[1] < tile_size
                    ):
                        padded = np.zeros(
                            (tile_size, tile_size, 3), dtype=np.uint8
                        )
                        padded[: img_rgb.shape[0], : img_rgb.shape[1]] = img_rgb
                        img_rgb = padded

                    # Saltar tiles vacíos (fondo negro > 80%)
                    if saltar_vacios:
                        negro = np.sum(img_rgb == 0) / img_rgb.size
                        if negro > 0.8:
                            tiles_omitidos += 1
                            if on_tile_done:
                                on_tile_done(tiles_guardados + tiles_omitidos)
                            continue

                    # Guardar JPG
                    nombre = f"tile_{row:04d}_{col:04d}.jpg"
                    dest = output_dir / nombre
                    img_pil = Image.fromarray(img_rgb)
                    img_pil.save(
                        str(dest),
                        "JPEG",
                        quality=calidad_jpg,
                        optimize=True,
                    )
                    tiles_guardados += 1

                    # Metadatos geo de este tile
                    tile_bounds = TiffService._tile_bounds_wgs84(src, window)
                    tiles_meta.append(
                        {
                            "nombre": nombre,
                            "fila": row,
                            "col": col,
                            "pixel_x": x_off,
                            "pixel_y": y_off,
                            "bbox_geo": tile_bounds,
                        }
                    )

                    if on_tile_done:
                        on_tile_done(tiles_guardados + tiles_omitidos)

            ancho_px = src.width
            alto_px = src.height
            bandas = src.count

        metadatos_geo = {
            "crs": crs_str,
            "bounds": {
                "west": bounds_wgs84[0],
                "south": bounds_wgs84[1],
                "east": bounds_wgs84[2],
                "north": bounds_wgs84[3],
            },
            "ancho_px": ancho_px,
            "alto_px": alto_px,
            "bandas": bandas,
            "tile_size": tile_size,
            "overlap_px": overlap_px,
            "tiles": tiles_meta,
        }

        # Guardar JSON de metadatos en el directorio de tiles (NO en el .zip)
        with open(output_dir / "metadata.json", "w") as f:
            json.dump(metadatos_geo, f, indent=2, ensure_ascii=False)

        return {
            "total_tiles": total_tiles,
            "tiles_guardados": tiles_guardados,
            "tiles_omitidos": tiles_omitidos,
            "metadatos_geo": metadatos_geo,
        }

    @staticmethod
    def _bandas_a_rgb(data: np.ndarray, num_bandas: int):
        """
        Convierte array de bandas rasterio a imagen RGB uint8.
        Soporta 1 banda (grayscale), 3+ bandas (RGB/multiespectral).
        Normaliza a 8 bits si el GeoTIFF es 16 bits.
        """
        try:
            if num_bandas == 1:
                banda = data[0].astype(np.float32)
                banda = TiffService._normalizar_a_uint8(banda)
                return np.stack([banda, banda, banda], axis=-1)

            elif num_bandas >= 3:
                r = TiffService._normalizar_a_uint8(data[0].astype(np.float32))
                g = TiffService._normalizar_a_uint8(data[1].astype(np.float32))
                b = TiffService._normalizar_a_uint8(data[2].astype(np.float32))
                return np.stack([r, g, b], axis=-1)

            else:  # 2 bandas (raro, pero posible)
                banda = TiffService._normalizar_a_uint8(
                    data[0].astype(np.float32)
                )
                return np.stack([banda, banda, banda], axis=-1)

        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error convirtiendo bandas a RGB: {e}")
            return None

    @staticmethod
    def _normalizar_a_uint8(arr: np.ndarray) -> np.ndarray:
        """Normaliza cualquier rango a 0-255 uint8."""
        arr_min = arr.min()
        arr_max = arr.max()
        if arr_max == arr_min:
            return np.zeros_like(arr, dtype=np.uint8)
        normalizado = (arr - arr_min) / (arr_max - arr_min) * 255
        return normalizado.astype(np.uint8)

    @staticmethod
    def _tile_bounds_wgs84(src, window: Window) -> dict:
        """
        Calcula el bbox WGS84 de un tile dado su Window,
        usando la transform afín del raster.
        """
        try:
            if not src.crs:
                return {}
            x_off, y_off = window.col_off, window.row_off
            w, h = window.width, window.height

            transform = src.transform
            left = transform.c + x_off * transform.a
            top = transform.f + y_off * transform.e
            right = left + w * transform.a
            bot = top + h * transform.e

            bounds = transform_bounds(
                src.crs, CRS.from_epsg(4326), left, bot, right, top
            )
            return {
                "west": bounds[0],
                "south": bounds[1],
                "east": bounds[2],
                "north": bounds[3],
            }
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    def crear_zip(tiles_dir: Path, session_id: int) -> Path:
        """
        Empaqueta todos los tiles JPG en un .zip.
        NO incluye metadata.json (se queda en el servidor).
        """
        zip_dir = MEDIA_ROOT / "zips_tiles"
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"tiles_sesion_{session_id}.zip"

        with zipfile.ZipFile(
            str(zip_path),
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=1,
        ) as zf:
            for jpg in sorted(tiles_dir.glob("*.jpg")):
                zf.write(jpg, jpg.name)

        return zip_path
