from rest_framework import serializers

from .models import SesionConversion


class SesionConversionSerializer(serializers.ModelSerializer):
    porcentaje = serializers.ReadOnlyField()
    nombre_archivo_fuente = serializers.ReadOnlyField()
    imagen_vuelo_nombre = serializers.SerializerMethodField()

    class Meta:
        model = SesionConversion
        fields = [
            "id",
            "nombre",
            "fuente",
            "archivo_tiff",
            "imagen_vuelo",
            "imagen_vuelo_nombre",
            "tile_size",
            "overlap_px",
            "calidad_jpg",
            "saltar_vacios",
            "estado",
            "total_tiles",
            "tiles_procesados",
            "porcentaje",
            "error_mensaje",
            "metadatos_geo",
            "directorio_tiles",
            "archivo_zip",
            "notas",
            "creado_en",
            "completado_en",
            "nombre_archivo_fuente",
        ]
        read_only_fields = [
            "estado",
            "total_tiles",
            "tiles_procesados",
            "porcentaje",
            "error_mensaje",
            "metadatos_geo",
            "directorio_tiles",
            "archivo_zip",
            "completado_en",
            "nombre_archivo_fuente",
        ]

    def get_imagen_vuelo_nombre(self, obj) -> str | None:
        if obj.imagen_vuelo:
            return obj.imagen_vuelo.nombre_original
        return None

    def validate(self, data):
        fuente = data.get("fuente", "upload")
        if fuente == "upload" and not data.get("archivo_tiff"):
            raise serializers.ValidationError(
                {"archivo_tiff": "Requerido para fuente upload."}
            )
        if fuente == "vuelo" and not data.get("imagen_vuelo"):
            raise serializers.ValidationError(
                {"imagen_vuelo": "Requerido para fuente vuelo."}
            )
        tile_size = data.get("tile_size")
        if tile_size and tile_size < 128:
            raise serializers.ValidationError(
                {"tile_size": "Tamaño mínimo: 128 px."}
            )
        overlap_px = data.get("overlap_px")
        if overlap_px is not None and tile_size:
            if overlap_px >= tile_size // 2:
                raise serializers.ValidationError(
                    {"overlap_px": "El solapamiento debe ser menor a tile_size / 2."}
                )
        return data
