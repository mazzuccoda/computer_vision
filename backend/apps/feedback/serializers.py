from rest_framework import serializers

from .models import CicloReentrenamiento, ConfiguracionReentrenamiento


class ConfiguracionReentrenamientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionReentrenamiento
        fields = [
            "auto_reentrenar",
            "umbral_correcciones",
            "auto_activar_modelo",
            "margen_map50",
            "epochs",
            "base_model",
            "correcciones_acumuladas",
            "ultimo_reentrenamiento",
            "actualizado_en",
        ]
        read_only_fields = [
            "correcciones_acumuladas",
            "ultimo_reentrenamiento",
            "actualizado_en",
        ]


class CicloReentrenamientoSerializer(serializers.ModelSerializer):
    modelo_nombre = serializers.SerializerMethodField()
    modelo_version = serializers.SerializerMethodField()

    class Meta:
        model = CicloReentrenamiento
        fields = [
            "id",
            "disparador",
            "estado",
            "num_correcciones",
            "num_imagenes",
            "num_anotaciones",
            "dataset",
            "modelo",
            "modelo_nombre",
            "modelo_version",
            "map50_anterior",
            "map50_nuevo",
            "activado",
            "mensaje",
            "creado_en",
            "completado_en",
        ]
        read_only_fields = fields

    def get_modelo_nombre(self, obj):
        return obj.modelo.nombre if obj.modelo else None

    def get_modelo_version(self, obj):
        return obj.modelo.version if obj.modelo else None
