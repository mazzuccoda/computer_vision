"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { ModuloInput, modulosService } from "@/services/modulos.service";

export function useModulos(campoId?: number) {
  return useQuery({
    queryKey: ["modulos", campoId ?? "all"],
    queryFn: () => modulosService.list(campoId),
  });
}

export function useCreateModulo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ModuloInput) => modulosService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modulos"] }),
  });
}

export function useDeleteModulo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => modulosService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modulos"] }),
  });
}
