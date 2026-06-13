import api from "./api";
import { Campo, PaginatedResponse } from "@/types";

export type CampoInput = {
  nombre: string;
  descripcion?: string;
  ubicacion?: string;
  latitud?: number | null;
  longitud?: number | null;
};

export const camposService = {
  async list(): Promise<PaginatedResponse<Campo>> {
    const { data } = await api.get<PaginatedResponse<Campo>>("/campos/");
    return data;
  },

  async get(id: number): Promise<Campo> {
    const { data } = await api.get<Campo>(`/campos/${id}/`);
    return data;
  },

  async create(payload: CampoInput): Promise<Campo> {
    const { data } = await api.post<Campo>("/campos/", payload);
    return data;
  },

  async update(id: number, payload: CampoInput): Promise<Campo> {
    const { data } = await api.put<Campo>(`/campos/${id}/`, payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/campos/${id}/`);
  },
};
