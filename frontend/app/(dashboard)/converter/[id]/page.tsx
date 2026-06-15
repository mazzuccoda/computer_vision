"use client";

import { AlertTriangle, ArrowLeft, Download } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import { EstadoConversionBadge } from "@/components/converter/EstadoConversionBadge";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useSesion } from "@/hooks/useConverter";
import { converterService } from "@/services/converter.service";

function fmtCoord(value?: number): string {
  if (value === undefined || value === null) return "—";
  return value.toFixed(5);
}

export default function ConversionDetallePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const { data: sesion, isLoading } = useSesion(id);

  if (isLoading) return <LoadingSpinner />;
  if (!sesion)
    return <p className="text-muted-foreground">Sesión no encontrada.</p>;

  async function handleDownload() {
    try {
      await converterService.download(id, sesion!.nombre);
    } catch {
      toast.error("No se pudo descargar el .zip");
    }
  }

  const geo = sesion.metadatos_geo ?? {};
  const omitidos = Math.max(0, sesion.total_tiles - sesion.tiles_procesados);

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/converter">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Volver a conversiones
        </Link>
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight">
              {sesion.nombre}
            </h2>
            <EstadoConversionBadge estado={sesion.estado} />
          </div>
          <p className="text-muted-foreground">
            <Badge variant="outline" className="mr-2 capitalize">
              {sesion.fuente === "vuelo"
                ? `Vuelo: ${sesion.imagen_vuelo_nombre ?? ""}`
                : "Upload"}
            </Badge>
            {sesion.nombre_archivo_fuente} · {sesion.tile_size}×
            {sesion.tile_size} px · overlap: {sesion.overlap_px} px · calidad:{" "}
            {sesion.calidad_jpg}%
          </p>
        </div>
        {sesion.estado === "completado" && (
          <Button onClick={handleDownload}>
            <Download className="mr-2 h-4 w-4" />
            Descargar tiles .zip
          </Button>
        )}
      </div>

      {/* Info del GeoTIFF */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Información del GeoTIFF</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-muted-foreground">Dimensiones</p>
            <p className="font-medium">
              {geo.ancho_px ?? "—"} × {geo.alto_px ?? "—"} px
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Bandas</p>
            <p className="font-medium">{geo.bandas ?? "—"}</p>
          </div>
          <div>
            <p className="text-muted-foreground">CRS</p>
            <p className="font-medium">{geo.crs ?? "—"}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Resolución</p>
            <p className="font-medium">
              {geo.res_m_per_px ? `${geo.res_m_per_px} m/px` : "—"}
            </p>
          </div>
          {geo.bounds && (
            <div className="sm:col-span-2 lg:col-span-4">
              <p className="text-muted-foreground">Bounds (lat/lon aprox.)</p>
              <p className="font-medium">
                W {fmtCoord(geo.bounds.west)} · S {fmtCoord(geo.bounds.south)} ·
                E {fmtCoord(geo.bounds.east)} · N {fmtCoord(geo.bounds.north)}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Progreso */}
      {sesion.estado === "procesando" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Progreso</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Progress value={sesion.porcentaje} />
            <p className="text-sm text-muted-foreground">
              Procesando tile {sesion.tiles_procesados} de {sesion.total_tiles}{" "}
              ({sesion.porcentaje}%)
            </p>
          </CardContent>
        </Card>
      )}

      {/* Error */}
      {sesion.estado === "error" && (
        <div className="flex items-start justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <div className="flex gap-3">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <div>
              <p className="font-medium">La conversión falló</p>
              <p>{sesion.error_mensaje}</p>
            </div>
          </div>
        </div>
      )}

      {/* Resultado */}
      {sesion.estado === "completado" && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Tiles generados
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">
                  {sesion.tiles_procesados}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Tiles omitidos (vacíos)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{omitidos}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Tamaño de tile
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{sesion.tile_size}px</div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Cómo usar en CVAT</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <ol className="list-inside list-decimal space-y-1">
                <li>En CVAT, crear un nuevo proyecto o tarea.</li>
                <li>Seleccionar &quot;Upload data&quot; y subir el .zip completo.</li>
                <li>
                  CVAT importará automáticamente todos los JPG como imágenes
                  independientes.
                </li>
                <li>Anotar las plantas con bounding boxes.</li>
                <li>
                  Exportar en formato YOLO para usar en el módulo de
                  entrenamiento.
                </li>
              </ol>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
