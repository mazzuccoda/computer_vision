"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { converterService } from "@/services/converter.service";
import { SesionConversion, SesionConversionCreate } from "@/types";

const EN_PROGRESO: SesionConversion["estado"][] = [
  "pendiente",
  "procesando",
];

export function useSesiones() {
  return useQuery({
    queryKey: ["sesiones-conversion"],
    queryFn: () => converterService.list(),
    refetchInterval: (query) =>
      query.state.data?.results.some((s) => EN_PROGRESO.includes(s.estado))
        ? 3000
        : false,
  });
}

export function useSesion(id: number) {
  return useQuery({
    queryKey: ["sesion-conversion", id],
    queryFn: () => converterService.get(id),
    enabled: Number.isFinite(id),
    refetchInterval: (query) =>
      query.state.data && EN_PROGRESO.includes(query.state.data.estado)
        ? 3000
        : false,
  });
}

export function useImagenesTiff() {
  return useQuery({
    queryKey: ["imagenes-tiff"],
    queryFn: () => converterService.listImagenesTiff(),
  });
}

export function useCreateSesion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      payload,
      onProgress,
    }: {
      payload: SesionConversionCreate;
      onProgress?: (percent: number) => void;
    }) => converterService.create(payload, onProgress),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["sesiones-conversion"] }),
  });
}

export function useDeleteSesion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => converterService.remove(id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["sesiones-conversion"] }),
  });
}
