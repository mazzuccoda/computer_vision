import api from "./api";
import { DatasetEntrenamiento, PaginatedResponse } from "@/types";

export const datasetsService = {
  async list(): Promise<PaginatedResponse<DatasetEntrenamiento>> {
    const { data } =
      await api.get<PaginatedResponse<DatasetEntrenamiento>>("/datasets/");
    return data;
  },

  async get(id: number): Promise<DatasetEntrenamiento> {
    const { data } = await api.get<DatasetEntrenamiento>(`/datasets/${id}/`);
    return data;
  },

  async upload(
    nombre: string,
    formato: DatasetEntrenamiento["formato"],
    archivo: File,
    onProgress?: (percent: number) => void,
  ): Promise<DatasetEntrenamiento> {
    const chunkMb = Number(process.env.NEXT_PUBLIC_UPLOAD_CHUNK_MB || "20");
    const chunkSize = Math.max(1, chunkMb) * 1024 * 1024;

    let creado: DatasetEntrenamiento;
    if (archivo.size <= chunkSize) {
      const formData = new FormData();
      formData.append("nombre", nombre);
      formData.append("formato", formato);
      formData.append("archivo", archivo);
      const { data } = await api.post<DatasetEntrenamiento>(
        "/datasets/",
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
      creado = data;
    } else {
      // Subida por fragmentos: cada chunk < límite de Cloudflare (100 MB).
      const uploadId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const totalChunks = Math.ceil(archivo.size / chunkSize);
      let uploadedBytes = 0;
      let ultimo: DatasetEntrenamiento | null = null;
      for (let index = 0; index < totalChunks; index++) {
        const start = index * chunkSize;
        const blob = archivo.slice(start, start + chunkSize);
        const fd = new FormData();
        fd.append("chunk", blob, archivo.name);
        fd.append("upload_id", uploadId);
        fd.append("filename", archivo.name);
        fd.append("chunk_index", String(index));
        fd.append("total_chunks", String(totalChunks));
        fd.append("nombre", nombre);
        fd.append("formato", formato);
        const base = uploadedBytes;
        const { data } = await api.post<
          Partial<DatasetEntrenamiento> & { detail?: string }
        >("/datasets/upload-chunk/", fd, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (event) => {
            if (onProgress) {
              onProgress(
                Math.min(
                  100,
                  Math.round(((base + event.loaded) / archivo.size) * 100),
                ),
              );
            }
          },
        });
        uploadedBytes += blob.size;
        if (typeof data?.id === "number") {
          ultimo = data as DatasetEntrenamiento;
        }
      }
      if (!ultimo) {
        throw new Error("No se recibió el dataset al terminar la subida.");
      }
      creado = ultimo;
    }

    if (onProgress) onProgress(100);
    // La validación corre en Celery; esperamos a que termine.
    return this.esperarValidacion(creado.id);
  },

  async esperarValidacion(
    id: number,
    intervaloMs = 2000,
    timeoutMs = 600000,
  ): Promise<DatasetEntrenamiento> {
    const inicio = Date.now();
    for (;;) {
      const ds = await this.get(id);
      if (ds.estado !== "validando" && ds.estado !== "subido") return ds;
      if (Date.now() - inicio > timeoutMs) return ds;
      await new Promise((r) => setTimeout(r, intervaloMs));
    }
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/datasets/${id}/`);
  },
};
