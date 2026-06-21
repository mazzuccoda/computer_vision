"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";

import { Button } from "@/components/ui/button";

const MapaDetecciones = dynamic(
  () => import("@/components/mapa/MapaDetecciones"),
  {
    ssr: false,
    loading: () => (
      <div className="h-[600px] animate-pulse rounded-lg bg-muted" />
    ),
  }
);

export default function VueloMapaPage() {
  const params = useParams<{ id: string }>();
  const vueloId = Number(params.id);

  return (
    <div className="space-y-4">
      <Button asChild variant="ghost" size="sm">
        <Link href={`/vuelos/${vueloId}`}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Volver al vuelo
        </Link>
      </Button>
      <div>
        <h2 className="text-2xl font-bold tracking-tight">
          Mapa de detecciones
        </h2>
        <p className="text-muted-foreground">
          Plantas detectadas distribuidas geográficamente, agrupadas por
          cercanía. Ajustá el umbral de confianza para filtrar.
        </p>
      </div>
      <MapaDetecciones vueloId={vueloId} />
    </div>
  );
}
