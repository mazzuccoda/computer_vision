import api from "./api";
import { Imagen, PaginatedResponse, Vuelo } from "@/types";

export type VueloInput = {
  modulo: number;
  nombre: string;
  fecha_vuelo: string;
};

export interface VueloResults {
  vuelo: Vuelo;
  imagenes: Imagen[];
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const vuelosService = {
  async list(moduloId?: number): Promise<PaginatedResponse<Vuelo>> {
    const { data } = await api.get<PaginatedResponse<Vuelo>>("/vuelos/", {
      params: moduloId ? { modulo_id: moduloId } : undefined,
    });
    return data;
  },

  async get(id: number): Promise<Vuelo> {
    const { data } = await api.get<Vuelo>(`/vuelos/${id}/`);
    return data;
  },

  async create(payload: VueloInput): Promise<Vuelo> {
    const { data } = await api.post<Vuelo>("/vuelos/", payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/vuelos/${id}/`);
  },

  async uploadImages(
    id: number,
    files: File[],
    onProgress?: (percent: number) => void,
  ): Promise<void> {
    const formData = new FormData();
    files.forEach((file) => formData.append("imagenes", file));

    await api.post(`/vuelos/${id}/upload-images/`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      },
    });
  },

  async process(id: number): Promise<void> {
    await api.post(`/vuelos/${id}/process/`);
  },

  async results(id: number): Promise<VueloResults> {
    const { data } = await api.get<VueloResults>(`/vuelos/${id}/results/`);
    return data;
  },

  async listImagenes(vueloId: number): Promise<PaginatedResponse<Imagen>> {
    const { data } = await api.get<PaginatedResponse<Imagen>>("/imagenes/", {
      params: { vuelo_id: vueloId },
    });
    return data;
  },

  exportCsvUrl(id: number): string {
    return `${API_BASE_URL}/api/vuelos/${id}/export-csv/`;
  },

  async downloadCsv(id: number): Promise<void> {
    const { data } = await api.get(`/vuelos/${id}/export-csv/`, {
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([data]));
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `vuelo_${id}_resultados.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};
