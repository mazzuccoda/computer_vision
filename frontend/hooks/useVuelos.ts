"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { VueloInput, vuelosService } from "@/services/vuelos.service";

export function useVuelos(moduloId?: number) {
  return useQuery({
    queryKey: ["vuelos", moduloId ?? "all"],
    queryFn: () => vuelosService.list(moduloId),
  });
}

export function useVuelo(id: number) {
  return useQuery({
    queryKey: ["vuelo", id],
    queryFn: () => vuelosService.get(id),
    enabled: Number.isFinite(id),
    // Polling: refrescar cada 3s mientras el vuelo está procesando.
    refetchInterval: (query) =>
      query.state.data?.estado === "procesando" ? 3000 : false,
  });
}

export function useVueloImagenes(vueloId: number, estado?: string) {
  return useQuery({
    queryKey: ["vuelo-imagenes", vueloId],
    queryFn: () => vuelosService.listImagenes(vueloId),
    enabled: Number.isFinite(vueloId),
    refetchInterval: estado === "procesando" ? 3000 : false,
  });
}

export function useCreateVuelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VueloInput) => vuelosService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vuelos"] }),
  });
}

export function useDeleteVuelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => vuelosService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vuelos"] }),
  });
}

export function useProcessVuelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => vuelosService.process(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["vuelo", id] });
    },
  });
}

export function useUploadImages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      files,
      onProgress,
    }: {
      id: number;
      files: File[];
      onProgress?: (p: number) => void;
    }) => vuelosService.uploadImages(id, files, onProgress),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["vuelo", id] });
      qc.invalidateQueries({ queryKey: ["vuelo-imagenes", id] });
    },
  });
}
