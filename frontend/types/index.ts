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
  creado_en: string;
}

export interface Deteccion {
  id: number;
  imagen: number;
  confianza: number;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
  clase: string;
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

export interface DashboardStats {
  total_campos: number;
  total_modulos: number;
  total_vuelos: number;
  total_plantas: number;
  vuelos_procesados_hoy: number;
  vuelos_procesando: number;
}
