"use client";

import { ArrowLeft, Download, Map, Play } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EstadoBadge } from "@/components/vuelos/EstadoBadge";
import { ImageUploader } from "@/components/vuelos/ImageUploader";
import { ProcessingStatus } from "@/components/vuelos/ProcessingStatus";
import VisorDetecciones from "@/components/vuelos/VisorDetecciones";
import {
  useProcessVuelo,
  useVuelo,
  useVueloImagenes,
} from "@/hooks/useVuelos";
import { vuelosService } from "@/services/vuelos.service";

// TODO FASE 3: Agregar panel de comparación histórica entre vuelos

export default function VueloDetallePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const { data: vuelo, isLoading } = useVuelo(id);
  const { data: imagenes } = useVueloImagenes(id, vuelo?.estado);
  const processVuelo = useProcessVuelo();

  if (isLoading) return <LoadingSpinner />;
  if (!vuelo) return <p className="text-muted-foreground">Vuelo no encontrado.</p>;

  async function handleProcess() {
    try {
      await processVuelo.mutateAsync(id);
      toast.success("Procesamiento iniciado");
    } catch {
      toast.error("No se pudo iniciar el procesamiento");
    }
  }

  async function handleExport() {
    try {
      await vuelosService.downloadCsv(id);
    } catch {
      toast.error("No se pudo exportar el CSV");
    }
  }

  const imagenesProcesadas = (imagenes?.results ?? []).filter(
    (img) => img.procesada,
  );

  const stats = [
    { label: "Total de plantas", value: vuelo.total_plantas },
    { label: "Imágenes cargadas", value: vuelo.total_imagenes },
    { label: "Imágenes procesadas", value: vuelo.imagenes_procesadas },
    { label: "% procesado", value: `${vuelo.porcentaje_procesado}%` },
  ];

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/vuelos">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Volver a vuelos
        </Link>
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight">
              {vuelo.nombre}
            </h2>
            <EstadoBadge estado={vuelo.estado} />
          </div>
          <p className="text-muted-foreground">
            {vuelo.campo_nombre ? `${vuelo.campo_nombre} · ` : ""}
            {vuelo.modulo_nombre} · {vuelo.fecha_vuelo}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ImageUploader vueloId={id} />
          <Button
            onClick={handleProcess}
            disabled={
              processVuelo.isPending ||
              vuelo.estado === "procesando" ||
              vuelo.total_imagenes === 0
            }
          >
            <Play className="mr-2 h-4 w-4" />
            Procesar vuelo
          </Button>
          {vuelo.estado === "completado" && (
            <>
              <Button asChild variant="outline">
                <Link href={`/vuelos/${id}/mapa`}>
                  <Map className="mr-2 h-4 w-4" />
                  Ver en mapa
                </Link>
              </Button>
              <Button variant="outline" onClick={handleExport}>
                <Download className="mr-2 h-4 w-4" />
                Exportar CSV
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {s.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {vuelo.estado === "completado" && imagenesProcesadas.length > 0 && (
        <VisorDetecciones vueloId={vuelo.id} imagenes={imagenesProcesadas} />
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Progreso</CardTitle>
        </CardHeader>
        <CardContent>
          <ProcessingStatus vuelo={vuelo} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Imágenes</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nombre</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Plantas</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {imagenes && imagenes.results.length > 0 ? (
                imagenes.results.map((img) => (
                  <TableRow key={img.id}>
                    <TableCell className="font-medium">
                      {img.nombre_original}
                    </TableCell>
                    <TableCell>
                      {img.procesada ? (
                        <span className="text-green-600">Procesada</span>
                      ) : (
                        <span className="text-muted-foreground">
                          Pendiente
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {img.conteo_plantas}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell
                    colSpan={3}
                    className="h-24 text-center text-muted-foreground"
                  >
                    No hay imágenes cargadas.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
