from django.contrib.gis.geos import Point
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import Campo, Deteccion, Imagen, Modulo, Vuelo


def _punto_desde_latlon(latitud, longitud) -> Point | None:
    """Crea un Point WGS84 (lon, lat) a partir de lat/lon planos, o None."""
    if latitud is None or longitud is None:
        return None
    try:
        return Point(float(longitud), float(latitud), srid=4326)
    except (TypeError, ValueError):
        return None


class CampoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campo
        fields = [
            "id",
            "nombre",
            "descripcion",
            "ubicacion",
            "latitud",
            "longitud",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["id", "creado_en", "actualizado_en"]

    def create(self, validated_data):
        campo = super().create(validated_data)
        punto = _punto_desde_latlon(campo.latitud, campo.longitud)
        if punto:
            campo.punto = punto
            campo.save(update_fields=["punto"])
        return campo

    def update(self, instance, validated_data):
        campo = super().update(instance, validated_data)
        punto = _punto_desde_latlon(campo.latitud, campo.longitud)
        if punto:
            campo.punto = punto
            campo.save(update_fields=["punto"])
        return campo


class ModuloSerializer(serializers.ModelSerializer):
    campo_nombre = serializers.CharField(source="campo.nombre", read_only=True)

    class Meta:
        model = Modulo
        fields = [
            "id",
            "campo",
            "campo_nombre",
            "nombre",
            "descripcion",
            "creado_en",
        ]
        read_only_fields = ["id", "campo_nombre", "creado_en"]


class VueloSerializer(serializers.ModelSerializer):
    modulo_nombre = serializers.CharField(source="modulo.nombre", read_only=True)
    porcentaje_procesado = serializers.FloatField(read_only=True)

    class Meta:
        model = Vuelo
        fields = [
            "id",
            "modulo",
            "modulo_nombre",
            "nombre",
            "fecha_vuelo",
            "estado",
            "total_plantas",
            "total_imagenes",
            "imagenes_procesadas",
            "porcentaje_procesado",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = [
            "id",
            "modulo_nombre",
            "estado",
            "total_plantas",
            "total_imagenes",
            "imagenes_procesadas",
            "porcentaje_procesado",
            "creado_en",
            "actualizado_en",
        ]


class DeteccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deteccion
        fields = [
            "id",
            "imagen",
            "confianza",
            "x_min",
            "y_min",
            "x_max",
            "y_max",
            "clase",
        ]
        read_only_fields = fields


class ImagenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Imagen
        fields = [
            "id",
            "vuelo",
            "archivo",
            "nombre_original",
            "procesada",
            "conteo_plantas",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            "nombre_original",
            "procesada",
            "conteo_plantas",
            "creado_en",
        ]


class VueloDetalleSerializer(VueloSerializer):
    """Vuelo with nested module/field context for the detail screen."""

    campo = serializers.IntegerField(source="modulo.campo.id", read_only=True)
    campo_nombre = serializers.CharField(
        source="modulo.campo.nombre", read_only=True
    )

    class Meta(VueloSerializer.Meta):
        fields = VueloSerializer.Meta.fields + ["campo", "campo_nombre"]


# --------------------------------------------------------------------------
# GeoJSON serializers (solo para los endpoints de mapa Leaflet)
# --------------------------------------------------------------------------


class CampoGeoSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Campo
        geo_field = "punto"
        fields = ["id", "nombre", "descripcion", "ubicacion"]


class VueloGeoSerializer(GeoFeatureModelSerializer):
    campo = serializers.IntegerField(source="modulo.campo.id", read_only=True)
    campo_nombre = serializers.CharField(
        source="modulo.campo.nombre", read_only=True
    )

    class Meta:
        model = Vuelo
        geo_field = "ubicacion"
        fields = [
            "id",
            "nombre",
            "estado",
            "total_plantas",
            "fecha_vuelo",
            "campo",
            "campo_nombre",
        ]


class DeteccionMapaSerializer(GeoFeatureModelSerializer):
    """
    Serializer liviano para el mapa: solo lo necesario para pintar un
    marcador, no todos los campos de Deteccion.
    """

    class Meta:
        model = Deteccion
        geo_field = "ubicacion"
        fields = ["id", "confianza", "clase"]
