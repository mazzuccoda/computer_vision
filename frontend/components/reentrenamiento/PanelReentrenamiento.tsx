"use client";

import { useEffect, useState } from "react";
import { Loader2, Play, RefreshCw, Settings2, Zap } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import {
  useActivarCiclo,
  useCiclosReentrenamiento,
  useDispararReentrenamiento,
  useEstadoReentrenamiento,
  useUpdateConfigReentrenamiento,
} from "@/hooks/useReentrenamiento";
import type { CicloEstado } from "@/types";

const EN_PROGRESO: CicloEstado[] = [
  "pendiente",
  "construyendo",
  "entrenando",
  "evaluando",
];

const ESTADO_COLOR: Record<CicloEstado, string> = {
  pendiente: "bg-slate-500",
  construyendo: "bg-blue-500",
  entrenando: "bg-blue-600",
  evaluando: "bg-indigo-600",
  completado: "bg-amber-500",
  activado: "bg-emerald-600",
  error: "bg-red-600",
};

const fmtMap = (v: number | null | undefined) =>
  v == null ? "—" : v.toFixed(4);

export default function PanelReentrenamiento() {
  const { data: estado, isLoading } = useEstadoReentrenamiento();
  const { data: ciclos = [] } = useCiclosReentrenamiento();
  const disparar = useDispararReentrenamiento();
  const updateConfig = useUpdateConfigReentrenamiento();
  const activar = useActivarCiclo();

  const [umbral, setUmbral] = useState(50);
  const [epochs, setEpochs] = useState(50);
  const [margen, setMargen] = useState(0);

  useEffect(() => {
    if (estado?.config) {
      setUmbral(estado.config.umbral_correcciones);
      setEpochs(estado.config.epochs);
      setMargen(estado.config.margen_map50);
    }
  }, [estado?.config]);

  if (isLoading || !estado) {
    return (
      <div className="flex h-40 items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Cargando…
      </div>
    );
  }

  const { config, imagenes_revisadas, modelo_activo, ultimo_ciclo } = estado;
  const enProgreso =
    !!ultimo_ciclo && EN_PROGRESO.includes(ultimo_ciclo.estado);
  const pct = config.umbral_correcciones
    ? Math.min(
        100,
        (config.correcciones_acumuladas / config.umbral_correcciones) * 100,
      )
    : 0;

  const handleDisparar = async () => {
    try {
      await disparar.mutateAsync();
      toast.success("Reentrenamiento encolado", {
        description: "Seguí el progreso en esta página.",
      });
    } catch (e) {
      const msg =
        (e as { response?: { data?: { error?: string } } }).response?.data
          ?.error ?? "No se pudo iniciar el reentrenamiento.";
      toast.error(msg);
    }
  };

  const handleGuardarConfig = async (
    extra?: Partial<{
      auto_reentrenar: boolean;
      auto_activar_modelo: boolean;
    }>,
  ) => {
    try {
      await updateConfig.mutateAsync({
        umbral_correcciones: umbral,
        epochs,
        margen_map50: margen,
        ...extra,
      });
      toast.success("Configuración guardada");
    } catch {
      toast.error("No se pudo guardar la configuración.");
    }
  };

  const handleActivar = async (cicloId: number) => {
    try {
      await activar.mutateAsync(cicloId);
      toast.success("Modelo activado (bypass de mAP).");
    } catch {
      toast.error("No se pudo activar el modelo.");
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Estado del ciclo */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Zap className="h-4 w-4 text-amber-500" />
            Correcciones acumuladas
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-3xl font-bold">
                {config.correcciones_acumuladas}
              </span>
              <span className="text-sm text-muted-foreground">
                umbral {config.umbral_correcciones}
              </span>
            </div>
            <Progress value={pct} className="mt-2" />
            <p className="mt-1 text-xs text-muted-foreground">
              {config.auto_reentrenar
                ? `Reentrena automáticamente al llegar a ${config.umbral_correcciones}.`
                : "Auto-reentrenamiento desactivado."}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-md border p-2">
              <p className="text-xs text-muted-foreground">
                Imágenes revisadas
              </p>
              <p className="text-lg font-semibold">{imagenes_revisadas}</p>
            </div>
            <div className="rounded-md border p-2">
              <p className="text-xs text-muted-foreground">Modelo activo</p>
              <p className="truncate text-sm font-semibold">
                {modelo_activo
                  ? `${modelo_activo.nombre} (${modelo_activo.version})`
                  : "—"}
              </p>
              <p className="text-xs text-muted-foreground">
                mAP50 {fmtMap(modelo_activo?.map50)}
              </p>
            </div>
          </div>

          <Button
            className="w-full"
            onClick={handleDisparar}
            disabled={disparar.isPending || enProgreso}
          >
            {enProgreso ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            {enProgreso ? "Reentrenando…" : "Reentrenar ahora"}
          </Button>
        </CardContent>
      </Card>

      {/* Configuración */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4" />
            Configuración
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="auto" className="text-sm">
              Reentrenar automáticamente
            </Label>
            <Switch
              id="auto"
              checked={config.auto_reentrenar}
              onCheckedChange={(v) =>
                handleGuardarConfig({ auto_reentrenar: v })
              }
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="autoact" className="text-sm">
              Auto-activar si mejora (gate mAP50)
            </Label>
            <Switch
              id="autoact"
              checked={config.auto_activar_modelo}
              onCheckedChange={(v) =>
                handleGuardarConfig({ auto_activar_modelo: v })
              }
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label htmlFor="umbral" className="text-xs">
                Umbral
              </Label>
              <Input
                id="umbral"
                type="number"
                min={1}
                value={umbral}
                onChange={(e) => setUmbral(Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="epochs" className="text-xs">
                Épocas
              </Label>
              <Input
                id="epochs"
                type="number"
                min={1}
                value={epochs}
                onChange={(e) => setEpochs(Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="margen" className="text-xs">
                Margen mAP50
              </Label>
              <Input
                id="margen"
                type="number"
                step={0.01}
                min={0}
                value={margen}
                onChange={(e) => setMargen(Number(e.target.value))}
              />
            </div>
          </div>

          <Button
            variant="outline"
            className="w-full"
            onClick={() => handleGuardarConfig()}
            disabled={updateConfig.isPending}
          >
            {updateConfig.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Guardar configuración
          </Button>
        </CardContent>
      </Card>

      {/* Historial de ciclos */}
      <Card className="lg:col-span-2">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Historial de ciclos</CardTitle>
        </CardHeader>
        <CardContent>
          {ciclos.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Todavía no hay ciclos de reentrenamiento.
            </p>
          ) : (
            <div className="space-y-2">
              {ciclos.map((c) => (
                <div
                  key={c.id}
                  className="flex flex-wrap items-center gap-3 rounded-md border p-3"
                >
                  <Badge
                    className={`${ESTADO_COLOR[c.estado]} hover:${ESTADO_COLOR[c.estado]}`}
                  >
                    {c.estado}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    #{c.id} · {c.disparador}
                  </span>
                  <span className="text-xs">
                    {c.num_imagenes} imgs · {c.num_anotaciones} anns
                  </span>
                  <span className="text-xs">
                    mAP50 {fmtMap(c.map50_anterior)} →{" "}
                    <strong>{fmtMap(c.map50_nuevo)}</strong>
                  </span>
                  {c.activado && (
                    <Badge variant="secondary" className="text-emerald-600">
                      activado
                    </Badge>
                  )}
                  {c.mensaje && (
                    <span className="w-full text-xs text-muted-foreground sm:w-auto sm:flex-1">
                      {c.mensaje}
                    </span>
                  )}
                  {c.estado === "completado" && !c.activado && c.modelo && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="ml-auto"
                      onClick={() => handleActivar(c.id)}
                      disabled={activar.isPending}
                    >
                      Activar igual
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
