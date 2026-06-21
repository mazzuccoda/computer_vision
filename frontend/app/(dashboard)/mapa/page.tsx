"use client";

import dynamic from "next/dynamic";

const MapaGeneral = dynamic(() => import("@/components/mapa/MapaGeneral"), {
  ssr: false,
  loading: () => (
    <div className="h-[600px] animate-pulse rounded-lg bg-muted" />
  ),
});

export default function MapaPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">
          Mapa de campos y vuelos
        </h2>
        <p className="text-muted-foreground">
          Campos y vuelos georreferenciados. Hacé clic en un vuelo para ver
          sus detecciones en el mapa.
        </p>
      </div>
      <MapaGeneral />
    </div>
  );
}
