export interface Campo {
  id: number;
  nombre: string;
  descripcion: string;
  ubicacion: string;
  latitud: number | null;
  longitud: number | null;
  creado_en: string;
  actualizado_en: string;
}

export interface Modulo {
  id: number;
  campo: number;
  campo_nombre?: string;
  nombre: string;
  descripcion: string;
  creado_en: string;
}

export interface Vuelo {
  id: number;
  modulo: number;
  modulo_nombre?: string;
  campo?: number;
  campo_nombre?: string;
  nombre: string;
  fecha_vuelo: string;
  estado: "pendiente" | "procesando" | "completado" | "error";
  total_plantas: number;
  total_imagenes: number;
  imagenes_procesadas: number;
  porcentaje_procesado: number;
  creado_en: string;
  actualizado_en?: string;
}

export interface Imagen {
  id: number;
  vuelo: number;
  archivo: string;
  nombre_original: string;
  procesada: boolean;
  conteo_plantas: number;
  revisada: boolean;
  revisada_en: string | null;
  creado_en: string;
}

export type DeteccionOrigen = "modelo" | "manual" | "corregida";

export interface Deteccion {
  id: number;
  imagen: number;
  confianza: number;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
  clase: string;
  origen: DeteccionOrigen;
}

export interface EstadoVisor {
  imagenActivaIndex: number;
  minConfianza: number; // 0.0 – 1.0; slider en el cliente
  mostrarEtiquetas: boolean;
  descargando: boolean;
}

// --------------------------------------------------------------------------
// GIS / mapas (GeoJSON). OJO: GeoJSON usa [lon, lat]; Leaflet usa [lat, lon].
// --------------------------------------------------------------------------

export interface GeoPoint {
  type: "Point";
  coordinates: [number, number]; // [lon, lat]
}

export interface GeoFeature<P> {
  type: "Feature";
  id?: number;
  geometry: GeoPoint;
  properties: P;
}

export interface GeoFeatureCollection<P> {
  type: "FeatureCollection";
  features: Array<GeoFeature<P>>;
}

export interface CampoMapaProps {
  id: number;
  nombre: string;
  descripcion: string;
  ubicacion: string;
}

export interface VueloMapaProps {
  id: number;
  nombre: string;
  estado: Vuelo["estado"];
  total_plantas: number;
  fecha_vuelo: string;
  campo: number | null;
  campo_nombre: string | null;
}

export interface DeteccionMapaProps {
  id: number;
  confianza: number;
  clase: string;
  origen: DeteccionOrigen;
  imagen: number;
  bbox?: [number, number, number, number]; // [west, south, east, north]
}

export interface RasterOverlay {
  imagen_id: number;
  nombre: string;
  bounds: [[number, number], [number, number]]; // [[south, west], [north, east]]
  // Zoom XYZ que iguala la resolución nativa del GeoTIFF (maxNativeZoom de la
  // capa de tiles). null si no se pudo calcular.
  max_native_zoom?: number | null;
}

export interface RasterOverlayResponse {
  overlays: RasterOverlay[];
}

// --------------------------------------------------------------------------
// Fase 4: corrección manual + reentrenamiento activo
// --------------------------------------------------------------------------

export interface ConfigReentrenamiento {
  auto_reentrenar: boolean;
  umbral_correcciones: number;
  auto_activar_modelo: boolean;
  margen_map50: number;
  epochs: number;
  base_model: string;
  correcciones_acumuladas: number;
  ultimo_reentrenamiento: string | null;
  actualizado_en: string;
}

export type CicloEstado =
  | "pendiente"
  | "construyendo"
  | "entrenando"
  | "evaluando"
  | "completado"
  | "activado"
  | "error";

export interface CicloReentrenamiento {
  id: number;
  disparador: "auto" | "manual";
  estado: CicloEstado;
  num_correcciones: number;
  num_imagenes: number;
  num_anotaciones: number;
  dataset: number | null;
  modelo: number | null;
  modelo_nombre: string | null;
  modelo_version: string | null;
  map50_anterior: number | null;
  map50_nuevo: number | null;
  activado: boolean;
  mensaje: string;
  creado_en: string;
  completado_en: string | null;
}

export interface ModeloActivoResumen {
  id: number;
  nombre: string;
  version: string;
  map50: number | null;
}

export interface EstadoReentrenamiento {
  config: ConfigReentrenamiento;
  imagenes_revisadas: number;
  modelo_activo: ModeloActivoResumen | null;
  ultimo_ciclo: CicloReentrenamiento | null;
}

export interface MapaGeneralResponse {
  campos: GeoFeatureCollection<CampoMapaProps>;
  vuelos: GeoFeatureCollection<VueloMapaProps>;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface DatasetEntrenamiento {
  id: number;
  nombre: string;
  archivo: string;
  formato: "yolo" | "cvat_xml" | "coco";
  num_imagenes: number;
  clases: string[];
  estado: "subido" | "validando" | "valido" | "invalido";
  reporte_validacion: {
    total_imagenes?: number;
    total_anotaciones?: number;
    distribucion_por_clase?: Record<string, number>;
    warnings?: string[];
    error?: string;
  };
  creado_en: string;
}

export interface ModeloEntrenado {
  id: number;
  nombre: string;
  version: string;
  dataset: number;
  dataset_nombre?: string;
  base_model: "yolov8n.pt" | "yolov8s.pt" | "yolov8m.pt";
  epochs: number;
  img_size: number;
  patience: number;
  estado: "pendiente" | "preparando" | "entrenando" | "completado" | "error";
  epoca_actual: number;
  porcentaje: number;
  metricas: {
    map50?: number;
    map50_95?: number;
    precision?: number;
    recall?: number;
    fitness?: number;
  };
  archivo_pesos: string | null;
  activo: boolean;
  notas: string;
  error_mensaje: string;
  creado_en: string;
  completado_en: string | null;
}

export interface ModeloResults {
  metricas: ModeloEntrenado["metricas"];
  imagenes: Record<string, string>;
  porcentaje: number;
  epoca_actual: number;
  epochs: number;
}

export interface DashboardStats {
  total_campos: number;
  total_modulos: number;
  total_vuelos: number;
  total_plantas: number;
  vuelos_procesados_hoy: number;
  vuelos_procesando: number;
}

export interface MetadatosGeo {
  crs?: string;
  bounds?: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
  ancho_px?: number;
  alto_px?: number;
  bandas?: number;
  res_m_per_px?: number;
  tile_size?: number;
  overlap_px?: number;
  tiles?: Array<{
    nombre: string;
    fila: number;
    col: number;
    pixel_x: number;
    pixel_y: number;
    bbox_geo: { west: number; south: number; east: number; north: number };
  }>;
}

export interface SesionConversion {
  id: number;
  nombre: string;
  fuente: "upload" | "vuelo";
  archivo_tiff: string | null;
  imagen_vuelo: number | null;
  imagen_vuelo_nombre: string | null;
  tile_size: number;
  overlap_px: number;
  calidad_jpg: number;
  saltar_vacios: boolean;
  estado: "pendiente" | "procesando" | "completado" | "error";
  total_tiles: number;
  tiles_procesados: number;
  porcentaje: number;
  error_mensaje: string;
  metadatos_geo: MetadatosGeo;
  directorio_tiles: string;
  archivo_zip: string | null;
  notas: string;
  nombre_archivo_fuente: string;
  creado_en: string;
  completado_en: string | null;
}

export type SesionConversionCreate = {
  nombre: string;
  fuente: "upload" | "vuelo";
  archivo_tiff?: File;
  imagen_vuelo?: number;
  tile_size: number;
  overlap_px: number;
  calidad_jpg: number;
  saltar_vacios: boolean;
  notas?: string;
};
