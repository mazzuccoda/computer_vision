import shutil
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from services.tiff_service import TiffService

from .models import SesionConversion
from .serializers import SesionConversionSerializer
from .tasks import convert_tiff_task

MEDIA_ROOT = Path(settings.MEDIA_ROOT)


class SesionConversionViewSet(viewsets.ModelViewSet):
    """
    POST   /api/converter/sesiones/               → crear sesión y lanzar Celery
    GET    /api/converter/sesiones/               → listar sesiones
    GET    /api/converter/sesiones/{id}/          → detalle + progreso (polling)
    GET    /api/converter/sesiones/{id}/info/     → info del TIFF + estimación
    GET    /api/converter/sesiones/{id}/download/ → descargar .zip de tiles
    DELETE /api/converter/sesiones/{id}/          → eliminar sesión y archivos
    """

    queryset = SesionConversion.objects.all().order_by("-creado_en")
    serializer_class = SesionConversionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete"]

    def _tiff_path(self, sesion: SesionConversion) -> str:
        if sesion.fuente == SesionConversion.FuenteTiff.UPLOAD:
            return str(MEDIA_ROOT / sesion.archivo_tiff.name)
        return sesion.imagen_vuelo.archivo.path

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sesion = serializer.save()

        # Validación rápida: verificar que el TIFF es legible
        try:
            info = TiffService.leer_info(self._tiff_path(sesion))
            sesion.metadatos_geo = {
                "crs": info.crs,
                "bounds": info.bounds_geo,
                "ancho_px": info.ancho,
                "alto_px": info.alto,
                "bandas": info.bandas,
                "res_m_per_px": info.res_m_per_px,
            }
            sesion.save(update_fields=["metadatos_geo"])
        except Exception as e:  # noqa: BLE001
            sesion.delete()
            return Response(
                {"error": f"No se puede leer el GeoTIFF: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lanzar conversión en Celery
        convert_tiff_task.apply_async(args=[sesion.id], queue="conversion")

        return Response(
            SesionConversionSerializer(sesion).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        sesion = self.get_object()
        if sesion.directorio_tiles:
            tiles_dir = MEDIA_ROOT / sesion.directorio_tiles
            if tiles_dir.exists():
                shutil.rmtree(tiles_dir)
        if sesion.archivo_zip and sesion.archivo_zip.name:
            zip_path = MEDIA_ROOT / sesion.archivo_zip.name
            if zip_path.exists():
                zip_path.unlink()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def info(self, request, pk=None):
        """
        Retorna info del GeoTIFF + estimación de tiles.
        Útil para preview antes de lanzar la conversión.
        """
        sesion = self.get_object()
        estimacion = (
            TiffService.calcular_total_tiles(
                self._tiff_path(sesion),
                sesion.tile_size,
                sesion.overlap_px,
            )
            if sesion.estado == SesionConversion.Estado.PENDIENTE
            else sesion.total_tiles
        )
        return Response(
            {
                "metadatos_geo": sesion.metadatos_geo,
                "estimacion_tiles": estimacion,
            }
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Descarga el .zip de tiles JPG."""
        sesion = self.get_object()
        if sesion.estado != SesionConversion.Estado.COMPLETADO:
            return Response(
                {"error": "La conversión no está completa todavía."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not sesion.archivo_zip:
            return Response(
                {"error": "El archivo .zip no está disponible."},
                status=status.HTTP_404_NOT_FOUND,
            )
        zip_path = MEDIA_ROOT / sesion.archivo_zip.name
        if not zip_path.exists():
            return Response(
                {"error": "Archivo .zip no encontrado en disco."},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = FileResponse(
            open(zip_path, "rb"), content_type="application/zip"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="tiles_{sesion.nombre}.zip"'
        )
        return response
