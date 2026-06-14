"use client";

import { Plus } from "lucide-react";
import Link from "next/link";

import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EstadoModeloBadge } from "@/components/modelos/EstadoModeloBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useModelos } from "@/hooks/useModelos";

function fmtMetric(value?: number): string {
  if (value === undefined || value === null) return "—";
  return value.toFixed(3);
}

export default function ModelosPage() {
  const { data, isLoading } = useModelos();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Modelos</h2>
          <p className="text-muted-foreground">
            Entrená modelos YOLO desde datasets anotados y activá el que usa la
            inferencia.
          </p>
        </div>
        <Button asChild>
          <Link href="/modelos/nuevo">
            <Plus className="mr-2 h-4 w-4" />
            Nuevo entrenamiento
          </Link>
        </Button>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : data && data.results.length > 0 ? (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nombre</TableHead>
                <TableHead>Versión</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">mAP50</TableHead>
                <TableHead className="text-center">Activo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((m) => (
                <TableRow key={m.id} className="cursor-pointer">
                  <TableCell className="font-medium">
                    <Link href={`/modelos/${m.id}`} className="hover:underline">
                      {m.nombre}
                    </Link>
                  </TableCell>
                  <TableCell>{m.version}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {m.dataset_nombre ?? `#${m.dataset}`}
                  </TableCell>
                  <TableCell>
                    {m.estado === "entrenando" || m.estado === "preparando" ? (
                      <div className="flex items-center gap-2">
                        <EstadoModeloBadge estado={m.estado} />
                        <span className="text-xs text-muted-foreground">
                          {m.porcentaje}%
                        </span>
                      </div>
                    ) : (
                      <EstadoModeloBadge estado={m.estado} />
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {fmtMetric(m.metricas?.map50)}
                  </TableCell>
                  <TableCell className="text-center">
                    {m.activo && (
                      <Badge className="border-0 bg-green-600 text-white hover:bg-green-600">
                        ACTIVO
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-muted-foreground">
          No hay modelos todavía. Creá el primer entrenamiento.
        </p>
      )}
    </div>
  );
}
