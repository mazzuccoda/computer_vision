import logging

from celery import shared_task
from django.db import transaction
from django.db.models import Sum

logger = logging.getLogger(__name__)


def _sesion_geo_para_imagen(imagen):
    """
    Devuelve la SesionConversion completada con metadatos_geo asociada a una
    imagen (vía converter), o None si no existe.
    """
    from apps.converter.models import SesionConversion

    return (
        SesionConversion.objects.filter(
            imagen_vuelo=imagen,
            estado=SesionConversion.Estado.COMPLETADO,
        )
        .exclude(metadatos_geo={})
        .first()
    )


def _es_tiff(imagen) -> bool:
    nombre = (imagen.nombre_original or imagen.archivo.name or "").lower()
    return nombre.endswith((".tif", ".tiff"))


def _referencer_archivo_geotiff(imagen):
    """
    Devuelve un proyector píxel→WGS84 leído del transform/CRS embebido en el
    propio archivo GeoTIFF de la imagen, o None si no es un GeoTIFF
    georreferenciado (JPG/PNG o TIFF sin CRS).
    """
    from services.geo_service import GeoService

    if not _es_tiff(imagen):
        return None
    try:
        return GeoService.referencer_desde_tiff(imagen.archivo.path)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo leer geo del archivo {imagen.id}: {e}")
        return None


def referencer_para_imagen(imagen):
    """
    Devuelve un proyector ``(cx_px, cy_px) -> Point|None`` para una imagen,
    usando primero la SesionConversion (converter) y, si no, el CRS embebido
    en el propio GeoTIFF. Devuelve None si la imagen no es georreferenciable.
    Reutilizado por el procesamiento y por la edición manual de detecciones.
    """
    from services.geo_service import GeoService

    sesion = _sesion_geo_para_imagen(imagen)
    if sesion:
        tile_bbox_geo, tile_size_px = GeoService.tile_bbox_para_imagen(
            sesion, imagen.nombre_original
        )
        if tile_bbox_geo:
            def _proj(cx, cy, _bbox=tile_bbox_geo, _ts=tile_size_px):
                return GeoService.pixel_a_geo(cx, cy, _bbox, _ts)

            return _proj

    return _referencer_archivo_geotiff(imagen)


def _crear_detecciones_con_geo(imagen, detecciones_data):
    """
    Crea las Deteccion de una imagen, intentando georreferenciar cada una.
    Orden de preferencia:
      1. SesionConversion (módulo converter) con tile bbox_geo.
      2. Transform/CRS embebido en el propio GeoTIFF subido al vuelo.
      3. Sin datos geo → ubicacion=None.
    """
    from apps.vision.models import Deteccion
    from services.geo_service import GeoService

    tile_bbox_geo = None
    tile_size_px = 640

    sesion = _sesion_geo_para_imagen(imagen)
    if sesion:
        tile_bbox_geo, tile_size_px = GeoService.tile_bbox_para_imagen(
            sesion, imagen.nombre_original
        )

    referencer = None if tile_bbox_geo else _referencer_archivo_geotiff(imagen)

    detecciones_obj = []
    for d in detecciones_data:
        deteccion = Deteccion(imagen=imagen, **d)
        if tile_bbox_geo:
            deteccion.ubicacion = GeoService.centro_deteccion_a_geo(
                deteccion, tile_bbox_geo, tile_size_px
            )
        elif referencer:
            cx = (deteccion.x_min + deteccion.x_max) / 2
            cy = (deteccion.y_min + deteccion.y_max) / 2
            deteccion.ubicacion = referencer(cx, cy)
        detecciones_obj.append(deteccion)

    Deteccion.objects.bulk_create(detecciones_obj)
    return detecciones_obj


def _georreferenciar_detecciones_existentes(vuelo) -> int:
    """
    Georreferencia detecciones YA creadas que no tienen ubicacion, leyendo el
    transform/CRS del propio GeoTIFF de cada imagen. Permite que un vuelo cuyas
    imágenes ya estaban procesadas (sin geo) aparezca en el mapa al pulsar
    "Procesar vuelo" de nuevo, sin volver a inferir. Idempotente.
    """
    actualizadas = 0
    for imagen in vuelo.imagenes.all():
        pendientes = imagen.detecciones.filter(ubicacion__isnull=True)
        if not pendientes.exists():
            continue
        referencer = _referencer_archivo_geotiff(imagen)
        if referencer is None:
            continue
        for det in pendientes:
            cx = (det.x_min + det.x_max) / 2
            cy = (det.y_min + det.y_max) / 2
            punto = referencer(cx, cy)
            if punto:
                det.ubicacion = punto
                det.save(update_fields=["ubicacion"])
                actualizadas += 1
    if actualizadas:
        logger.info(
            f"Vuelo {vuelo.id}: {actualizadas} detecciones georreferenciadas "
            f"desde el archivo GeoTIFF."
        )
    return actualizadas


def _intentar_georreferenciar_vuelo(vuelo):
    """
    Si alguna imagen del vuelo tiene una SesionConversion asociada con
    metadatos_geo válidos, usa esos bounds para fijar Vuelo.ubicacion. No
    falla el procesamiento del vuelo si no encuentra datos geo.
    """
    from apps.converter.models import SesionConversion
    from services.geo_service import GeoService

    try:
        punto = None
        sesion = (
            SesionConversion.objects.filter(
                imagen_vuelo__vuelo=vuelo,
                estado=SesionConversion.Estado.COMPLETADO,
            )
            .exclude(metadatos_geo={})
            .first()
        )
        if sesion:
            punto = GeoService.centroide_desde_geotiff(sesion.metadatos_geo)

        # Fallback: centroide leído del propio GeoTIFF subido al vuelo.
        if punto is None:
            for imagen in vuelo.imagenes.all():
                if _es_tiff(imagen):
                    punto = GeoService.centroide_desde_tiff(imagen.archivo.path)
                    if punto:
                        break

        if punto:
            vuelo.ubicacion = punto
            vuelo.save(update_fields=["ubicacion"])
            logger.info(f"Vuelo {vuelo.id} georreferenciado: {punto}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo georreferenciar vuelo {vuelo.id}: {e}")


@shared_task(bind=True, max_retries=3)
def process_vuelo_task(self, vuelo_id: int) -> dict:
    """
    Procesa todas las imágenes de un vuelo con YOLO.
    Actualiza estado y conteos en tiempo real para polling.
    """
    from apps.vision.models import Vuelo
    from services.yolo_service import YOLOService

    try:
        vuelo = Vuelo.objects.get(id=vuelo_id)
        vuelo.estado = Vuelo.Estado.PROCESANDO
        vuelo.save(update_fields=["estado"])

        yolo = YOLOService.get_instance()
        imagenes = vuelo.imagenes.filter(procesada=False)
        total_plantas = 0

        def _progreso_tiles(procesados, total):
            # Progreso fino para TIFF gigapíxel (se infiere por tiles); la barra
            # por imagen quedaría en 0% durante horas.
            Vuelo.objects.filter(id=vuelo.id).update(
                tiles_procesados=procesados, tiles_total=total
            )

        for imagen in imagenes:
            resultado = yolo.process_image_with_yolo(
                imagen.archivo.path, progress_callback=_progreso_tiles
            )

            with transaction.atomic():
                _crear_detecciones_con_geo(imagen, resultado["detecciones"])

                imagen.procesada = True
                imagen.conteo_plantas = resultado["total_detecciones"]
                imagen.save(update_fields=["procesada", "conteo_plantas"])

                total_plantas += resultado["total_detecciones"]
                vuelo.imagenes_procesadas += 1
                vuelo.tiles_total = None
                vuelo.tiles_procesados = None
                vuelo.save(update_fields=[
                    "imagenes_procesadas", "tiles_total", "tiles_procesados"
                ])

        _georreferenciar_detecciones_existentes(vuelo)
        _intentar_georreferenciar_vuelo(vuelo)

        # Recalcular desde la fuente de verdad (suma del conteo por imagen) en
        # lugar del acumulador del loop. Así el total queda consistente con la
        # tabla de imágenes aunque el vuelo se reprocese o procese parcialmente
        # (el loop solo recorre imágenes con procesada=False).
        total_plantas = (
            vuelo.imagenes.aggregate(total=Sum("conteo_plantas"))["total"] or 0
        )
        vuelo.total_plantas = total_plantas
        vuelo.estado = Vuelo.Estado.COMPLETADO
        vuelo.save(update_fields=["total_plantas", "estado"])

        return {"status": "completado", "total_plantas": total_plantas}

    except Exception as exc:
        vuelo = Vuelo.objects.filter(id=vuelo_id).first()
        if vuelo:
            vuelo.estado = Vuelo.Estado.ERROR
            vuelo.save(update_fields=["estado"])
        raise self.retry(exc=exc, countdown=5)


@shared_task(bind=True, max_retries=1, queue="conversion")
def construir_overviews_ortofoto_task(self, tiff_path: str) -> dict:
    """
    Genera en segundo plano la pirámide de overviews externa del GeoTIFF para
    servir los tiles de la ortofoto nítidos y rápidos a cualquier zoom, sin
    modificar el archivo original. Idempotente: si ya están, no hace nada.
    """
    from services.tiff_service import TiffService

    try:
        vrt = TiffService.construir_overviews(tiff_path)
        return {"status": "ok" if vrt else "omitido", "tiff_path": tiff_path}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error generando overviews de %s: %s", tiff_path, exc)
        raise self.retry(exc=exc, countdown=30)
