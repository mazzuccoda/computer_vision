from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.training.models import ModeloEntrenado
from apps.vision.models import Imagen

from .models import CicloReentrenamiento, ConfiguracionReentrenamiento
from .serializers import (
    CicloReentrenamientoSerializer,
    ConfiguracionReentrenamientoSerializer,
)
from .services import lanzar_ciclo


class CicloReentrenamientoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/reentrenamiento/ciclos/        → historial de ciclos
    GET  /api/reentrenamiento/ciclos/{id}/   → detalle (polling de progreso)
    """

    queryset = CicloReentrenamiento.objects.all()
    serializer_class = CicloReentrenamientoSerializer
    permission_classes = [IsAuthenticated]


class ReentrenamientoViewSet(viewsets.ViewSet):
    """
    GET  /api/reentrenamiento/config/    → configuración actual
    PUT  /api/reentrenamiento/config/    → actualizar configuración
    GET  /api/reentrenamiento/estado/    → panel del ciclo (contador, modelos)
    POST /api/reentrenamiento/disparar/  → "Reentrenar ahora" (manual)
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get", "put"])
    def config(self, request):
        config = ConfiguracionReentrenamiento.get_solo()
        if request.method == "PUT":
            serializer = ConfiguracionReentrenamientoSerializer(
                config, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(ConfiguracionReentrenamientoSerializer(config).data)

    @action(detail=False, methods=["get"])
    def estado(self, request):
        config = ConfiguracionReentrenamiento.get_solo()
        activo = ModeloEntrenado.objects.filter(activo=True).first()
        ultimo = CicloReentrenamiento.objects.first()
        imagenes_revisadas = Imagen.objects.filter(revisada=True).count()

        return Response(
            {
                "config": ConfiguracionReentrenamientoSerializer(config).data,
                "imagenes_revisadas": imagenes_revisadas,
                "modelo_activo": (
                    {
                        "id": activo.id,
                        "nombre": activo.nombre,
                        "version": activo.version,
                        "map50": (activo.metricas or {}).get("map50"),
                    }
                    if activo
                    else None
                ),
                "ultimo_ciclo": (
                    CicloReentrenamientoSerializer(ultimo).data
                    if ultimo
                    else None
                ),
            }
        )

    @action(detail=False, methods=["post"])
    def disparar(self, request):
        ciclo = lanzar_ciclo("manual")
        if ciclo is None:
            return Response(
                {"error": "Ya hay un reentrenamiento en curso."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            CicloReentrenamientoSerializer(ciclo).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def activar(self, request):
        """
        POST /api/reentrenamiento/activar/  body: {"ciclo_id": N}
        Activa manualmente el modelo de un ciclo que terminó sin auto-activarse
        (bypass del gate de mAP50). Sirve para el botón "Activar de todas formas".
        """
        ciclo_id = request.data.get("ciclo_id")
        if not ciclo_id:
            return Response(
                {"error": "Falta ciclo_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ciclo = CicloReentrenamiento.objects.filter(id=ciclo_id).first()
        if ciclo is None or ciclo.modelo is None:
            return Response(
                {"error": "Ciclo o modelo inexistente."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if ciclo.modelo.estado != ModeloEntrenado.Estado.COMPLETADO:
            return Response(
                {"error": "El modelo del ciclo no está completado."},
                status=status.HTTP_409_CONFLICT,
            )
        from .tasks import _activar_modelo

        _activar_modelo(ciclo.modelo)
        ciclo.activado = True
        ciclo.estado = CicloReentrenamiento.Estado.ACTIVADO
        ciclo.mensaje = (
            (ciclo.mensaje or "") + " | Activado manualmente (bypass de mAP)."
        ).strip()
        ciclo.save(update_fields=["activado", "estado", "mensaje"])
        return Response(CicloReentrenamientoSerializer(ciclo).data)
