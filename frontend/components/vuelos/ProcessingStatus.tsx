"use client";

import { EstadoBadge } from "@/components/vuelos/EstadoBadge";
import { Progress } from "@/components/ui/progress";
import { Vuelo } from "@/types";

export function ProcessingStatus({ vuelo }: { vuelo: Vuelo }) {
  const tilesTotal = vuelo.tiles_total ?? 0;
  const tilesHechos = vuelo.tiles_procesados ?? 0;
  const mostrarTiles =
    vuelo.estado === "procesando" && tilesTotal > 0;
  const pctTiles = tilesTotal > 0
    ? Math.round((tilesHechos / tilesTotal) * 100)
    : 0;

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

      {mostrarTiles && (
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              Procesando imagen grande por tiles
            </span>
            <span className="text-muted-foreground">
              {tilesHechos.toLocaleString()} / {tilesTotal.toLocaleString()}{" "}
              tiles · {pctTiles}%
            </span>
          </div>
          <Progress value={pctTiles} />
        </div>
      )}
    </div>
  );
}
