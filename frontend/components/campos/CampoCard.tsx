"use client";

import { MapPin, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { CampoForm } from "@/components/campos/CampoForm";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDeleteCampo } from "@/hooks/useCampos";
import { Campo } from "@/types";

export function CampoCard({ campo }: { campo: Campo }) {
  const deleteCampo = useDeleteCampo();

  async function handleDelete() {
    if (!confirm(`¿Eliminar el campo "${campo.nombre}"?`)) return;
    try {
      await deleteCampo.mutateAsync(campo.id);
      toast.success("Campo eliminado");
    } catch {
      toast.error("No se pudo eliminar el campo");
    }
  }

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-primary" />
          {campo.nombre}
        </CardTitle>
        <CardDescription>
          {campo.ubicacion || "Sin ubicación"}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 text-sm text-muted-foreground">
        {campo.descripcion || "Sin descripción."}
      </CardContent>
      <CardFooter className="flex items-center justify-between gap-2">
        <Button asChild variant="secondary" size="sm">
          <Link href={`/campos/${campo.id}`}>Ver detalle</Link>
        </Button>
        <div className="flex gap-2">
          <CampoForm
            campo={campo}
            trigger={
              <Button variant="outline" size="icon">
                <Pencil className="h-4 w-4" />
              </Button>
            }
          />
          <Button
            variant="outline"
            size="icon"
            onClick={handleDelete}
            disabled={deleteCampo.isPending}
          >
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
}
