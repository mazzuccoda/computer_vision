import json
import tempfile
import zipfile as zf
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DatasetEntrenamiento, ModeloEntrenado
from .serializers import DatasetSerializer, ModeloSerializer
from .tasks import train_model_task


class DatasetViewSet(viewsets.ModelViewSet):
    """
    POST /api/datasets/       → subir .zip (multipart) + validación inmediata
    GET  /api/datasets/       → listar
    GET  /api/datasets/{id}/  → detalle con reporte de validación
    """

    queryset = DatasetEntrenamiento.objects.all().order_by("-creado_en")
    serializer_class = DatasetSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dataset = serializer.save()

        from services.dataset_service import (
            DatasetService,
            DatasetValidationError,
        )

        try:
            dataset.estado = "validando"
            dataset.save(update_fields=["estado"])
            res = DatasetService.validar_y_preparar(dataset)
            dataset.num_imagenes = res["num_imagenes"]
            dataset.clases = res["clases"]
            dataset.reporte_validacion = res["reporte"]
            dataset.estado = "valido"
        except DatasetValidationError as e:
            dataset.estado = "invalido"
            dataset.reporte_validacion = {"error": str(e)}
        dataset.save()

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
        train_model_task.apply_async(args=[modelo.id], queue="training")
        return Response(
            ModeloSerializer(modelo).data, status=status.HTTP_201_CREATED
        )

    def destroy(self, request, *args, **kwargs):
        modelo = self.get_object()
        if modelo.activo:
            return Response(
                {"error": "Activar otro modelo antes de eliminar este."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
