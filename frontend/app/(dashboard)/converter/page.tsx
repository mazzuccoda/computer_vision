"use client";

import { Plus } from "lucide-react";
import Link from "next/link";

import { EstadoConversionBadge } from "@/components/converter/EstadoConversionBadge";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSesiones } from "@/hooks/useConverter";

export default function ConverterPage() {
  const { data, isLoading } = useSesiones();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">
            Convertir GeoTIFF
          </h2>
          <p className="text-muted-foreground">
            Fragmentá ortomosaicos GeoTIFF en tiles JPG listos para anotar en
            CVAT.
          </p>
        </div>
        <Button asChild>
          <Link href="/converter/nuevo">
            <Plus className="mr-2 h-4 w-4" />
            Nueva conversión
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
                <TableHead>Fuente</TableHead>
                <TableHead>Archivo TIFF</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Tiles</TableHead>
                <TableHead className="text-center">Tamaño tile</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((s) => (
                <TableRow key={s.id} className="cursor-pointer">
                  <TableCell className="font-medium">
                    <Link
                      href={`/converter/${s.id}`}
                      className="hover:underline"
                    >
                      {s.nombre}
                    </Link>
                  </TableCell>
                  <TableCell className="capitalize text-muted-foreground">
                    {s.fuente}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {s.nombre_archivo_fuente}
                  </TableCell>
                  <TableCell>
                    {s.estado === "procesando" ? (
                      <div className="flex items-center gap-2">
                        <EstadoConversionBadge estado={s.estado} />
                        <span className="text-xs text-muted-foreground">
                          {s.porcentaje}%
                        </span>
                      </div>
                    ) : (
                      <EstadoConversionBadge estado={s.estado} />
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {s.estado === "completado"
                      ? s.tiles_procesados
                      : `${s.tiles_procesados}/${s.total_tiles}`}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground">
                    {s.tile_size}px
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-muted-foreground">
          No hay conversiones todavía. Creá la primera.
        </p>
      )}
    </div>
  );
}
