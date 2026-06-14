import api from "./api";
import {
  ModeloEntrenado,
  ModeloResults,
  PaginatedResponse,
} from "@/types";

export type ModeloInput = {
  nombre: string;
  dataset: number;
  base_model: ModeloEntrenado["base_model"];
  epochs: number;
  img_size: number;
  patience: number;
  notas?: string;
};

export const modelosService = {
  async list(): Promise<PaginatedResponse<ModeloEntrenado>> {
    const { data } =
      await api.get<PaginatedResponse<ModeloEntrenado>>("/modelos/");
    return data;
  },

  async get(id: number): Promise<ModeloEntrenado> {
    const { data } = await api.get<ModeloEntrenado>(`/modelos/${id}/`);
    return data;
  },

  async create(payload: ModeloInput): Promise<ModeloEntrenado> {
    const { data } = await api.post<ModeloEntrenado>("/modelos/", payload);
    return data;
  },

  async results(id: number): Promise<ModeloResults> {
    const { data } = await api.get<ModeloResults>(`/modelos/${id}/results/`);
    return data;
  },

  async activate(id: number): Promise<void> {
    await api.post(`/modelos/${id}/activate/`);
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/modelos/${id}/`);
  },

  async download(id: number, nombre: string, version: string): Promise<void> {
    const { data } = await api.get(`/modelos/${id}/download/`, {
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([data]));
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `modelo_${version}_${nombre}.zip`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};
