"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { ModeloInput, modelosService } from "@/services/modelos.service";
import { ModeloEntrenado } from "@/types";

const EN_PROGRESO: ModeloEntrenado["estado"][] = [
  "pendiente",
  "preparando",
  "entrenando",
];

export function useModelos() {
  return useQuery({
    queryKey: ["modelos"],
    queryFn: () => modelosService.list(),
    // Polling mientras algún modelo esté preparándose o entrenando.
    refetchInterval: (query) =>
      query.state.data?.results.some((m) => EN_PROGRESO.includes(m.estado))
        ? 5000
        : false,
  });
}

export function useModelo(id: number) {
  return useQuery({
    queryKey: ["modelo", id],
    queryFn: () => modelosService.get(id),
    enabled: Number.isFinite(id),
    refetchInterval: (query) =>
      query.state.data && EN_PROGRESO.includes(query.state.data.estado)
        ? 3000
        : false,
  });
}

export function useCreateModelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ModeloInput) => modelosService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modelos"] }),
  });
}

export function useActivateModelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => modelosService.activate(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["modelos"] });
      qc.invalidateQueries({ queryKey: ["modelo", id] });
    },
  });
}

export function useDeleteModelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => modelosService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modelos"] }),
  });
}
