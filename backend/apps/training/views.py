import json
import logging
import shutil
import tempfile
import zipfile as zf
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DatasetEntrenamiento, ModeloEntrenado
from .serializers import DatasetSerializer, ModeloSerializer
from .tasks import train_model_task, validate_dataset_task

logger = logging.getLogger(__name__)


class DatasetViewSet(viewsets.ModelViewSet):
    """
    POST /api/datasets/              → subir .zip (multipart) + validación async
    POST /api/datasets/upload-chunk/ → subir .zip por fragmentos (archivos grandes)
    GET  /api/datasets/              → listar
    GET  /api/datasets/{id}/         → detalle + estado de validación (polling)
    """

    queryset = DatasetEntrenamiento.objects.all().order_by("-creado_en")
    serializer_class = DatasetSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "delete"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dataset = serializer.save()
        self._lanzar_validacion(dataset)
        return Response(
            DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _lanzar_validacion(dataset: DatasetEntrenamiento) -> None:
        dataset.estado = DatasetEntrenamiento.Estado.VALIDANDO
        dataset.save(update_fields=["estado"])
        validate_dataset_task.delay(dataset.id)

    @action(
        detail=False,
        methods=["post"],
        url_path="upload-chunk",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_chunk(self, request):
        """Subida por fragmentos para datasets grandes.

        El cliente parte el .zip en fragmentos < límite del proxy/CDN (p. ej.
        Cloudflare corta en 100 MB) y los envía en orden con el mismo
        ``upload_id``. Al recibir el último se reensambla, se crea el dataset
        y se lanza la validación en Celery.
        """
        chunk = request.FILES.get("chunk")
        upload_id = request.data.get("upload_id", "")
        filename = request.data.get("filename", "")
        nombre = request.data.get("nombre", "")
        formato = request.data.get("formato", DatasetEntrenamiento.Formato.YOLO)
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
                {
                    "detail": "Fragmento recibido.",
                    "recibido": index + 1,
                    "total": total,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        assembled = tmp_dir / "assembled"
        with open(assembled, "wb") as out:
            for i in range(total):
                part = tmp_dir / f"{i:06d}.part"
                if not part.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return Response(
                        {
                            "detail": (
                                f"Falta el fragmento {i}; reintentá la subida."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                with open(part, "rb") as pf:
                    shutil.copyfileobj(pf, out, length=1024 * 1024)

        dataset = DatasetEntrenamiento(
            nombre=nombre or safe_name,
            formato=formato or DatasetEntrenamiento.Formato.YOLO,
        )
        with open(assembled, "rb") as f:
            dataset.archivo.save(safe_name, File(f), save=True)

        shutil.rmtree(tmp_dir, ignore_errors=True)

        self._lanzar_validacion(dataset)
        return Response(
            DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED
        )


class ModeloViewSet(viewsets.ModelViewSet):
    """
    POST   /api/modelos/                → crear y lanzar entrenamiento (Celery)
    GET    /api/modelos/                → listar (incluye cuál está activo)
    GET    /api/modelos/{id}/           → estado + epoca_actual + % + métricas
    GET    /api/modelos/{id}/results/   → métricas detalladas + URLs de gráficas
    POST   /api/modelos/{id}/activate/  → marcar activo → YOLOService recarga
    POST   /api/modelos/{id}/cancel/    → cancelar un entrenamiento en curso
    GET    /api/modelos/{id}/download/  → zip: best.pt + data.yaml + metrics.json
    DELETE /api/modelos/{id}/           → eliminar (bloqueado si está activo)
    """

    queryset = ModeloEntrenado.objects.all().order_by("-creado_en")
    serializer_class = ModeloSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        modelo = serializer.save()
        async_result = train_model_task.apply_async(
            args=[modelo.id], queue="training"
        )
        modelo.celery_task_id = async_result.id
        modelo.save(update_fields=["celery_task_id"])
        return Response(
            ModeloSerializer(modelo).data, status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _detener_tarea(modelo) -> None:
        """Mata la tarea de Celery del entrenamiento (sin reiniciar el worker).

        SIGKILL al proceso hijo del pool que la ejecuta; el worker se recupera
        solo. Si no hay task_id (corridas viejas) no hace nada.
        """
        if not modelo.celery_task_id:
            return
        try:
            from config.celery import app

            app.control.revoke(
                modelo.celery_task_id, terminate=True, signal="SIGKILL"
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "No se pudo revocar la tarea Celery %s del modelo %s",
                modelo.celery_task_id,
                modelo.pk,
            )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        modelo = self.get_object()
        if modelo.estado not in ModeloEntrenado.ESTADOS_EN_PROGRESO:
            return Response(
                {"error": "El entrenamiento no está en curso."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self._detener_tarea(modelo)
        modelo.estado = ModeloEntrenado.Estado.CANCELADO
        modelo.error_mensaje = "Cancelado por el usuario."
        modelo.save(update_fields=["estado", "error_mensaje"])
        return Response(ModeloSerializer(modelo).data)

    def destroy(self, request, *args, **kwargs):
        modelo = self.get_object()
        if modelo.activo:
            return Response(
                {"error": "Activar otro modelo antes de eliminar este."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if modelo.estado in ModeloEntrenado.ESTADOS_EN_PROGRESO:
            self._detener_tarea(modelo)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        modelo = self.get_object()
        run_dir = (
            Path(settings.MEDIA_ROOT)
            / "training_runs"
            / f"modelo_{pk}_{modelo.version}"
            / "train"
        )
        imagenes = {}
        for img in ["results.png", "confusion_matrix.png", "PR_curve.png"]:
            p = run_dir / img
            if p.exists():
                imagenes[img] = request.build_absolute_uri(
                    settings.MEDIA_URL
                    + f"training_runs/modelo_{pk}_{modelo.version}/train/{img}"
                )
        return Response(
            {
                "metricas": modelo.metricas,
                "imagenes": imagenes,
                "porcentaje": modelo.porcentaje,
                "epoca_actual": modelo.epoca_actual,
                "epochs": modelo.epochs,
            }
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        modelo = self.get_object()
        if modelo.estado != ModeloEntrenado.Estado.COMPLETADO:
            return Response(
                {"error": "Solo se puede activar un modelo completado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not modelo.archivo_pesos:
            return Response(
                {"error": "Modelo sin pesos guardados."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        modelo.activo = True
        modelo.save()
        from django.core.cache import cache

        cache.set("yolo_model_reload", modelo.id, timeout=60)
        from services.yolo_service import YOLOService

        YOLOService.get_instance().reload_model()
        return Response(
            {
                "status": "activado",
                "modelo_id": modelo.id,
                "version": modelo.version,
            }
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        modelo = self.get_object()
        if not modelo.archivo_pesos:
            return Response(
                {"error": "Sin pesos disponibles."},
                status=status.HTTP_404_NOT_FOUND,
            )
        with tempfile.NamedTemporaryFile(
            suffix=".zip", delete=False
        ) as tmp:
            with zf.ZipFile(tmp, "w", zf.ZIP_DEFLATED) as z:
                pesos = Path(settings.MEDIA_ROOT) / modelo.archivo_pesos.name
                if pesos.exists():
                    z.write(pesos, "best.pt")
                run_dir = (
                    Path(settings.MEDIA_ROOT)
                    / "training_runs"
                    / f"modelo_{pk}_{modelo.version}"
                )
                if (run_dir / "data.yaml").exists():
                    z.write(run_dir / "data.yaml", "data.yaml")
                z.writestr(
                    "metrics.json",
                    json.dumps(
                        modelo.metricas, indent=2, ensure_ascii=False
                    ),
                )
                for img in ["results.png", "confusion_matrix.png"]:
                    p = run_dir / "train" / img
                    if p.exists():
                        z.write(p, img)
            tmp_path = tmp.name
        resp = FileResponse(
            open(tmp_path, "rb"), content_type="application/zip"
        )
        resp["Content-Disposition"] = (
            f'attachment; filename="modelo_{modelo.version}_{modelo.nombre}.zip"'
        )
        return resp
