import io
import json
import logging
import math
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from django.conf import settings
from PIL import Image
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import array_bounds, from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import (
    calculate_default_transform,
    reproject,
    transform_bounds,
)
from rasterio.windows import Window

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(settings.MEDIA_ROOT)

# Lado máximo (px) y calidad del JPG de preview reproyectado a EPSG:4326.
# Configurables por settings/env para poder subir la nitidez al hacer zoom.
PREVIEW_MAX_DIM = getattr(settings, "ORTOFOTO_PREVIEW_MAX_DIM", 4096)
PREVIEW_JPG_QUALITY = getattr(settings, "ORTOFOTO_PREVIEW_JPG_QUALITY", 90)

# Web Mercator (EPSG:3857): CRS de los tiles XYZ (estándar slippy map / Leaflet).
WEB_MERCATOR = CRS.from_epsg(3857)
# Resolución (m/px en unidades Mercator) del nivel de zoom 0 con tiles de 256 px:
# circunferencia ecuatorial (2*pi*R) / 256.
MERCATOR_RES_Z0 = 2 * math.pi * 6378137.0 / 256.0  # ≈ 156543.0339
TILE_SIZE = 256


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
    def _grid_4326(src, max_dim: int):
        """
        Calcula la grilla de destino EPSG:4326 (north-up) para el preview:
        (dst_transform, out_w, out_h, src_w, src_h). Compartido por el preview
        JPG y por los bounds de overlay, para que la imagen y su colocación en
        Leaflet usen exactamente la misma extensión.
        """
        dst_crs = CRS.from_epsg(4326)
        escala = min(1.0, max_dim / max(src.width, src.height))
        src_w = max(1, int(round(src.width * escala)))
        src_h = max(1, int(round(src.height * escala)))
        dst_transform, out_w, out_h = calculate_default_transform(
            src.crs,
            dst_crs,
            src_w,
            src_h,
            left=src.bounds.left,
            bottom=src.bounds.bottom,
            right=src.bounds.right,
            top=src.bounds.top,
        )
        return dst_transform, out_w, out_h, src_w, src_h

    @staticmethod
    def preview_bounds(
        tiff_path: str, max_dim: int = PREVIEW_MAX_DIM
    ) -> dict | None:
        """
        Devuelve los bounds WGS84 de la grilla del preview (sin generar el JPG),
        para colocar la ortofoto en el mapa alineada con su imagen reproyectada.
        """
        try:
            with rasterio.open(tiff_path) as src:
                if not src.crs:
                    return None
                dst_transform, out_w, out_h, _, _ = TiffService._grid_4326(
                    src, max_dim
                )
                west, south, east, north = array_bounds(
                    out_h, out_w, dst_transform
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo calcular bounds del preview: {e}")
            return None
        return {"west": west, "south": south, "east": east, "north": north}

    @staticmethod
    def generar_preview_web(
        tiff_path: str,
        out_path: Path,
        max_dim: int = PREVIEW_MAX_DIM,
        calidad_jpg: int = PREVIEW_JPG_QUALITY,
    ) -> dict | None:
        """
        Genera un preview JPG reescalado de un GeoTIFF para superponerlo en el
        mapa (imageOverlay de Leaflet) y devuelve sus bounds WGS84.

        El preview se **reproyecta a EPSG:4326 (north-up)**, por lo que su grilla
        de píxeles mapea de forma lineal a sus bounds lat/lon. Así Leaflet (que
        coloca la imagen estirándola entre esquinas) queda alineado con los
        recuadros de cada detección, que se proyectan píxel→WGS84 con precisión.
        Sin esto, un GeoTIFF en CRS proyectado (UTM) se vería desfasado.

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

                dst_crs = CRS.from_epsg(4326)
                dst_transform, out_w, out_h, src_w, src_h = (
                    TiffService._grid_4326(src, max_dim)
                )
                bandas = min(src.count, 3)

                data = src.read(
                    indexes=list(range(1, bandas + 1)),
                    out_shape=(bandas, src_h, src_w),
                    resampling=Resampling.bilinear,
                )
                img_rgb = TiffService._bandas_a_rgb(
                    data, bandas, preview=True
                )
                if img_rgb is None:
                    return None

                src_transform = src.transform * rasterio.Affine.scale(
                    src.width / src_w, src.height / src_h
                )

                dst_rgb = np.zeros((out_h, out_w, 3), dtype=np.uint8)
                for ch in range(3):
                    reproject(
                        source=img_rgb[:, :, ch],
                        destination=dst_rgb[:, :, ch],
                        src_transform=src_transform,
                        src_crs=src.crs,
                        dst_transform=dst_transform,
                        dst_crs=dst_crs,
                        resampling=Resampling.bilinear,
                    )

                west, south, east, north = array_bounds(
                    out_h, out_w, dst_transform
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo generar preview del TIFF: {e}")
            return None

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(dst_rgb).save(
            str(out_path), "JPEG", quality=calidad_jpg, optimize=True
        )

        return {
            "bounds": {
                "west": west,
                "south": south,
                "east": east,
                "north": north,
            },
            "ancho": out_w,
            "alto": out_h,
        }

    # ------------------------------------------------------------------
    # Tiles XYZ on-demand (slippy map) — nitidez nativa al hacer zoom.
    #
    # En vez de servir un único JPG reescalado (que Leaflet estira y se ve
    # borroso al acercarse), se generan tiles 256×256 en Web Mercator por
    # nivel de zoom leídos directamente del GeoTIFF a su resolución nativa.
    # Cada tile lee sólo la ventana del raster que cubre, así funciona con
    # GeoTIFF pesados (cientos de MB) sin cargarlos enteros en memoria.
    # ------------------------------------------------------------------

    @staticmethod
    def _tile_bounds_3857(z: int, x: int, y: int) -> tuple:
        """Bbox (oeste, sur, este, norte) de un tile XYZ en EPSG:3857."""
        n = 2 ** z
        origen = math.pi * 6378137.0  # media circunferencia ecuatorial
        ancho_tile = (2 * origen) / n
        west = -origen + x * ancho_tile
        east = west + ancho_tile
        north = origen - y * ancho_tile
        south = north - ancho_tile
        return west, south, east, north

    @staticmethod
    def tile_native_maxzoom(tiff_path: str) -> int | None:
        """
        Nivel de zoom XYZ que iguala (sin sobre-muestrear) la resolución nativa
        del GeoTIFF, para que el frontend lo use como ``maxNativeZoom``. Más allá
        de ese nivel, Leaflet sobre-escala los últimos tiles nativos.
        """
        try:
            with rasterio.open(tiff_path) as src:
                if not src.crs:
                    return None
                b = transform_bounds(
                    src.crs, WEB_MERCATOR, *src.bounds, densify_pts=21
                )
                ancho_m = abs(b[2] - b[0])
                if ancho_m <= 0 or src.width <= 0:
                    return None
                res_nativa = ancho_m / src.width  # m/px en Mercator
                z = math.log2(MERCATOR_RES_Z0 / res_nativa)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo calcular maxzoom del TIFF: {e}")
            return None
        return int(max(0, min(24, math.ceil(z))))

    @staticmethod
    @lru_cache(maxsize=64)
    def _rango_preview_cache(tiff_path: str, mtime: float, bandas: int):
        """
        Rango (lo, hi) por banda para normalizar a 8 bits de forma consistente
        entre todos los tiles (evita costuras de contraste tile a tile).

        - uint8: devuelve None (color real, sin estiramiento).
        - mayor profundidad: percentiles 2–98 % calculados UNA vez sobre una
          versión submuestreada de todo el raster.
        El resultado se cachea por (path, mtime) para no recomputarlo por tile.
        """
        with rasterio.open(tiff_path) as src:
            if src.dtypes[0] == "uint8":
                return None
            escala = min(1.0, 1024 / max(src.width, src.height))
            sw = max(1, int(src.width * escala))
            sh = max(1, int(src.height * escala))
            data = src.read(
                indexes=list(range(1, bandas + 1)),
                out_shape=(bandas, sh, sw),
                resampling=Resampling.bilinear,
            ).astype(np.float32)
            rangos = []
            for banda in data:
                lo, hi = np.percentile(banda, (2.0, 98.0))
                if hi <= lo:
                    lo, hi = float(banda.min()), float(banda.max())
                    if hi <= lo:
                        hi = lo + 1.0
                rangos.append((float(lo), float(hi)))
            return tuple(rangos)

    @staticmethod
    def _aplicar_rango(banda: np.ndarray, rango) -> np.ndarray:
        """Escala una banda a uint8 usando (lo, hi); si es None, asume uint8."""
        if rango is None:
            if banda.dtype == np.uint8:
                return banda
            return TiffService._normalizar_a_uint8(banda)
        lo, hi = rango
        arr = np.clip(banda.astype(np.float32), lo, hi)
        return ((arr - lo) / (hi - lo) * 255).astype(np.uint8)

    @staticmethod
    def generar_tile_xyz(
        tiff_path: str, z: int, x: int, y: int, tile_size: int = TILE_SIZE
    ) -> bytes | None:
        """
        Genera el tile XYZ (z/x/y) del GeoTIFF como PNG RGBA (con transparencia
        fuera de la ortofoto). Devuelve None si el tile no intersecta el raster.
        """
        west, south, east, north = TiffService._tile_bounds_3857(z, x, y)
        try:
            with rasterio.open(tiff_path) as src:
                if not src.crs:
                    return None
                sb = transform_bounds(
                    src.crs, WEB_MERCATOR, *src.bounds, densify_pts=21
                )
                # Sin intersección con la extensión del raster → tile vacío.
                if (
                    east <= sb[0]
                    or west >= sb[2]
                    or north <= sb[1]
                    or south >= sb[3]
                ):
                    return None

                bandas = min(src.count, 3)
                rango = TiffService._rango_preview_cache(
                    tiff_path, Path(tiff_path).stat().st_mtime, bandas
                )
                rango_por_banda = (
                    rango if rango is not None else [None] * bandas
                )

                # La grilla de salida del VRT se define exactamente sobre la
                # extensión del tile, así read() devuelve tile_size×tile_size y
                # los píxeles fuera de la ortofoto quedan como nodata (mask=0).
                dst_transform = from_bounds(
                    west, south, east, north, tile_size, tile_size
                )
                with WarpedVRT(
                    src,
                    crs=WEB_MERCATOR,
                    transform=dst_transform,
                    width=tile_size,
                    height=tile_size,
                    resampling=Resampling.bilinear,
                    add_alpha=True,
                ) as vrt:
                    data = vrt.read(indexes=list(range(1, bandas + 1)))
                    mask = vrt.read_masks(1)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo generar tile {z}/{x}/{y}: {e}")
            return None

        if bandas >= 3:
            canales = [
                TiffService._aplicar_rango(data[i], rango_por_banda[i])
                for i in range(3)
            ]
        else:  # 1 banda → escala de grises replicada en RGB
            g = TiffService._aplicar_rango(data[0], rango_por_banda[0])
            canales = [g, g, g]

        rgba = np.dstack([canales[0], canales[1], canales[2], mask])
        buf = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG", optimize=True)
        return buf.getvalue()

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
    def _bandas_a_rgb(
        data: np.ndarray, num_bandas: int, preview: bool = False
    ):
        """
        Convierte array de bandas rasterio a imagen RGB uint8.
        Soporta 1 banda (grayscale), 3+ bandas (RGB/multiespectral).
        Normaliza a 8 bits si el GeoTIFF es 16 bits.

        Args:
            preview: si True usa una normalización pensada para visualización
                (color fiel para imágenes ya de 8 bits + estiramiento por
                percentiles para mayor contraste en el resto). El default
                (False) conserva el comportamiento histórico de los tiles que
                alimentan a YOLO, para no alterar la inferencia.
        """
        try:
            norm = (
                TiffService._normalizar_para_preview
                if preview
                else TiffService._normalizar_a_uint8
            )
            if num_bandas == 1:
                banda = norm(data[0])
                return np.stack([banda, banda, banda], axis=-1)

            elif num_bandas >= 3:
                r = norm(data[0])
                g = norm(data[1])
                b = norm(data[2])
                return np.stack([r, g, b], axis=-1)

            else:  # 2 bandas (raro, pero posible)
                banda = norm(data[0])
                return np.stack([banda, banda, banda], axis=-1)

        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error convirtiendo bandas a RGB: {e}")
            return None

    @staticmethod
    def _normalizar_a_uint8(arr: np.ndarray) -> np.ndarray:
        """Normaliza cualquier rango a 0-255 uint8 (min-max global)."""
        arr = arr.astype(np.float32)
        arr_min = arr.min()
        arr_max = arr.max()
        if arr_max == arr_min:
            return np.zeros_like(arr, dtype=np.uint8)
        normalizado = (arr - arr_min) / (arr_max - arr_min) * 255
        return normalizado.astype(np.uint8)

    @staticmethod
    def _normalizar_para_preview(arr: np.ndarray) -> np.ndarray:
        """
        Normalización orientada a visualización de la ortofoto:

        - GeoTIFF ya de 8 bits (uint8): se devuelve tal cual, preservando el
          color real (un min-max por banda distorsionaría los colores).
        - Mayor profundidad (uint16, float, etc.): estiramiento por percentiles
          2–98 % para dar contraste sin que outliers laven la imagen.
        """
        if arr.dtype == np.uint8:
            return arr
        arr = arr.astype(np.float32)
        lo, hi = np.percentile(arr, (2.0, 98.0))
        if hi <= lo:
            return TiffService._normalizar_a_uint8(arr)
        recortado = np.clip(arr, lo, hi)
        normalizado = (recortado - lo) / (hi - lo) * 255
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
