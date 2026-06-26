import api from "./api";
import {
  Imagen,
  PaginatedResponse,
  SesionConversion,
  SesionConversionCreate,
} from "@/types";

export const converterService = {
  async list(): Promise<PaginatedResponse<SesionConversion>> {
    const { data } =
      await api.get<PaginatedResponse<SesionConversion>>(
        "/converter/sesiones/",
      );
    return data;
  },

  async get(id: number): Promise<SesionConversion> {
    const { data } = await api.get<SesionConversion>(
      `/converter/sesiones/${id}/`,
    );
    return data;
  },

  async create(
    payload: SesionConversionCreate,
    onProgress?: (percent: number) => void,
  ): Promise<SesionConversion> {
    const formData = new FormData();
    formData.append("nombre", payload.nombre);
    formData.append("fuente", payload.fuente);
    if (payload.archivo_tiff) {
      formData.append("archivo_tiff", payload.archivo_tiff);
    }
    if (payload.imagen_vuelo !== undefined) {
      formData.append("imagen_vuelo", String(payload.imagen_vuelo));
    }
    formData.append("tile_size", String(payload.tile_size));
    formData.append("overlap_px", String(payload.overlap_px));
    formData.append("calidad_jpg", String(payload.calidad_jpg));
    formData.append("saltar_vacios", String(payload.saltar_vacios));
    if (payload.notas) formData.append("notas", payload.notas);

    const { data } = await api.post<SesionConversion>(
      "/converter/sesiones/",
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (event) => {
          if (onProgress && event.total) {
            onProgress(Math.round((event.loaded / event.total) * 100));
          }
        },
      },
    );
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/converter/sesiones/${id}/`);
  },

  async download(id: number, nombre: string): Promise<void> {
    const { data } = await api.get(`/converter/sesiones/${id}/download/`, {
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([data]));
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `tiles_${nombre}.zip`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },

  // Imágenes TIFF de vuelos existentes (fuente "vuelo").
  // El backend filtra por extensión con ?solo_tiff=true; recorremos todas
  // las páginas porque los TIFF pueden estar repartidos entre muchas imágenes.
  async listImagenesTiff(): Promise<Imagen[]> {
    const imagenes: Imagen[] = [];
    let page = 1;
    for (;;) {
      const { data } = await api.get<PaginatedResponse<Imagen>>(
        "/imagenes/",
        { params: { solo_tiff: true, page } },
      );
      imagenes.push(...data.results);
      if (!data.next) break;
      page += 1;
    }
    return imagenes.filter((img) =>
      /\.tiff?$/i.test(img.nombre_original),
    );
  },
};
