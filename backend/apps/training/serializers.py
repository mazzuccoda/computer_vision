from rest_framework import serializers

from .models import DatasetEntrenamiento, ModeloEntrenado


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetEntrenamiento
        fields = [
            "id",
            "nombre",
            "archivo",
            "formato",
            "num_imagenes",
            "clases",
            "estado",
            "reporte_validacion",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            "num_imagenes",
            "clases",
            "estado",
            "reporte_validacion",
            "creado_en",
        ]


class ModeloSerializer(serializers.ModelSerializer):
    dataset_nombre = serializers.CharField(
        source="dataset.nombre", read_only=True
    )
    porcentaje = serializers.FloatField(read_only=True)

    class Meta:
        model = ModeloEntrenado
        fields = [
            "id",
            "nombre",
            "version",
            "dataset",
            "dataset_nombre",
            "base_model",
            "epochs",
            "img_size",
            "patience",
            "estado",
            "epoca_actual",
            "porcentaje",
            "metricas",
            "archivo_pesos",
            "activo",
            "notas",
            "error_mensaje",
            "creado_en",
            "completado_en",
        ]
        read_only_fields = [
            "id",
            "version",
            "dataset_nombre",
            "estado",
            "epoca_actual",
            "porcentaje",
            "metricas",
            "archivo_pesos",
            "activo",
            "error_mensaje",
            "creado_en",
            "completado_en",
        ]
