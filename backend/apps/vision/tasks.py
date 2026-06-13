from celery import shared_task
from django.db import transaction


@shared_task(bind=True, max_retries=3)
def process_vuelo_task(self, vuelo_id: int) -> dict:
    """
    Procesa todas las imágenes de un vuelo con YOLO.
    Actualiza estado y conteos en tiempo real para polling.
    """
    from apps.vision.models import Deteccion, Vuelo
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
                detecciones_bulk = [
                    Deteccion(imagen=imagen, **d)
                    for d in resultado["detecciones"]
                ]
                Deteccion.objects.bulk_create(detecciones_bulk)

                imagen.procesada = True
                imagen.conteo_plantas = resultado["total_detecciones"]
                imagen.save(update_fields=["procesada", "conteo_plantas"])

                total_plantas += resultado["total_detecciones"]
                vuelo.imagenes_procesadas += 1
                vuelo.save(update_fields=["imagenes_procesadas"])

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
