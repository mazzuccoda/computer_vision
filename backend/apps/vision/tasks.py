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


def _crear_detecciones_con_geo(imagen, detecciones_data):
    """
    Crea las Deteccion de una imagen, intentando georreferenciar cada una si
    la imagen tiene una SesionConversion con tile bbox_geo asociado. Si no hay
    datos geo, crea las detecciones igual con ubicacion=None.
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

    detecciones_obj = []
    for d in detecciones_data:
        deteccion = Deteccion(imagen=imagen, **d)
        if tile_bbox_geo:
            deteccion.ubicacion = GeoService.centro_deteccion_a_geo(
                deteccion, tile_bbox_geo, tile_size_px
            )
        detecciones_obj.append(deteccion)

    Deteccion.objects.bulk_create(detecciones_obj)
    return detecciones_obj


def _intentar_georreferenciar_vuelo(vuelo):
    """
    Si alguna imagen del vuelo tiene una SesionConversion asociada con
    metadatos_geo válidos, usa esos bounds para fijar Vuelo.ubicacion. No
    falla el procesamiento del vuelo si no encuentra datos geo.
    """
    from apps.converter.models import SesionConversion
    from services.geo_service import GeoService

    try:
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

        for imagen in imagenes:
            resultado = yolo.process_image_with_yolo(imagen.archivo.path)

            with transaction.atomic():
                _crear_detecciones_con_geo(imagen, resultado["detecciones"])

                imagen.procesada = True
                imagen.conteo_plantas = resultado["total_detecciones"]
                imagen.save(update_fields=["procesada", "conteo_plantas"])

                total_plantas += resultado["total_detecciones"]
                vuelo.imagenes_procesadas += 1
                vuelo.save(update_fields=["imagenes_procesadas"])

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
