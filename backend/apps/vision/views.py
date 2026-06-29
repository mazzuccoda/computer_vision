import csv
import logging
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Campo, Deteccion, Imagen, Modulo, Vuelo
from .serializers import (
    CampoGeoSerializer,
    CampoSerializer,
    DeteccionEditSerializer,
    DeteccionMapaSerializer,
    DeteccionSerializer,
    ImagenSerializer,
    ModuloSerializer,
    VueloDetalleSerializer,
    VueloGeoSerializer,
    VueloSerializer,
)
from apps.feedback.services import registrar_correccion
from .tasks import process_vuelo_task
from services.annotation_service import AnnotationService
from services.geo_service import GeoService
from services.tiff_service import TiffService

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"detail": "El token 'refresh' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Token inválido o ya expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_205_RESET_CONTENT)


# --------------------------------------------------------------------------
# CRUD ViewSets
# --------------------------------------------------------------------------


class CampoViewSet(viewsets.ModelViewSet):
    queryset = Campo.objects.all()
    serializer_class = CampoSerializer
    permission_classes = [IsAuthenticated]


class ModuloViewSet(viewsets.ModelViewSet):
    serializer_class = ModuloSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Modulo.objects.select_related("campo").all()
        campo_id = self.request.query_params.get("campo_id")
        if campo_id:
            qs = qs.filter(campo_id=campo_id)
        return qs


class VueloViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Vuelo.objects.select_related("modulo", "modulo__campo").all()
        modulo_id = self.request.query_params.get("modulo_id")
        if modulo_id:
            qs = qs.filter(modulo_id=modulo_id)
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return VueloDetalleSerializer
        return VueloSerializer

    @action(
        detail=True,
        methods=["post"],
        url_path="upload-images",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_images(self, request, pk=None):
        vuelo = self.get_object()
        archivos = request.FILES.getlist("imagenes") or request.FILES.getlist(
            "archivos"
        )
        if not archivos:
            return Response(
                {"detail": "No se enviaron imágenes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        creadas = []
        for archivo in archivos:
            imagen = Imagen.objects.create(
                vuelo=vuelo,
                archivo=archivo,
                nombre_original=archivo.name,
            )
            creadas.append(imagen)

        vuelo.total_imagenes = vuelo.imagenes.count()
        vuelo.save(update_fields=["total_imagenes"])

        serializer = ImagenSerializer(
            creadas, many=True, context={"request": request}
        )
        return Response(
            {"creadas": len(creadas), "imagenes": serializer.data},
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="upload-images-chunk",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_images_chunk(self, request, pk=None):
        """Subida por fragmentos para archivos grandes.

        Permite subir GeoTIFF que superan el límite de cuerpo por request de los
        proxies/CDN (p. ej. Cloudflare corta en 100 MB). El cliente parte el
        archivo en fragmentos < límite y los envía en orden con el mismo
        ``upload_id``; al recibir el último se reensamblan y se crea la Imagen.
        """
        vuelo = self.get_object()
        chunk = request.FILES.get("chunk")
        upload_id = request.data.get("upload_id", "")
        filename = request.data.get("filename", "")
        try:
            index = int(request.data.get("chunk_index"))
            total = int(request.data.get("total_chunks"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "chunk_index/total_chunks inválidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        safe_id = "".join(c for c in upload_id if c.isalnum() or c in "-_")
        safe_name = Path(filename).name
        if chunk is None or not safe_id or not safe_name or total < 1:
            return Response(
                {"detail": "Faltan datos del fragmento."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tmp_dir = Path(settings.MEDIA_ROOT) / "tmp_uploads" / safe_id
        tmp_dir.mkdir(parents=True, exist_ok=True)
        part_path = tmp_dir / f"{index:06d}.part"
        with open(part_path, "wb") as dest:
            for piece in chunk.chunks():
                dest.write(piece)

        if len(list(tmp_dir.glob("*.part"))) < total:
            return Response(
                {"detail": "Fragmento recibido.", "recibido": index + 1, "total": total},
                status=status.HTTP_202_ACCEPTED,
            )

        assembled = tmp_dir / "assembled"
        with open(assembled, "wb") as out:
            for i in range(total):
                part = tmp_dir / f"{i:06d}.part"
                if not part.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return Response(
                        {"detail": f"Falta el fragmento {i}; reintentá la subida."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                with open(part, "rb") as pf:
                    shutil.copyfileobj(pf, out, length=1024 * 1024)

        imagen = Imagen(vuelo=vuelo, nombre_original=safe_name)
        with open(assembled, "rb") as f:
            imagen.archivo.save(safe_name, File(f), save=True)

        shutil.rmtree(tmp_dir, ignore_errors=True)

        vuelo.total_imagenes = vuelo.imagenes.count()
        vuelo.save(update_fields=["total_imagenes"])

        serializer = ImagenSerializer(imagen, context={"request": request})
        return Response(
            {"creadas": 1, "imagenes": [serializer.data]},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="process")
    def process(self, request, pk=None):
        vuelo = self.get_object()
        if vuelo.total_imagenes == 0:
            return Response(
                {"detail": "El vuelo no tiene imágenes para procesar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ``reprocesar``: rehacer la inferencia de TODO el vuelo con el modelo
        # activo. El task sólo procesa imágenes con procesada=False, así que sin
        # este reset un vuelo ya procesado no vuelve a inferir nada (no se podría
        # aplicar otro modelo). Borra detecciones previas y resetea las imágenes.
        reprocesar = str(request.data.get("reprocesar", "")).lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        # Bloqueo contra doble disparo: si se pulsa "Procesar"/"Reprocesar" dos
        # veces (o el front reintenta), se llegaban a encolar 2 tareas que
        # inferían en paralelo y guardaban CADA detección 2 veces (el conteo del
        # vuelo quedaba a la mitad del total real en el mapa). Marcamos el vuelo
        # como PROCESANDO dentro de una fila bloqueada y rechazamos si ya lo
        # estaba: así el segundo request no encola nada.
        with transaction.atomic():
            vuelo = Vuelo.objects.select_for_update().get(pk=vuelo.pk)
            if vuelo.estado == Vuelo.Estado.PROCESANDO:
                return Response(
                    {"detail": "El vuelo ya se está procesando."},
                    status=status.HTTP_409_CONFLICT,
                )
            if reprocesar:
                Deteccion.objects.filter(imagen__vuelo=vuelo).delete()
                vuelo.imagenes.update(procesada=False, conteo_plantas=0)
                vuelo.total_plantas = 0

            vuelo.estado = Vuelo.Estado.PROCESANDO
            vuelo.imagenes_procesadas = vuelo.imagenes.filter(
                procesada=True
            ).count()
            vuelo.tiles_total = None
            vuelo.tiles_procesados = None
            vuelo.save(update_fields=[
                "estado", "imagenes_procesadas", "total_plantas",
                "tiles_total", "tiles_procesados",
            ])

        async_result = process_vuelo_task.delay(vuelo.id)
        vuelo.celery_task_id = async_result.id
        vuelo.save(update_fields=["celery_task_id"])
        return Response(
            {"detail": "Procesamiento iniciado.", "vuelo_id": vuelo.id},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="deduplicar")
    def deduplicar(self, request, pk=None):
        """Elimina detecciones duplicadas EXACTAS del vuelo (misma imagen y
        mismo bounding box), dejando una sola copia. Sirve para limpiar vuelos
        que quedaron con detecciones repetidas por un doble procesamiento
        anterior, sin tener que reinferir el TIFF. Recalcula los conteos."""
        vuelo = self.get_object()
        if vuelo.estado == Vuelo.Estado.PROCESANDO:
            return Response(
                {"detail": "El vuelo se está procesando; esperá a que termine."},
                status=status.HTTP_409_CONFLICT,
            )

        vistos: set[tuple] = set()
        a_borrar: list[int] = []
        filas = (
            Deteccion.objects.filter(imagen__vuelo=vuelo)
            .order_by("id")
            .values("id", "imagen_id", "x_min", "y_min", "x_max", "y_max")
            .iterator(chunk_size=5000)
        )
        for d in filas:
            clave = (
                d["imagen_id"],
                round(d["x_min"], 2),
                round(d["y_min"], 2),
                round(d["x_max"], 2),
                round(d["y_max"], 2),
            )
            if clave in vistos:
                a_borrar.append(d["id"])
            else:
                vistos.add(clave)

        eliminadas = 0
        for i in range(0, len(a_borrar), 5000):
            chunk = a_borrar[i:i + 5000]
            eliminadas += Deteccion.objects.filter(id__in=chunk).delete()[0]

        for imagen in vuelo.imagenes.all():
            imagen.conteo_plantas = imagen.detecciones.count()
            imagen.save(update_fields=["conteo_plantas"])
        vuelo.total_plantas = (
            vuelo.imagenes.aggregate(total=Sum("conteo_plantas"))["total"] or 0
        )
        vuelo.save(update_fields=["total_plantas"])

        return Response(
            {
                "eliminadas": eliminadas,
                "total_plantas": vuelo.total_plantas,
            }
        )

    @action(detail=True, methods=["post"], url_path="rededuplicar")
    def rededuplicar(self, request, pk=None):
        """Re-aplica el dedup geométrico (IoU/IoS/distancia entre centros) sobre
        las detecciones YA guardadas del vuelo, SIN reinferir el TIFF. Sirve para
        afinar la superposición al instante (segundos) en vez de reprocesar horas
        en CPU. Acepta overrides opcionales en el body: ``iou``, ``ios``,
        ``dist`` (px); si no se pasan usa los valores de entorno (settings).
        Conserva siempre la detección de mayor confianza. Recalcula los conteos.
        """
        from services.yolo_service import (
            NMS_DIST_DEDUP,
            NMS_IOS_DEDUP,
            NMS_IOU_TILES,
            TILE_SIZE_INFERENCIA,
            _GrillaDedup,
        )

        vuelo = self.get_object()
        if vuelo.estado == Vuelo.Estado.PROCESANDO:
            return Response(
                {"detail": "El vuelo se está procesando; esperá a que termine."},
                status=status.HTTP_409_CONFLICT,
            )

        def _num(nombre, default):
            val = request.data.get(nombre)
            if val in (None, ""):
                return default
            try:
                return max(0.0, float(val))
            except (TypeError, ValueError):
                return default

        iou = _num("iou", NMS_IOU_TILES)
        ios = _num("ios", NMS_IOS_DEDUP)
        dist = _num("dist", NMS_DIST_DEDUP)

        total_antes = 0
        a_borrar: list[int] = []
        for imagen in vuelo.imagenes.all():
            dets = list(
                imagen.detecciones.all().values(
                    "id", "x_min", "y_min", "x_max", "y_max", "clase", "confianza"
                )
            )
            total_antes += len(dets)
            grilla = _GrillaDedup(iou, ios, dist, celda=TILE_SIZE_INFERENCIA)
            for d in dets:
                grilla.add(dict(d))
            keep_ids = {d["id"] for d in grilla.resultado()}
            a_borrar.extend(d["id"] for d in dets if d["id"] not in keep_ids)
            imagen.conteo_plantas = len(keep_ids)
            imagen.save(update_fields=["conteo_plantas"])

        eliminadas = 0
        for i in range(0, len(a_borrar), 5000):
            chunk = a_borrar[i:i + 5000]
            eliminadas += Deteccion.objects.filter(id__in=chunk).delete()[0]

        vuelo.total_plantas = (
            vuelo.imagenes.aggregate(total=Sum("conteo_plantas"))["total"] or 0
        )
        vuelo.save(update_fields=["total_plantas"])

        return Response(
            {
                "eliminadas": eliminadas,
                "total_antes": total_antes,
                "total_plantas": vuelo.total_plantas,
                "parametros": {"iou": iou, "ios": ios, "dist": dist},
            }
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancela el procesamiento en curso: mata la tarea de Celery (sin
        reiniciar el worker) y deja el vuelo en 'pendiente' para poder
        reprocesarlo. Las detecciones ya guardadas se conservan."""
        vuelo = self.get_object()
        if vuelo.estado != Vuelo.Estado.PROCESANDO:
            return Response(
                {"detail": "El vuelo no está procesando."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if vuelo.celery_task_id:
            try:
                from config.celery import app

                app.control.revoke(
                    vuelo.celery_task_id, terminate=True, signal="SIGKILL"
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "No se pudo revocar la tarea Celery %s del vuelo %s",
                    vuelo.celery_task_id,
                    vuelo.pk,
                )

        vuelo.estado = Vuelo.Estado.PENDIENTE
        vuelo.celery_task_id = ""
        vuelo.tiles_total = None
        vuelo.tiles_procesados = None
        vuelo.imagenes_procesadas = vuelo.imagenes.filter(
            procesada=True
        ).count()
        vuelo.save(update_fields=[
            "estado", "celery_task_id", "tiles_total",
            "tiles_procesados", "imagenes_procesadas",
        ])
        return Response(VueloSerializer(vuelo, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="results")
    def results(self, request, pk=None):
        vuelo = self.get_object()
        imagenes = vuelo.imagenes.all().order_by("creado_en")
        return Response(
            {
                "vuelo": VueloDetalleSerializer(vuelo).data,
                "imagenes": ImagenSerializer(
                    imagenes, many=True, context={"request": request}
                ).data,
            }
        )

    @action(detail=True, methods=["get"], url_path="detecciones-mapa")
    def detecciones_mapa(self, request, pk=None):
        """
        GET /api/vuelos/{id}/detecciones-mapa/?min_confidence=0.5
        Devuelve un GeoJSON FeatureCollection con las detecciones
        georreferenciadas del vuelo, para pintar en el mapa de detalle.
        """
        try:
            min_conf = float(request.query_params.get("min_confidence", 0.5))
        except (TypeError, ValueError):
            min_conf = 0.5
        min_conf = max(0.0, min(1.0, min_conf))

        detecciones = list(
            Deteccion.objects.filter(
                imagen__vuelo_id=pk,
                ubicacion__isnull=False,
                confianza__gte=min_conf,
            )
            .select_related("imagen")
            .order_by("id")
        )
        serializer = DeteccionMapaSerializer(detecciones, many=True)
        data = serializer.data

        # Agregar el bbox geográfico de cada detección (proyectando las
        # esquinas píxel→WGS84) para poder dibujar recuadros sobre la ortofoto.
        bboxes = self._bbox_geo_por_deteccion(detecciones)
        if bboxes:
            for feature in data.get("features", []):
                bbox = bboxes.get(feature.get("id"))
                if bbox:
                    feature["properties"]["bbox"] = bbox

        return Response(data)

    @staticmethod
    def _bbox_geo_por_deteccion(detecciones):
        """
        Devuelve {deteccion_id: [west, south, east, north]} proyectando las
        esquinas de cada bounding box píxel→WGS84 con el transform/CRS del
        GeoTIFF de su imagen.

        Proyecta TODAS las esquinas de cada imagen en una sola llamada
        vectorizada (no punto a punto): con decenas de miles de detecciones
        esto baja de ~1 min a ~1 s y es lo que destrababa el mapa.
        """
        from collections import defaultdict

        por_imagen = defaultdict(list)
        for det in detecciones:
            por_imagen[det.imagen].append(det)

        bboxes = {}
        for imagen, dets in por_imagen.items():
            nombre = (
                imagen.nombre_original or imagen.archivo.name or ""
            ).lower()
            if not nombre.endswith((".tif", ".tiff")):
                continue

            xs: list[float] = []
            ys: list[float] = []
            for det in dets:
                xs += [det.x_min, det.x_max, det.x_max, det.x_min]
                ys += [det.y_min, det.y_min, det.y_max, det.y_max]

            try:
                lons, lats = GeoService.proyectar_pixeles_desde_tiff(
                    imagen.archivo.path, xs, ys
                )
            except Exception:  # noqa: BLE001
                lons = lats = None
            if not lons:
                continue

            for i, det in enumerate(dets):
                j = i * 4
                dl = lons[j:j + 4]
                da = lats[j:j + 4]
                if len(dl) < 4 or len(da) < 4:
                    continue
                bboxes[det.id] = [min(dl), min(da), max(dl), max(da)]
        return bboxes

    @action(detail=True, methods=["get"], url_path="raster-overlay")
    def raster_overlay(self, request, pk=None):
        """
        GET /api/vuelos/{id}/raster-overlay/
        Por cada imagen GeoTIFF georreferenciada del vuelo devuelve los bounds
        WGS84 para superponer la ortofoto en el mapa (imageOverlay de Leaflet).
        El preview JPG se sirve por /api/imagenes/{id}/preview/.
        """
        overlays = []
        for imagen in Imagen.objects.filter(vuelo_id=pk):
            nombre = (
                imagen.nombre_original or imagen.archivo.name or ""
            ).lower()
            if not nombre.endswith((".tif", ".tiff")):
                continue
            try:
                b = TiffService.preview_bounds(imagen.archivo.path)
            except Exception:  # noqa: BLE001
                continue
            if not b:
                continue
            overlays.append(
                {
                    "imagen_id": imagen.id,
                    "nombre": imagen.nombre_original,
                    "bounds": [
                        [b["south"], b["west"]],
                        [b["north"], b["east"]],
                    ],
                    # Zoom XYZ que iguala la resolución nativa del GeoTIFF: el
                    # frontend lo usa como maxNativeZoom de la capa de tiles.
                    "max_native_zoom": TiffService.tile_native_maxzoom(
                        imagen.archivo.path
                    ),
                }
            )
        return Response({"overlays": overlays})

    @action(detail=True, methods=["get"], url_path="export-csv")
    def export_csv(self, request, pk=None):
        vuelo = self.get_object()

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="vuelo_{pk}_resultados.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            ["imagen", "nombre_original", "procesada", "conteo_plantas", "creado_en"]
        )

        for imagen in vuelo.imagenes.all().order_by("creado_en"):
            writer.writerow(
                [
                    imagen.id,
                    imagen.nombre_original,
                    imagen.procesada,
                    imagen.conteo_plantas,
                    imagen.creado_en.isoformat(),
                ]
            )

        return response


class ImagenViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ImagenSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Imagen.objects.all()
        vuelo_id = self.request.query_params.get("vuelo_id")
        if vuelo_id:
            qs = qs.filter(vuelo_id=vuelo_id)
        solo_tiff = self.request.query_params.get("solo_tiff")
        if solo_tiff in ("1", "true", "True"):
            qs = qs.filter(
                Q(nombre_original__iendswith=".tif")
                | Q(nombre_original__iendswith=".tiff")
            )
        return qs

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        """
        GET /api/imagenes/{id}/preview/
        Devuelve un JPG reescalado del GeoTIFF para usarlo como imageOverlay
        en el mapa. Cachea el preview en disco para no re-renderizar en cada
        request (se regenera si el GeoTIFF cambió).
        """
        imagen = self.get_object()
        nombre = (imagen.nombre_original or imagen.archivo.name or "").lower()
        if not nombre.endswith((".tif", ".tiff")):
            return Response(
                {"error": "La imagen no es un GeoTIFF."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            tiff_path = imagen.archivo.path
        except (ValueError, FileNotFoundError):
            return Response(
                {"error": "Archivo no disponible."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cache_dir = Path(settings.MEDIA_ROOT) / "overlays"
        # El lado máximo va en el nombre: al cambiar la resolución del preview
        # (setting/env) se invalida el caché viejo sin tocar el GeoTIFF.
        max_dim = getattr(settings, "ORTOFOTO_PREVIEW_MAX_DIM", 4096)
        out_path = cache_dir / f"imagen_{imagen.id}_{max_dim}.jpg"
        if not out_path.exists() or (
            os.path.getmtime(tiff_path) > os.path.getmtime(out_path)
        ):
            info = TiffService.generar_preview_web(tiff_path, out_path)
            if info is None:
                return Response(
                    {"error": "El GeoTIFF no está georreferenciado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with open(out_path, "rb") as f:
            data = f.read()
        response = HttpResponse(data, content_type="image/jpeg")
        response["Content-Length"] = len(data)
        response["Cache-Control"] = "private, max-age=3600"
        return response

    @action(detail=True, methods=["get"], url_path="annotated")
    def annotated(self, request, pk=None):
        """
        GET /api/imagenes/{id}/annotated/
        Genera JPG con bounding boxes usando OpenCV.
        """
        imagen = self.get_object()

        if not imagen.procesada:
            return Response(
                {"error": "La imagen no ha sido procesada todavía."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            min_conf = float(request.query_params.get("min_confidence", 0.5))
        except (TypeError, ValueError):
            min_conf = 0.5
        min_conf = max(0.0, min(1.0, min_conf))
        force_dl = (
            request.query_params.get("download", "false").lower() == "true"
        )

        detecciones = list(
            imagen.detecciones.filter(confianza__gte=min_conf).values(
                "confianza", "x_min", "y_min", "x_max", "y_max", "clase"
            )
        )

        try:
            jpg_bytes, escala = AnnotationService.generar_imagen_anotada(
                imagen_path=imagen.archivo.path,
                detecciones=detecciones,
                min_confidence=min_conf,
            )
        except FileNotFoundError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Error generando JPG anotado de imagen %s", pk)
            return Response(
                {"error": f"No se pudo generar la imagen anotada: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        base = imagen.nombre_original.rsplit(".", 1)[0]
        nombre = f"anotada_{base}.jpg"
        disposition = "attachment" if force_dl else "inline"

        response = HttpResponse(jpg_bytes, content_type="image/jpeg")
        response["Content-Disposition"] = (
            f'{disposition}; filename="{nombre}"'
        )
        response["Content-Length"] = len(jpg_bytes)
        # Factor de decimado: el frontend reescala las cajas que dibuja sobre
        # el JPG (las ortofotos gigapíxel se sirven submuestreadas).
        response["X-Annotated-Scale"] = repr(float(escala))
        return response

    @action(detail=True, methods=["post"], url_path="marcar-revisada")
    def marcar_revisada(self, request, pk=None):
        """
        POST /api/imagenes/{id}/marcar-revisada/  body: {"revisada": bool}
        Marca/desmarca la imagen como revisada por un humano. Sus detecciones
        actuales se usan como verdad de referencia para reentrenar.
        """
        from django.utils import timezone

        imagen = self.get_object()
        revisada = bool(request.data.get("revisada", True))
        imagen.revisada = revisada
        imagen.revisada_en = timezone.now() if revisada else None
        imagen.save(update_fields=["revisada", "revisada_en"])
        return Response(ImagenSerializer(imagen).data)


class ImagenTileView(APIView):
    """
    GET /api/imagenes/{id}/tiles/{z}/{x}/{y}.png

    Sirve tiles XYZ (slippy map) leídos del GeoTIFF a resolución nativa, para
    que la ortofoto se vea nítida al hacer zoom (en vez de un único JPG estirado
    por Leaflet). Cada tile se cachea en disco; se regenera si el GeoTIFF cambió.
    Devuelve 204 para tiles fuera de la extensión de la ortofoto.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, z, x, y):
        try:
            imagen = Imagen.objects.get(pk=pk)
        except Imagen.DoesNotExist:
            return HttpResponse(status=404)

        nombre = (imagen.nombre_original or imagen.archivo.name or "").lower()
        if not nombre.endswith((".tif", ".tiff")):
            return HttpResponse(status=404)
        try:
            tiff_path = imagen.archivo.path
        except (ValueError, FileNotFoundError):
            return HttpResponse(status=404)

        # La primera vez (sin overviews) lanzamos la generación en segundo
        # plano para que los próximos tiles sean nítidos y rápidos a cualquier
        # zoom. Es idempotente y está protegida con lock, pero solo encolamos si
        # aún no está lista ni en curso, para no inundar la cola de Celery.
        if TiffService._overviews_listos(tiff_path) is None:
            lock = Path(str(TiffService._ruta_overviews(tiff_path)) + ".building")
            if not lock.exists():
                from apps.vision.tasks import construir_overviews_ortofoto_task

                construir_overviews_ortofoto_task.delay(tiff_path)

        cache_path = (
            Path(settings.MEDIA_ROOT)
            / "tiles_xyz"
            / f"imagen_{imagen.id}"
            / str(z)
            / str(x)
            / f"{y}.png"
        )
        if cache_path.exists() and (
            os.path.getmtime(cache_path) >= os.path.getmtime(tiff_path)
        ):
            with open(cache_path, "rb") as f:
                data = f.read()
        else:
            data = TiffService.generar_tile_xyz(tiff_path, z, x, y)
            if data is None:
                return HttpResponse(status=204)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".png.tmp")
            with open(tmp, "wb") as f:
                f.write(data)
            tmp.replace(cache_path)

        response = HttpResponse(data, content_type="image/png")
        response["Content-Length"] = len(data)
        response["Cache-Control"] = "private, max-age=86400"
        return response


def _recalcular_conteos(imagen):
    """Recalcula el conteo de la imagen y el total del vuelo tras editar
    detecciones manualmente (idempotente, misma fuente de verdad que la task)."""
    from django.db.models import Sum

    imagen.conteo_plantas = imagen.detecciones.count()
    imagen.save(update_fields=["conteo_plantas"])
    vuelo = imagen.vuelo
    vuelo.total_plantas = (
        vuelo.imagenes.aggregate(total=Sum("conteo_plantas"))["total"] or 0
    )
    vuelo.save(update_fields=["total_plantas"])


def _georreferenciar_deteccion(deteccion):
    """Proyecta el centro de la caja a WGS84 si la imagen es georreferenciable."""
    from apps.vision.tasks import referencer_para_imagen

    referencer = referencer_para_imagen(deteccion.imagen)
    if referencer is None:
        return
    cx = (deteccion.x_min + deteccion.x_max) / 2
    cy = (deteccion.y_min + deteccion.y_max) / 2
    deteccion.ubicacion = referencer(cx, cy)
    deteccion.save(update_fields=["ubicacion"])


class DeteccionViewSet(viewsets.ModelViewSet):
    """
    GET    /api/detecciones/?imagen_id=  → todas las cajas de una imagen
    POST   /api/detecciones/             → crear caja manual (planta faltante)
    PUT    /api/detecciones/{id}/        → mover/redimensionar una caja
    DELETE /api/detecciones/{id}/        → borrar caja (falso positivo)

    Toda edición marca origen=manual/corregida, recalcula conteos, intenta
    georreferenciar y registra la corrección para el reentrenamiento activo.
    """

    permission_classes = [IsAuthenticated]
    # El visor necesita TODAS las detecciones de una imagen para dibujar los
    # boxes; sin esto la paginación global (PAGE_SIZE=20) recorta el resultado.
    pagination_class = None
    http_method_names = ["get", "post", "put", "patch", "delete"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return DeteccionEditSerializer
        return DeteccionSerializer

    def get_queryset(self):
        qs = Deteccion.objects.all()
        imagen_id = self.request.query_params.get("imagen_id")
        if imagen_id:
            qs = qs.filter(imagen_id=imagen_id)
        return qs.order_by("id")

    def perform_create(self, serializer):
        deteccion = serializer.save(
            origen=Deteccion.Origen.MANUAL,
            confianza=serializer.validated_data.get("confianza", 1.0),
            clase=serializer.validated_data.get("clase", "planta"),
        )
        _georreferenciar_deteccion(deteccion)
        _recalcular_conteos(deteccion.imagen)
        registrar_correccion(1)

    def perform_update(self, serializer):
        # Una caja del modelo que se reubica pasa a 'corregida'; una manual
        # sigue siendo manual.
        instance = serializer.instance
        nuevo_origen = (
            Deteccion.Origen.MANUAL
            if instance.origen == Deteccion.Origen.MANUAL
            else Deteccion.Origen.CORREGIDA
        )
        deteccion = serializer.save(origen=nuevo_origen)
        _georreferenciar_deteccion(deteccion)
        _recalcular_conteos(deteccion.imagen)
        registrar_correccion(1)

    def perform_destroy(self, instance):
        imagen = instance.imagen
        instance.delete()
        _recalcular_conteos(imagen)
        registrar_correccion(1)


# --------------------------------------------------------------------------
# Dashboard stats
# --------------------------------------------------------------------------


class MapaGeneralView(APIView):
    """
    GET /api/mapa/campos-y-vuelos/
    Devuelve campos y vuelos georreferenciados (GeoJSON) para el mapa
    principal.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        campos = Campo.objects.filter(punto__isnull=False)
        vuelos = Vuelo.objects.filter(ubicacion__isnull=False).select_related(
            "modulo__campo"
        )
        return Response(
            {
                "campos": CampoGeoSerializer(campos, many=True).data,
                "vuelos": VueloGeoSerializer(vuelos, many=True).data,
            }
        )


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone

        hoy = timezone.now().date()
        return Response(
            {
                "total_campos": Campo.objects.count(),
                "total_modulos": Modulo.objects.count(),
                "total_vuelos": Vuelo.objects.count(),
                "total_plantas": sum(
                    Vuelo.objects.values_list("total_plantas", flat=True)
                ),
                "vuelos_procesados_hoy": Vuelo.objects.filter(
                    estado=Vuelo.Estado.COMPLETADO,
                    actualizado_en__date=hoy,
                ).count(),
                "vuelos_procesando": Vuelo.objects.filter(
                    estado=Vuelo.Estado.PROCESANDO
                ).count(),
            }
        )
