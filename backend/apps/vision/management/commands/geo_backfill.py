"""
Georreferencia vuelos y detecciones YA existentes sin reprocesar YOLO.

Recorre las SesionConversion completadas con metadatos_geo y, para cada
imagen asociada (imagen_vuelo), proyecta sus detecciones a coordenadas
geográficas y fija el centroide del vuelo. Idempotente: por defecto solo
completa lo que está en NULL; con --force recalcula todo.
"""

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from apps.converter.models import SesionConversion
from apps.vision.models import Campo
from services.geo_service import GeoService


class Command(BaseCommand):
    help = "Georreferencia vuelos y detecciones existentes (backfill)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recalcula ubicacion aunque ya esté poblada.",
        )

    def handle(self, *args, **options):
        force = options["force"]

        # 1. Campos: derivar punto desde latitud/longitud existentes.
        campos_qs = Campo.objects.exclude(
            latitud__isnull=True
        ).exclude(longitud__isnull=True)
        if not force:
            campos_qs = campos_qs.filter(punto__isnull=True)
        campos_geo = 0
        for campo in campos_qs:
            if not campo.latitud and not campo.longitud:
                continue  # (0, 0) = sin georreferenciar
            campo.punto = Point(campo.longitud, campo.latitud, srid=4326)
            campo.save(update_fields=["punto"])
            campos_geo += 1

        # 2. Vuelos + detecciones desde sesiones del converter.
        sesiones = (
            SesionConversion.objects.filter(
                estado=SesionConversion.Estado.COMPLETADO,
                imagen_vuelo__isnull=False,
            )
            .exclude(metadatos_geo={})
            .select_related("imagen_vuelo__vuelo")
        )

        vuelos_geo = set()
        det_actualizadas = 0

        for sesion in sesiones:
            imagen = sesion.imagen_vuelo
            if imagen is None:
                continue

            tile_bbox_geo, tile_size_px = GeoService.tile_bbox_para_imagen(
                sesion, imagen.nombre_original
            )
            if not tile_bbox_geo:
                continue

            qs = imagen.detecciones.all()
            if not force:
                qs = qs.filter(ubicacion__isnull=True)

            for det in qs:
                punto = GeoService.centro_deteccion_a_geo(
                    det, tile_bbox_geo, tile_size_px
                )
                if punto:
                    det.ubicacion = punto
                    det.save(update_fields=["ubicacion"])
                    det_actualizadas += 1

            vuelo = imagen.vuelo
            if vuelo and (force or vuelo.ubicacion is None):
                punto = GeoService.centroide_desde_geotiff(sesion.metadatos_geo)
                if punto:
                    vuelo.ubicacion = punto
                    vuelo.save(update_fields=["ubicacion"])
                    vuelos_geo.add(vuelo.id)

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill completo: {campos_geo} campos, "
                f"{len(vuelos_geo)} vuelos y "
                f"{det_actualizadas} detecciones georreferenciadas."
            )
        )
