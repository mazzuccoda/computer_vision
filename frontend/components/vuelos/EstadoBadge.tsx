import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Vuelo } from "@/types";

const ESTADO_STYLES: Record<Vuelo["estado"], string> = {
  pendiente: "bg-gray-200 text-gray-800 hover:bg-gray-200",
  procesando: "bg-blue-100 text-blue-700 hover:bg-blue-100",
  completado: "bg-green-100 text-green-700 hover:bg-green-100",
  error: "bg-red-100 text-red-700 hover:bg-red-100",
};

const ESTADO_LABELS: Record<Vuelo["estado"], string> = {
  pendiente: "Pendiente",
  procesando: "Procesando",
  completado: "Completado",
  error: "Error",
};

export function EstadoBadge({ estado }: { estado: Vuelo["estado"] }) {
  return (
    <Badge className={cn("border-0", ESTADO_STYLES[estado])}>
      {ESTADO_LABELS[estado]}
    </Badge>
  );
}
