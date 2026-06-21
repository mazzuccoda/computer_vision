import logging

from django.contrib.gis.geos import Point

logger = logging.getLogger(__name__)


class GeoService:
    """
    Convierte coordenadas de píxel (sistema de la imagen) a coordenadas
    geográficas (WGS84), usando los metadatos generados por el módulo
    converter (SesionConversion.metadatos_geo).
    """

    @staticmethod
    def centroide_desde_geotiff(metadatos_geo: dict) -> Point | None:
        """
        Calcula el punto central de un GeoTIFF a partir de sus bounds WGS84.
        Usado para Vuelo.ubicacion cuando hay un GeoTIFF asociado.

        Args:
            metadatos_geo: dict con estructura {bounds: {west, south, east,
                north}, ...} (la misma que genera TiffService.generar_tiles()).

        Returns:
            Point WGS84 (lon, lat) del centro del bounding box, o None si
            metadatos_geo no tiene bounds válidos.
        """
        bounds = metadatos_geo.get("bounds") if metadatos_geo else None
        if not bounds:
            return None

        try:
            lon = (bounds["west"] + bounds["east"]) / 2
            lat = (bounds["south"] + bounds["north"]) / 2
            if lon == 0 and lat == 0:
                return None  # bounds vacíos / no georreferenciados
            return Point(lon, lat, srid=4326)
        except (KeyError, TypeError) as e:
            logger.warning(f"Bounds inválidos en metadatos_geo: {e}")
            return None

    @staticmethod
    def pixel_a_geo(
        x_px: float,
        y_px: float,
        tile_bbox_geo: dict,
        tile_size_px: int,
    ) -> Point | None:
        """
        Proyecta una coordenada de píxel DENTRO de un tile a coordenadas
        geográficas, usando interpolación lineal sobre el bbox_geo del tile.

        Args:
            x_px, y_px:     coordenadas de píxel relativas al tile
                            (0 a tile_size_px).
            tile_bbox_geo:  {west, south, east, north} del tile, desde
                            metadatos_geo['tiles'][i]['bbox_geo'].
            tile_size_px:   tamaño del tile en píxeles (normalmente 640).

        Returns:
            Point WGS84, o None si tile_bbox_geo es inválido.
        """
        if not tile_bbox_geo or not tile_size_px:
            return None

        try:
            west, south = tile_bbox_geo["west"], tile_bbox_geo["south"]
            east, north = tile_bbox_geo["east"], tile_bbox_geo["north"]

            frac_x = max(0.0, min(1.0, x_px / tile_size_px))
            frac_y = max(0.0, min(1.0, y_px / tile_size_px))

            lon = west + frac_x * (east - west)
            # Y crece hacia abajo en píxeles, pero la latitud decrece hacia
            # el sur — por eso se invierte frac_y.
            lat = north - frac_y * (north - south)

            if lon == 0 and lat == 0:
                return None
            return Point(lon, lat, srid=4326)
        except (KeyError, TypeError, ZeroDivisionError) as e:
            logger.warning(f"Error proyectando píxel a geo: {e}")
            return None

    @staticmethod
    def centro_deteccion_a_geo(
        deteccion,
        tile_bbox_geo: dict,
        tile_size_px: int = 640,
    ) -> Point | None:
        """
        Calcula el punto geográfico del CENTRO de una bounding box de
        detección (no de una esquina), proyectándolo sobre el tile.
        """
        cx = (deteccion.x_min + deteccion.x_max) / 2
        cy = (deteccion.y_min + deteccion.y_max) / 2
        return GeoService.pixel_a_geo(cx, cy, tile_bbox_geo, tile_size_px)

    @staticmethod
    def tile_bbox_para_imagen(sesion, nombre_imagen: str):
        """
        Dado una SesionConversion y el nombre de archivo de una imagen,
        devuelve (tile_bbox_geo, tile_size_px) si esa imagen corresponde a
        un tile del metadatos_geo, o (None, 640) si no hay match.
        """
        meta = getattr(sesion, "metadatos_geo", None) or {}
        tiles = meta.get("tiles", [])
        tile_size_px = meta.get("tile_size", 640)
        tile_match = next(
            (t for t in tiles if t.get("nombre") == nombre_imagen),
            None,
        )
        if tile_match:
            return tile_match.get("bbox_geo"), tile_size_px
        return None, tile_size_px
