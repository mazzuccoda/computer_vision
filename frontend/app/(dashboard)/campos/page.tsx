"use client";

import { CampoCard } from "@/components/campos/CampoCard";
import { CampoForm } from "@/components/campos/CampoForm";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { useCampos } from "@/hooks/useCampos";

export default function CamposPage() {
  const { data, isLoading } = useCampos();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Campos</h2>
          <p className="text-muted-foreground">
            Gestioná los campos agrícolas.
          </p>
        </div>
        <CampoForm />
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : data && data.results.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.results.map((campo) => (
            <CampoCard key={campo.id} campo={campo} />
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">
          No hay campos todavía. Creá el primero.
        </p>
      )}
    </div>
  );
}
