"use client";

import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { VueloCard } from "@/components/vuelos/VueloCard";
import { VueloForm } from "@/components/vuelos/VueloForm";
import { useVuelos } from "@/hooks/useVuelos";

export default function VuelosPage() {
  const { data, isLoading } = useVuelos();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Vuelos</h2>
          <p className="text-muted-foreground">
            Gestioná los vuelos y su procesamiento.
          </p>
        </div>
        <VueloForm />
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : data && data.results.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.results.map((vuelo) => (
            <VueloCard key={vuelo.id} vuelo={vuelo} />
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">
          No hay vuelos todavía. Creá el primero.
        </p>
      )}
    </div>
  );
}
