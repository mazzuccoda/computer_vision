import api from "./api";
import type { Deteccion, Imagen } from "@/types";

export interface BBox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export const deteccionesService = {
  async listByImagen(imagenId: number): Promise<Deteccion[]> {
    const { data } = await api.get(`/detecciones/?imagen_id=${imagenId}`);
    return data.results ?? data;
  },

  async create(imagenId: number, box: BBox): Promise<Deteccion> {
    const { data } = await api.post<Deteccion>("/detecciones/", {
      imagen: imagenId,
      ...box,
    });
    return data;
  },

  async update(id: number, box: BBox): Promise<Deteccion> {
    const { data } = await api.put<Deteccion>(`/detecciones/${id}/`, box);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/detecciones/${id}/`);
  },

  async marcarRevisada(
    imagenId: number,
    revisada = true,
  ): Promise<Imagen> {
    const { data } = await api.post<Imagen>(
      `/imagenes/${imagenId}/marcar-revisada/`,
      { revisada },
    );
    return data;
  },
};
