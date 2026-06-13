import api from "./api";
import { Modulo, PaginatedResponse } from "@/types";

export type ModuloInput = {
  campo: number;
  nombre: string;
  descripcion?: string;
};

export const modulosService = {
  async list(campoId?: number): Promise<PaginatedResponse<Modulo>> {
    const { data } = await api.get<PaginatedResponse<Modulo>>("/modulos/", {
      params: campoId ? { campo_id: campoId } : undefined,
    });
    return data;
  },

  async get(id: number): Promise<Modulo> {
    const { data } = await api.get<Modulo>(`/modulos/${id}/`);
    return data;
  },

  async create(payload: ModuloInput): Promise<Modulo> {
    const { data } = await api.post<Modulo>("/modulos/", payload);
    return data;
  },

  async update(id: number, payload: ModuloInput): Promise<Modulo> {
    const { data } = await api.put<Modulo>(`/modulos/${id}/`, payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/modulos/${id}/`);
  },
};
