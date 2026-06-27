"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  Trash2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { EstadoModeloBadge } from "@/components/modelos/EstadoModeloBadge";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  useActivateModelo,
  useCancelModelo,
  useDeleteModelo,
  useModelo,
} from "@/hooks/useModelos";
import { modelosService } from "@/services/modelos.service";

function fmt(value?: number): string {
  if (value === undefined || value === null) return "—";
  return value.toFixed(4);
}

export default function ModeloDetallePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const router = useRouter();
  const { data: modelo, isLoading } = useModelo(id);
  const activate = useActivateModelo();
  const cancelar = useCancelModelo();
  const eliminar = useDeleteModelo();

  const enProgreso =
    modelo?.estado === "pendiente" ||
    modelo?.estado === "preparando" ||
    modelo?.estado === "entrenando";

  const { data: results } = useQuery({
    queryKey: ["modelo-results", id],
    queryFn: () => modelosService.results(id),
    enabled: Number.isFinite(id) && modelo?.estado === "completado",
  });

  if (isLoading) return <LoadingSpinner />;
  if (!modelo)
    return <p className="text-muted-foreground">Modelo no encontrado.</p>;

  async function handleActivate() {
    try {
      await activate.mutateAsync(id);
      toast.success("Modelo activado — la inferencia lo usará");
    } catch {
      toast.error("No se pudo activar el modelo");
    }
  }

  async function handleCancelar() {
    if (!window.confirm("¿Cancelar este entrenamiento?")) return;
    try {
      await cancelar.mutateAsync(id);
      toast.success("Entrenamiento cancelado");
    } catch {
      toast.error("No se pudo cancelar el entrenamiento");
    }
  }

  async function handleEliminar() {
    if (!window.confirm("¿Eliminar este modelo?")) return;
    try {
      await eliminar.mutateAsync(id);
      toast.success("Modelo eliminado");
      router.push("/modelos");
    } catch {
      toast.error("No se pudo eliminar (¿está activo?)");
    }
  }

  async function handleDownload() {
    try {
      await modelosService.download(id, modelo!.nombre, modelo!.version);
    } catch {
      toast.error("No se pudo descargar el entregable");
    }
  }

  const metricas = [
    { label: "mAP50", value: fmt(modelo.metricas?.map50) },
    { label: "mAP50-95", value: fmt(modelo.metricas?.map50_95) },
    { label: "Precision", value: fmt(modelo.metricas?.precision) },
    { label: "Recall", value: fmt(modelo.metricas?.recall) },
  ];

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/modelos">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Volver a modelos
        </Link>
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight">
              {modelo.nombre}
            </h2>
            <EstadoModeloBadge estado={modelo.estado} />
            {modelo.activo && (
              <Badge className="border-0 bg-green-600 text-white hover:bg-green-600">
                ACTIVO
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground">
            {modelo.version} · {modelo.base_model} ·{" "}
            {modelo.dataset_nombre ?? `dataset #${modelo.dataset}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {modelo.estado === "completado" && (
            <>
              {!modelo.activo && (
                <Button
                  onClick={handleActivate}
                  disabled={activate.isPending}
                >
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                  Activar modelo
                </Button>
              )}
              <Button variant="outline" onClick={handleDownload}>
                <Download className="mr-2 h-4 w-4" />
                Descargar .zip
              </Button>
            </>
          )}
          {enProgreso && (
            <Button
              variant="outline"
              className="text-amber-700 hover:text-amber-800"
              onClick={handleCancelar}
              disabled={cancelar.isPending}
            >
              <XCircle className="mr-2 h-4 w-4" />
              Cancelar entrenamiento
            </Button>
          )}
          {!modelo.activo && (
            <Button
              variant="outline"
              className="text-red-600 hover:text-red-700"
              onClick={handleEliminar}
              disabled={eliminar.isPending}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Eliminar
            </Button>
          )}
        </div>
      </div>

      {enProgreso && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Progreso</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Progress value={modelo.porcentaje} />
            <p className="text-sm text-muted-foreground">
              Época {modelo.epoca_actual} de {modelo.epochs} (
              {modelo.porcentaje}%)
            </p>
          </CardContent>
        </Card>
      )}

      {modelo.estado === "cancelado" && (
        <div className="flex gap-3 rounded-md border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
          <XCircle className="h-5 w-5 shrink-0" />
          <div>
            <p className="font-medium">Entrenamiento cancelado</p>
            <p>{modelo.error_mensaje}</p>
          </div>
        </div>
      )}

      {modelo.estado === "error" && (
        <div className="flex gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <div>
            <p className="font-medium">El entrenamiento falló</p>
            <p>{modelo.error_mensaje}</p>
          </div>
        </div>
      )}

      {modelo.estado === "completado" && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {metricas.map((m) => (
              <Card key={m.label}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    {m.label}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{m.value}</div>
                </CardContent>
              </Card>
            ))}
          </div>

          {results && Object.keys(results.imagenes).length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(results.imagenes).map(([name, url]) => (
                <Card key={name}>
                  <CardHeader>
                    <CardTitle className="text-base">{name}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={url}
                      alt={name}
                      className="w-full rounded-md border"
                    />
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
