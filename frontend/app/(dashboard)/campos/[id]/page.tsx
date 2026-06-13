"use client";

import { ArrowLeft, Layers } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useCampo } from "@/hooks/useCampos";
import { useModulos } from "@/hooks/useModulos";

export default function CampoDetallePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const { data: campo, isLoading } = useCampo(id);
  const { data: modulos } = useModulos(id);

  if (isLoading) return <LoadingSpinner />;
  if (!campo) return <p className="text-muted-foreground">Campo no encontrado.</p>;

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/campos">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Volver a campos
        </Link>
      </Button>

      <div>
        <h2 className="text-2xl font-bold tracking-tight">{campo.nombre}</h2>
        <p className="text-muted-foreground">
          {campo.ubicacion || "Sin ubicación"}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Información</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Descripción: </span>
            {campo.descripcion || "—"}
          </p>
          <p>
            <span className="text-muted-foreground">Coordenadas: </span>
            {campo.latitud != null && campo.longitud != null
              ? `${campo.latitud}, ${campo.longitud}`
              : "—"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers className="h-4 w-4 text-primary" />
            Módulos del campo
          </CardTitle>
        </CardHeader>
        <CardContent>
          {modulos && modulos.results.length > 0 ? (
            <ul className="space-y-2">
              {modulos.results.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between rounded-md border p-3 text-sm"
                >
                  <span className="font-medium">{m.nombre}</span>
                  <span className="text-muted-foreground">
                    {m.descripcion || "—"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              Este campo no tiene módulos.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
