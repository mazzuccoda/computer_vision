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
    def referencer_desde_tiff(tiff_path: str):
        """
        Construye un proyector píxel→WGS84 leyendo el transform afín y el CRS
        embebidos en el propio GeoTIFF (sin depender del módulo converter).

        Returns:
            Una función (x_px, y_px) -> Point|None en coordenadas de la imagen
            completa, o None si el archivo no es un GeoTIFF georreferenciado.
        """
        import rasterio
        from rasterio.crs import CRS
        from rasterio.warp import transform as warp_transform

        try:
            src = rasterio.open(tiff_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo abrir TIFF para georreferenciar: {e}")
            return None

        if not src.crs:
            src.close()
            return None

        transform = src.transform
        src_crs = src.crs
        dst_crs = CRS.from_epsg(4326)
        src.close()

        def proyectar(x_px: float, y_px: float) -> Point | None:
            try:
                x_crs, y_crs = transform * (x_px, y_px)
                lon, lat = warp_transform(src_crs, dst_crs, [x_crs], [y_crs])
                lon, lat = lon[0], lat[0]
                if lon == 0 and lat == 0:
                    return None
                return Point(lon, lat, srid=4326)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Error proyectando píxel a geo desde TIFF: {e}")
                return None

        return proyectar

    @staticmethod
    def referencer_inverso_desde_tiff(tiff_path: str):
        """
        Construye un proyector WGS84→píxel: el inverso de
        ``referencer_desde_tiff``. Sirve para persistir cajas dibujadas en el
        mapa (coordenadas geográficas) como bounding boxes en píxeles de la
        imagen completa.

        Returns:
            Una función (lon, lat) -> (x_px, y_px)|None, o None si el archivo
            no es un GeoTIFF georreferenciado.
        """
        import rasterio
        from rasterio.crs import CRS
        from rasterio.warp import transform as warp_transform

        try:
            src = rasterio.open(tiff_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo abrir TIFF para geo→píxel: {e}")
            return None

        if not src.crs:
            src.close()
            return None

        transform = src.transform
        src_crs = src.crs
        src.close()
        inverso = ~transform
        dst_crs = CRS.from_epsg(4326)

        def proyectar(lon: float, lat: float):
            try:
                xs, ys = warp_transform(dst_crs, src_crs, [lon], [lat])
                col, row = inverso * (xs[0], ys[0])
                return float(col), float(row)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Error proyectando geo→píxel desde TIFF: {e}")
                return None

        return proyectar

    @staticmethod
    def centroide_desde_tiff(tiff_path: str) -> Point | None:
        """
        Centro geográfico (WGS84) de un GeoTIFF leyendo sus bounds directamente
        del archivo. Usado para Vuelo.ubicacion cuando el GeoTIFF se subió
        directo al vuelo (sin pasar por el módulo converter).
        """
        import rasterio
        from rasterio.crs import CRS
        from rasterio.warp import transform_bounds

        try:
            with rasterio.open(tiff_path) as src:
                if not src.crs:
                    return None
                west, south, east, north = transform_bounds(
                    src.crs,
                    CRS.from_epsg(4326),
                    src.bounds.left,
                    src.bounds.bottom,
                    src.bounds.right,
                    src.bounds.top,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo leer centroide del TIFF: {e}")
            return None

        lon = (west + east) / 2
        lat = (south + north) / 2
        if lon == 0 and lat == 0:
            return None
        return Point(lon, lat, srid=4326)

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
