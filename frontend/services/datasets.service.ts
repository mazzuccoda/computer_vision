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
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/datasets/${id}/`);
  },
};
