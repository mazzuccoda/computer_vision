"use client";

import { Calendar, Leaf, Trash2 } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { EstadoBadge } from "@/components/vuelos/EstadoBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDeleteVuelo } from "@/hooks/useVuelos";
import { Vuelo } from "@/types";

export function VueloCard({ vuelo }: { vuelo: Vuelo }) {
  const deleteVuelo = useDeleteVuelo();

  async function handleDelete() {
    if (!confirm(`¿Eliminar el vuelo "${vuelo.nombre}"?`)) return;
    try {
      await deleteVuelo.mutateAsync(vuelo.id);
      toast.success("Vuelo eliminado");
    } catch {
      toast.error("No se pudo eliminar el vuelo");
    }
  }

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between">
          <CardTitle>{vuelo.nombre}</CardTitle>
          <EstadoBadge estado={vuelo.estado} />
        </div>
        <p className="text-sm text-muted-foreground">{vuelo.modulo_nombre}</p>
      </CardHeader>
      <CardContent className="flex-1 space-y-2 text-sm text-muted-foreground">
        <p className="flex items-center gap-2">
          <Calendar className="h-4 w-4" />
          {vuelo.fecha_vuelo}
        </p>
        <p className="flex items-center gap-2">
          <Leaf className="h-4 w-4 text-primary" />
          {vuelo.total_plantas} plantas · {vuelo.total_imagenes} imágenes
        </p>
      </CardContent>
      <CardFooter className="flex items-center justify-between gap-2">
        <Button asChild variant="secondary" size="sm">
          <Link href={`/vuelos/${vuelo.id}`}>Ver detalle</Link>
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={handleDelete}
          disabled={deleteVuelo.isPending}
        >
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </CardFooter>
    </Card>
  );
}
