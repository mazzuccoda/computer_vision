import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ModeloEntrenado } from "@/types";

const ESTADO_STYLES: Record<ModeloEntrenado["estado"], string> = {
  pendiente: "bg-gray-200 text-gray-800 hover:bg-gray-200",
  preparando: "bg-blue-100 text-blue-700 hover:bg-blue-100 animate-pulse",
  entrenando: "bg-amber-100 text-amber-700 hover:bg-amber-100 animate-pulse",
  completado: "bg-green-100 text-green-700 hover:bg-green-100",
  error: "bg-red-100 text-red-700 hover:bg-red-100",
};

const ESTADO_LABELS: Record<ModeloEntrenado["estado"], string> = {
  pendiente: "Pendiente",
  preparando: "Preparando",
  entrenando: "Entrenando",
  completado: "Completado",
  error: "Error",
};

export function EstadoModeloBadge({
  estado,
}: {
  estado: ModeloEntrenado["estado"];
}) {
  return (
    <Badge className={cn("border-0", ESTADO_STYLES[estado])}>
      {ESTADO_LABELS[estado]}
    </Badge>
  );
}
