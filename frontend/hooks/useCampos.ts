"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { CampoInput, camposService } from "@/services/campos.service";

export function useCampos() {
  return useQuery({
    queryKey: ["campos"],
    queryFn: () => camposService.list(),
  });
}

export function useCampo(id: number) {
  return useQuery({
    queryKey: ["campo", id],
    queryFn: () => camposService.get(id),
    enabled: Number.isFinite(id),
  });
}

export function useCreateCampo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CampoInput) => camposService.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campos"] }),
  });
}

export function useUpdateCampo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: CampoInput }) =>
      camposService.update(id, payload),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["campos"] });
      qc.invalidateQueries({ queryKey: ["campo", id] });
    },
  });
}

export function useDeleteCampo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => camposService.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campos"] }),
  });
}
