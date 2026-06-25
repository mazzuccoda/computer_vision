"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  ConfigInput,
  reentrenamientoService,
} from "@/services/reentrenamiento.service";
import type { CicloEstado } from "@/types";

const EN_PROGRESO: CicloEstado[] = [
  "pendiente",
  "construyendo",
  "entrenando",
  "evaluando",
];

export function useEstadoReentrenamiento() {
  return useQuery({
    queryKey: ["reentrenamiento", "estado"],
    queryFn: () => reentrenamientoService.estado(),
    // Polling en vivo mientras un ciclo está en curso.
    refetchInterval: (query) =>
      query.state.data?.ultimo_ciclo &&
      EN_PROGRESO.includes(query.state.data.ultimo_ciclo.estado)
        ? 3000
        : false,
  });
}

export function useCiclosReentrenamiento() {
  return useQuery({
    queryKey: ["reentrenamiento", "ciclos"],
    queryFn: () => reentrenamientoService.ciclos(),
    refetchInterval: (query) =>
      query.state.data?.some((c) => EN_PROGRESO.includes(c.estado))
        ? 3000
        : false,
  });
}

export function useUpdateConfigReentrenamiento() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConfigInput) =>
      reentrenamientoService.updateConfig(payload),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["reentrenamiento"] }),
  });
}

export function useDispararReentrenamiento() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => reentrenamientoService.disparar(),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["reentrenamiento"] }),
  });
}

export function useActivarCiclo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cicloId: number) => reentrenamientoService.activar(cicloId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["reentrenamiento"] }),
  });
}
