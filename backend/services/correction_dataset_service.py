import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

TIFF_EXTS = {".tif", ".tiff"}
TILE_SIZE = 640
TILE_OVERLAP = 64


class CorrectionDatasetError(Exception):
    pass


class CorrectionDatasetService:
    """
    Construye un dataset YOLO (.zip) a partir de las imágenes marcadas como
    revisadas por un humano. Las detecciones actuales de esas imágenes (del
    modelo + correcciones manuales) son la verdad de referencia.

    - Imagen normal (JPG/PNG): se incluye completa + un .txt con las cajas
      normalizadas al tamaño de la imagen.
    - GeoTIFF: se trocea en tiles 640 (reusando TiffService) y cada caja se
      reproyecta a coordenadas locales del tile que la contiene; solo se
      incluyen los tiles que tienen al menos una detección.
    """

    CLASES = ["planta"]

    @staticmethod
    def construir_zip(imagenes, destino_zip: Path) -> dict:
        """
        imagenes: queryset/iterable de apps.vision.models.Imagen revisadas.
        destino_zip: Path final del .zip.
        Returns: {num_imagenes, num_anotaciones, clases}
        """
        from PIL import Image

        work = Path(tempfile.mkdtemp(prefix="corr_ds_"))
        img_dir = work / "images"
        lbl_dir = work / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        total_imgs = 0
        total_anns = 0
        idx = 0

        for imagen in imagenes:
            detecciones = list(imagen.detecciones.all())
            if not detecciones:
                continue
            try:
                ruta = Path(imagen.archivo.path)
            except (ValueError, AttributeError):
                continue
            if not ruta.exists():
                logger.warning("Imagen sin archivo en disco: %s", imagen.id)
                continue

            if ruta.suffix.lower() in TIFF_EXTS:
                g_imgs, g_anns = CorrectionDatasetService._exportar_tiff(
                    imagen, ruta, detecciones, img_dir, lbl_dir, idx
                )
                total_imgs += g_imgs
                total_anns += g_anns
                idx += g_imgs
            else:
                ok, anns = CorrectionDatasetService._exportar_plana(
                    imagen, ruta, detecciones, img_dir, lbl_dir, idx, Image
                )
                if ok:
                    total_imgs += 1
                    total_anns += anns
                    idx += 1

        if total_imgs == 0:
            shutil.rmtree(work, ignore_errors=True)
            raise CorrectionDatasetError(
                "No hay imágenes revisadas con detecciones para exportar."
            )

        classes_txt = work / "classes.txt"
        classes_txt.write_text("\n".join(CorrectionDatasetService.CLASES))

        destino_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in work.rglob("*"):
                if p.is_file():
                    zf.write(p, p.relative_to(work))

        shutil.rmtree(work, ignore_errors=True)
        return {
            "num_imagenes": total_imgs,
            "num_anotaciones": total_anns,
            "clases": CorrectionDatasetService.CLASES,
        }

    @staticmethod
    def _exportar_plana(imagen, ruta, detecciones, img_dir, lbl_dir, idx, Image):
        try:
            with Image.open(ruta) as im:
                w, h = im.size
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo abrir %s: %s", ruta, e)
            return False, 0
        if w == 0 or h == 0:
            return False, 0

        nombre = f"img_{idx:06d}{ruta.suffix.lower()}"
        shutil.copy2(ruta, img_dir / nombre)

        lineas = []
        for d in detecciones:
            linea = CorrectionDatasetService._yolo_line(
                d.x_min, d.y_min, d.x_max, d.y_max, w, h
            )
            if linea:
                lineas.append(linea)
        (lbl_dir / f"img_{idx:06d}.txt").write_text("\n".join(lineas))
        return True, len(lineas)

    @staticmethod
    def _exportar_tiff(imagen, ruta, detecciones, img_dir, lbl_dir, idx_inicio):
        from services.tiff_service import TiffService

        tiles_dir = Path(tempfile.mkdtemp(prefix="corr_tiles_"))
        try:
            res = TiffService.generar_tiles(
                tiff_path=str(ruta),
                output_dir=tiles_dir,
                tile_size=TILE_SIZE,
                overlap_px=TILE_OVERLAP,
                saltar_vacios=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo tilear %s: %s", ruta, e)
            shutil.rmtree(tiles_dir, ignore_errors=True)
            return 0, 0

        guardados = 0
        anns = 0
        idx = idx_inicio
        for tile in res["metadatos_geo"]["tiles"]:
            tx = tile["pixel_x"]
            ty = tile["pixel_y"]
            lineas = []
            for d in detecciones:
                # Recortar la caja a la ventana del tile.
                lx_min = max(d.x_min, tx)
                ly_min = max(d.y_min, ty)
                lx_max = min(d.x_max, tx + TILE_SIZE)
                ly_max = min(d.y_max, ty + TILE_SIZE)
                if lx_max <= lx_min or ly_max <= ly_min:
                    continue
                linea = CorrectionDatasetService._yolo_line(
                    lx_min - tx,
                    ly_min - ty,
                    lx_max - tx,
                    ly_max - ty,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                if linea:
                    lineas.append(linea)
            if not lineas:
                continue
            nombre = f"img_{idx:06d}.jpg"
            shutil.copy2(tiles_dir / tile["nombre"], img_dir / nombre)
            (lbl_dir / f"img_{idx:06d}.txt").write_text("\n".join(lineas))
            guardados += 1
            anns += len(lineas)
            idx += 1

        shutil.rmtree(tiles_dir, ignore_errors=True)
        return guardados, anns

    @staticmethod
    def _yolo_line(x_min, y_min, x_max, y_max, w, h):
        cx = ((x_min + x_max) / 2) / w
        cy = ((y_min + y_max) / 2) / h
        bw = (x_max - x_min) / w
        bh = (y_max - y_min) / h
        # Descartar cajas degeneradas tras el recorte.
        if bw <= 0 or bh <= 0:
            return None
        cx = min(max(cx, 0.0), 1.0)
        cy = min(max(cy, 0.0), 1.0)
        bw = min(bw, 1.0)
        bh = min(bh, 1.0)
        return f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def dataset_dir() -> Path:
    return Path(settings.MEDIA_ROOT) / "datasets"
