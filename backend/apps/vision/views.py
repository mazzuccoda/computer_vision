import csv
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files import File
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
    DeteccionMapaSerializer,
    DeteccionSerializer,
    ImagenSerializer,
    ModuloSerializer,
    VueloDetalleSerializer,
    VueloGeoSerializer,
    VueloSerializer,
)
from .tasks import process_vuelo_task
from services.annotation_service import AnnotationService
from services.geo_service import GeoService
from services.tiff_service import TiffService

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

        # Reset progress counters before (re)processing.
        vuelo.estado = Vuelo.Estado.PENDIENTE
        vuelo.imagenes_procesadas = vuelo.imagenes.filter(procesada=True).count()
        vuelo.save(update_fields=["estado", "imagenes_procesadas"])

        process_vuelo_task.delay(vuelo.id)
        return Response(
            {"detail": "Procesamiento iniciado.", "vuelo_id": vuelo.id},
            status=status.HTTP_202_ACCEPTED,
        )

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
        GeoTIFF de su imagen. Abre cada GeoTIFF una sola vez.
        """
        referencers = {}
        bboxes = {}
        for det in detecciones:
            imagen = det.imagen
            if imagen.id not in referencers:
                ref = None
                nombre = (
                    imagen.nombre_original or imagen.archivo.name or ""
                ).lower()
                if nombre.endswith((".tif", ".tiff")):
                    try:
                        ref = GeoService.referencer_desde_tiff(
                            imagen.archivo.path
                        )
                    except Exception:  # noqa: BLE001
                        ref = None
                referencers[imagen.id] = ref

            ref = referencers[imagen.id]
            if ref is None:
                continue
            p1 = ref(det.x_min, det.y_min)
            p2 = ref(det.x_max, det.y_max)
            if p1 and p2:
                lons = (p1.x, p2.x)
                lats = (p1.y, p2.y)
                bboxes[det.id] = [
                    min(lons),
                    min(lats),
                    max(lons),
                    max(lats),
                ]
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
                info = TiffService.leer_info(imagen.archivo.path)
            except Exception:  # noqa: BLE001
                continue
            b = info.bounds_geo
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
        out_path = cache_dir / f"imagen_{imagen.id}.jpg"
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
            jpg_bytes = AnnotationService.generar_imagen_anotada(
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

        base = imagen.nombre_original.rsplit(".", 1)[0]
        nombre = f"anotada_{base}.jpg"
        disposition = "attachment" if force_dl else "inline"

        response = HttpResponse(jpg_bytes, content_type="image/jpeg")
        response["Content-Disposition"] = (
            f'{disposition}; filename="{nombre}"'
        )
        response["Content-Length"] = len(jpg_bytes)
        return response


class DeteccionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeteccionSerializer
    permission_classes = [IsAuthenticated]
    # El visor necesita TODAS las detecciones de una imagen para dibujar los
    # boxes; sin esto la paginación global (PAGE_SIZE=20) recorta el resultado.
    pagination_class = None

    def get_queryset(self):
        qs = Deteccion.objects.all()
        imagen_id = self.request.query_params.get("imagen_id")
        if imagen_id:
            qs = qs.filter(imagen_id=imagen_id)
        return qs.order_by("id")


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
