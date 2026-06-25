"use client";

import PanelReentrenamiento from "@/components/reentrenamiento/PanelReentrenamiento";

export default function ReentrenamientoPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Reentrenamiento</h2>
        <p className="text-muted-foreground">
          Cada corrección manual alimenta el dataset. Al alcanzar el umbral (o
          con el botón) se reentrena el modelo y, si mejora el mAP50, se activa
          automáticamente.
        </p>
      </div>
      <PanelReentrenamiento />
    </div>
  );
}
