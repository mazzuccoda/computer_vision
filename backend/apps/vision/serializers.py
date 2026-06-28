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


def _geo_bbox_a_pixel(imagen, geo_bbox):
    """
    Convierte una caja geográfica [west, south, east, north] (WGS84) a
    coordenadas de píxel (x_min, y_min, x_max, y_max) de la imagen, usando el
    transform/CRS embebido en su GeoTIFF. Recorta a los límites de la imagen.

    Devuelve None si la imagen no es un GeoTIFF georreferenciado o la
    proyección falla.
    """
    import rasterio

    from services.geo_service import GeoService

    nombre = (imagen.nombre_original or imagen.archivo.name or "").lower()
    if not nombre.endswith((".tif", ".tiff")):
        return None
    try:
        tiff_path = imagen.archivo.path
    except (ValueError, FileNotFoundError):
        return None

    proyectar = GeoService.referencer_inverso_desde_tiff(tiff_path)
    if proyectar is None:
        return None

    west, south, east, north = geo_bbox
    esquinas = [
        proyectar(west, north),
        proyectar(east, north),
        proyectar(east, south),
        proyectar(west, south),
    ]
    puntos = [p for p in esquinas if p is not None]
    if len(puntos) < 4:
        return None

    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    try:
        with rasterio.open(tiff_path) as src:
            ancho, alto = src.width, src.height
        x_min = max(0.0, min(x_min, ancho))
        x_max = max(0.0, min(x_max, ancho))
        y_min = max(0.0, min(y_min, alto))
        y_max = max(0.0, min(y_max, alto))
    except Exception:  # noqa: BLE001
        pass

    if x_max <= x_min or y_max <= y_min:
        return None
    return x_min, y_min, x_max, y_max


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
            "tiles_total",
            "tiles_procesados",
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
            "tiles_total",
            "tiles_procesados",
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
            "origen",
        ]
        read_only_fields = fields


class DeteccionEditSerializer(serializers.ModelSerializer):
    """
    Crear / actualizar una detección manualmente desde el visor (píxeles) o
    desde el mapa (coordenadas geográficas, vía ``geo_bbox``).
    """

    # Caja en coordenadas geográficas [west, south, east, north] (WGS84).
    # Si se envía, se convierte a píxeles con el transform del GeoTIFF de la
    # imagen; permite editar detecciones dibujando sobre la ortofoto del mapa.
    geo_bbox = serializers.ListField(
        child=serializers.FloatField(),
        min_length=4,
        max_length=4,
        write_only=True,
        required=False,
    )

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
            "origen",
            "geo_bbox",
        ]
        read_only_fields = ["id", "origen"]
        extra_kwargs = {
            "imagen": {"required": False},
            "confianza": {"required": False},
            "clase": {"required": False},
            "x_min": {"required": False},
            "y_min": {"required": False},
            "x_max": {"required": False},
            "y_max": {"required": False},
        }

    def validate(self, attrs):
        geo_bbox = attrs.pop("geo_bbox", None)
        if geo_bbox is not None:
            imagen = attrs.get("imagen") or getattr(
                self.instance, "imagen", None
            )
            if imagen is None:
                raise serializers.ValidationError(
                    "Se requiere 'imagen' para convertir geo_bbox a píxeles."
                )
            px = _geo_bbox_a_pixel(imagen, geo_bbox)
            if px is None:
                raise serializers.ValidationError(
                    "La imagen no es un GeoTIFF georreferenciado; no se puede "
                    "convertir geo_bbox a píxeles."
                )
            attrs["x_min"], attrs["y_min"], attrs["x_max"], attrs["y_max"] = px

        x_min = attrs.get("x_min", getattr(self.instance, "x_min", None))
        y_min = attrs.get("y_min", getattr(self.instance, "y_min", None))
        x_max = attrs.get("x_max", getattr(self.instance, "x_max", None))
        y_max = attrs.get("y_max", getattr(self.instance, "y_max", None))
        if None in (x_min, y_min, x_max, y_max):
            raise serializers.ValidationError("Faltan coordenadas de la caja.")
        if x_max <= x_min or y_max <= y_min:
            raise serializers.ValidationError(
                "La caja debe tener x_max>x_min y y_max>y_min."
            )
        return attrs


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
            "revisada",
            "revisada_en",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            "nombre_original",
            "procesada",
            "conteo_plantas",
            "revisada",
            "revisada_en",
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
        fields = ["id", "confianza", "clase", "origen", "imagen"]
