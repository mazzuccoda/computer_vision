"use client";

import { EstadoBadge } from "@/components/vuelos/EstadoBadge";
import { Progress } from "@/components/ui/progress";
import { Vuelo } from "@/types";

export function ProcessingStatus({ vuelo }: { vuelo: Vuelo }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2">
          Estado: <EstadoBadge estado={vuelo.estado} />
        </span>
        <span className="text-muted-foreground">
          {vuelo.imagenes_procesadas} / {vuelo.total_imagenes} imágenes ·{" "}
          {vuelo.porcentaje_procesado}%
        </span>
      </div>
      <Progress value={vuelo.porcentaje_procesado} />
    </div>
  );
}
