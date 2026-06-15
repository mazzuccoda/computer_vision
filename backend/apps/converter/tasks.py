import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
MEDIA_ROOT = Path(settings.MEDIA_ROOT)


@shared_task(bind=True, max_retries=2, queue="conversion")
def convert_tiff_task(self, sesion_id: int) -> dict:
    """
    Convierte un GeoTIFF en tiles JPG y genera el .zip descargable.
    Cola: 'conversion', concurrencia 2.
    """
    from apps.converter.models import SesionConversion
    from services.tiff_service import TiffService

    sesion = SesionConversion.objects.get(id=sesion_id)

    try:
        sesion.estado = SesionConversion.Estado.PROCESANDO
        sesion.save(update_fields=["estado"])

        # Resolver path al TIFF según la fuente
        if sesion.fuente == SesionConversion.FuenteTiff.UPLOAD:
            tiff_path = str(MEDIA_ROOT / sesion.archivo_tiff.name)
        else:
            tiff_path = sesion.imagen_vuelo.archivo.path

        # Directorio de salida para tiles
        output_dir = MEDIA_ROOT / "tiles" / f"sesion_{sesion_id}"

        # Calcular total de tiles para progreso
        total = TiffService.calcular_total_tiles(
            tiff_path, sesion.tile_size, sesion.overlap_px
        )
        sesion.total_tiles = total
        sesion.save(update_fields=["total_tiles"])

        # Callback de progreso para polling del frontend
        def on_tile_done(tiles_hechos: int):
            SesionConversion.objects.filter(id=sesion_id).update(
                tiles_procesados=tiles_hechos
            )

        # Generar tiles
        resultado = TiffService.generar_tiles(
            tiff_path=tiff_path,
            output_dir=output_dir,
            tile_size=sesion.tile_size,
            overlap_px=sesion.overlap_px,
            calidad_jpg=sesion.calidad_jpg,
            saltar_vacios=sesion.saltar_vacios,
            on_tile_done=on_tile_done,
        )

        # Crear .zip con los tiles JPG
        zip_path = TiffService.crear_zip(output_dir, sesion_id)
        relative_zip = zip_path.relative_to(MEDIA_ROOT)

        # Guardar resultados
        sesion.tiles_procesados = resultado["tiles_guardados"]
        sesion.total_tiles = (
            resultado["tiles_guardados"] + resultado["tiles_omitidos"]
        )
        sesion.directorio_tiles = str(output_dir.relative_to(MEDIA_ROOT))
        sesion.archivo_zip = str(relative_zip)
        sesion.metadatos_geo = resultado["metadatos_geo"]
        sesion.estado = SesionConversion.Estado.COMPLETADO
        sesion.completado_en = timezone.now()
        sesion.save()

        logger.info(
            "Sesión %s completada: %s tiles guardados, %s omitidos.",
            sesion_id,
            resultado["tiles_guardados"],
            resultado["tiles_omitidos"],
        )
        return {
            "status": "completado",
            "sesion_id": sesion_id,
            "tiles_guardados": resultado["tiles_guardados"],
            "tiles_omitidos": resultado["tiles_omitidos"],
        }

    except Exception as exc:
        sesion.estado = SesionConversion.Estado.ERROR
        sesion.error_mensaje = str(exc)
        sesion.save(update_fields=["estado", "error_mensaje"])
        logger.error("Error en sesión %s: %s", sesion_id, exc)
        raise self.retry(exc=exc, countdown=15)
