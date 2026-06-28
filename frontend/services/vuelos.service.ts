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
    const chunkMb = Number(process.env.NEXT_PUBLIC_UPLOAD_CHUNK_MB || "20");
    const chunkSize = Math.max(1, chunkMb) * 1024 * 1024;
    const totalBytes = files.reduce((sum, f) => sum + f.size, 0) || 1;
    let uploadedBytes = 0;

    const report = (base: number, loaded: number) => {
      if (onProgress) {
        onProgress(Math.min(100, Math.round(((base + loaded) / totalBytes) * 100)));
      }
    };

    for (const file of files) {
      if (file.size <= chunkSize) {
        const formData = new FormData();
        formData.append("imagenes", file);
        const base = uploadedBytes;
        await api.post(`/vuelos/${id}/upload-images/`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (event) => report(base, event.loaded),
        });
        uploadedBytes += file.size;
      } else {
        const uploadId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const totalChunks = Math.ceil(file.size / chunkSize);
        for (let index = 0; index < totalChunks; index++) {
          const start = index * chunkSize;
          const blob = file.slice(start, start + chunkSize);
          const fd = new FormData();
          fd.append("chunk", blob, file.name);
          fd.append("upload_id", uploadId);
          fd.append("filename", file.name);
          fd.append("chunk_index", String(index));
          fd.append("total_chunks", String(totalChunks));
          const base = uploadedBytes;
          await api.post(`/vuelos/${id}/upload-images-chunk/`, fd, {
            headers: { "Content-Type": "multipart/form-data" },
            onUploadProgress: (event) => report(base, event.loaded),
          });
          uploadedBytes += blob.size;
        }
      }
    }

    if (onProgress) onProgress(100);
  },

  async process(id: number, reprocesar = false): Promise<void> {
    await api.post(`/vuelos/${id}/process/`, reprocesar ? { reprocesar: true } : {});
  },

  async cancel(id: number): Promise<Vuelo> {
    const { data } = await api.post<Vuelo>(`/vuelos/${id}/cancel/`);
    return data;
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
