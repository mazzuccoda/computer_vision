import csv
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

        detecciones = (
            Deteccion.objects.filter(
                imagen__vuelo_id=pk,
                ubicacion__isnull=False,
                confianza__gte=min_conf,
            )
            .select_related("imagen")
            .order_by("id")
        )
        serializer = DeteccionMapaSerializer(detecciones, many=True)
        return Response(serializer.data)

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

    def get_queryset(self):
        qs = Deteccion.objects.all()
        imagen_id = self.request.query_params.get("imagen_id")
        if imagen_id:
            qs = qs.filter(imagen_id=imagen_id)
        return qs


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
