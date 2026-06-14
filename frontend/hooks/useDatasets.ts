"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { datasetsService } from "@/services/datasets.service";
import { DatasetEntrenamiento } from "@/types";

export function useDatasets() {
  return useQuery({
    queryKey: ["datasets"],
    queryFn: () => datasetsService.list(),
  });
}

export function useUploadDataset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      nombre,
      formato,
      archivo,
      onProgress,
    }: {
      nombre: string;
      formato: DatasetEntrenamiento["formato"];
      archivo: File;
      onProgress?: (p: number) => void;
    }) => datasetsService.upload(nombre, formato, archivo, onProgress),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });
}

export function useDeleteDataset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => datasetsService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });
}
