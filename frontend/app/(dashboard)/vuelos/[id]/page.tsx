"use client";

import {
  ArrowLeft,
  Combine,
  CopyMinus,
  Download,
  Map,
  Play,
  RotateCcw,
  Trash2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  useCancelVuelo,
  useDeduplicarVuelo,
  useDeleteVuelo,
  useProcessVuelo,
  useRededuplicarVuelo,
  useVuelo,
  useVueloImagenes,
} from "@/hooks/useVuelos";
import { vuelosService } from "@/services/vuelos.service";

// TODO FASE 3: Agregar panel de comparación histórica entre vuelos

export default function VueloDetallePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const router = useRouter();
  const { data: vuelo, isLoading } = useVuelo(id);
  const { data: imagenes } = useVueloImagenes(id, vuelo?.estado);
  const processVuelo = useProcessVuelo();
  const cancelVuelo = useCancelVuelo();
  const deduplicarVuelo = useDeduplicarVuelo();
  const rededuplicarVuelo = useRededuplicarVuelo();
  const deleteVuelo = useDeleteVuelo();

  const [iouThr, setIouThr] = useState("0.3");
  const [iosThr, setIosThr] = useState("0.4");
  const [distThr, setDistThr] = useState("60");

  if (isLoading) return <LoadingSpinner />;
  if (!vuelo) return <p className="text-muted-foreground">Vuelo no encontrado.</p>;

  async function handleProcess() {
    try {
      await processVuelo.mutateAsync({ id });
      toast.success("Procesamiento iniciado");
    } catch {
      toast.error("No se pudo iniciar el procesamiento");
    }
  }

  async function handleReprocess() {
    if (
      !window.confirm(
        "Esto borra las detecciones actuales y vuelve a procesar todo el " +
          "vuelo con el modelo activo. ¿Continuar?",
      )
    )
      return;
    try {
      await processVuelo.mutateAsync({ id, reprocesar: true });
      toast.success("Reprocesamiento iniciado con el modelo activo");
    } catch {
      toast.error("No se pudo reprocesar el vuelo");
    }
  }

  async function handleCancel() {
    if (
      !window.confirm(
        "Esto detiene el procesamiento en curso. Las detecciones ya " +
          "guardadas se conservan. ¿Continuar?",
      )
    )
      return;
    try {
      await cancelVuelo.mutateAsync(id);
      toast.success("Procesamiento cancelado");
    } catch {
      toast.error("No se pudo cancelar el procesamiento");
    }
  }

  async function handleDeduplicar() {
    if (
      !window.confirm(
        "Quita detecciones duplicadas exactas (la misma planta marcada más " +
          "de una vez por un procesamiento repetido). No reinfiere el vuelo. " +
          "¿Continuar?",
      )
    )
      return;
    try {
      const r = await deduplicarVuelo.mutateAsync(id);
      toast.success(
        `${r.eliminadas.toLocaleString()} duplicados eliminados · ` +
          `${r.total_plantas.toLocaleString()} plantas`,
      );
    } catch {
      toast.error("No se pudieron quitar los duplicados");
    }
  }

  async function handleRededuplicar() {
    if (
      !window.confirm(
        "Re-deduplica las detecciones YA guardadas con estos umbrales " +
          "(IoU / IoS / distancia). No reinfiere el TIFF: corre en segundos y " +
          "borra las cajas redundantes. ¿Continuar?",
      )
    )
      return;
    try {
      const r = await rededuplicarVuelo.mutateAsync({
        id,
        params: {
          iou: iouThr === "" ? undefined : Number(iouThr),
          ios: iosThr === "" ? undefined : Number(iosThr),
          dist: distThr === "" ? undefined : Number(distThr),
        },
      });
      toast.success(
        `${r.eliminadas.toLocaleString()} cajas quitadas · ` +
          `${r.total_plantas.toLocaleString()} plantas ` +
          `(de ${r.total_antes.toLocaleString()})`,
      );
    } catch {
      toast.error("No se pudo re-deduplicar");
    }
  }

  async function handleDelete() {
    if (!window.confirm(`¿Eliminar el vuelo "${vuelo!.nombre}"?`)) return;
    try {
      await deleteVuelo.mutateAsync(id);
      toast.success("Vuelo eliminado");
      router.push("/vuelos");
    } catch {
      toast.error("No se pudo eliminar el vuelo");
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
          {vuelo.estado === "procesando" && (
            <Button
              variant="outline"
              className="text-red-600 hover:text-red-700"
              onClick={handleCancel}
              disabled={cancelVuelo.isPending}
            >
              <XCircle className="mr-2 h-4 w-4" />
              Cancelar procesamiento
            </Button>
          )}
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
          {vuelo.estado !== "procesando" &&
            vuelo.imagenes_procesadas > 0 && (
              <>
                <Button
                  variant="outline"
                  onClick={handleReprocess}
                  disabled={processVuelo.isPending}
                >
                  <RotateCcw className="mr-2 h-4 w-4" />
                  Reprocesar con modelo activo
                </Button>
                <Button
                  variant="outline"
                  onClick={handleDeduplicar}
                  disabled={deduplicarVuelo.isPending}
                >
                  <CopyMinus className="mr-2 h-4 w-4" />
                  Quitar duplicados
                </Button>
              </>
            )}
          <Button
            variant="outline"
            className="text-red-600 hover:text-red-700"
            onClick={handleDelete}
            disabled={deleteVuelo.isPending || vuelo.estado === "procesando"}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Eliminar vuelo
          </Button>
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

      {vuelo.estado !== "procesando" && vuelo.total_plantas > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Re-deduplicar (sin reprocesar)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Vuelve a aplicar el dedup geométrico sobre las detecciones ya
              guardadas con estos umbrales, en segundos y sin reinferir el TIFF.
              Más bajo = más agresivo. Conserva la detección de mayor confianza.
            </p>
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-1">
                <Label htmlFor="iou">IoU (solapamiento)</Label>
                <Input
                  id="iou"
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={iouThr}
                  onChange={(e) => setIouThr(e.target.value)}
                  className="w-32"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="ios">IoS (caja anidada)</Label>
                <Input
                  id="ios"
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={iosThr}
                  onChange={(e) => setIosThr(e.target.value)}
                  className="w-32"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="dist">Distancia centros (px)</Label>
                <Input
                  id="dist"
                  type="number"
                  step="5"
                  min="0"
                  value={distThr}
                  onChange={(e) => setDistThr(e.target.value)}
                  className="w-36"
                />
              </div>
              <Button
                variant="outline"
                onClick={handleRededuplicar}
                disabled={rededuplicarVuelo.isPending}
              >
                <Combine className="mr-2 h-4 w-4" />
                {rededuplicarVuelo.isPending
                  ? "Procesando…"
                  : "Re-deduplicar"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

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
