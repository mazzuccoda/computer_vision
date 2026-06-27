"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, ArrowLeft, CheckCircle2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useUploadDataset } from "@/hooks/useDatasets";
import { useCreateModelo } from "@/hooks/useModelos";
import { DatasetEntrenamiento } from "@/types";

const schema = z.object({
  nombre: z.string().min(3, "Mínimo 3 caracteres"),
  base_model: z.enum(["yolov8n.pt", "yolov8s.pt", "yolov8m.pt"]),
  epochs: z.coerce.number().min(5).max(500),
  img_size: z.coerce.number().min(320).max(1280),
  patience: z.coerce.number().min(3).max(100),
  notas: z.string().optional(),
});

type FormValues = z.input<typeof schema>;

// Cloudflare corta los requests con body > 100 MB antes de llegar al backend.
const MAX_UPLOAD_MB = 100;

function mensajeErrorUpload(err: unknown, generico: string): string {
  const res = (err as { response?: { status?: number; data?: unknown } })
    ?.response;
  if (res?.status === 413) {
    return `El .zip supera el límite de ${MAX_UPLOAD_MB} MB para subir por la web. Reducí el tamaño del dataset o pedí subirlo por otra vía.`;
  }
  const data = res?.data;
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (typeof obj.error === "string") return obj.error;
    if (typeof obj.detail === "string") return obj.detail;
    const primero = Object.values(obj)[0];
    if (Array.isArray(primero) && typeof primero[0] === "string") {
      return primero[0];
    }
    if (typeof primero === "string") return primero;
  }
  if (res?.status) return `${generico} (HTTP ${res.status})`;
  return generico;
}

const FORMATOS: { value: DatasetEntrenamiento["formato"]; label: string }[] = [
  { value: "yolo", label: "YOLO Ultralytics (recomendado)" },
  { value: "cvat_xml", label: "CVAT for Images 1.1 XML (Fase 2)" },
  { value: "coco", label: "COCO JSON (Fase 2)" },
];

export default function NuevoModeloPage() {
  const router = useRouter();
  const uploadDataset = useUploadDataset();
  const createModelo = useCreateModelo();

  const [dataset, setDataset] = useState<DatasetEntrenamiento | null>(null);
  const [dsNombre, setDsNombre] = useState("");
  const [formato, setFormato] =
    useState<DatasetEntrenamiento["formato"]>("yolo");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre: "",
      base_model: "yolov8n.pt",
      epochs: 50,
      img_size: 640,
      patience: 10,
      notas: "",
    },
  });

  async function handleUpload() {
    if (!dsNombre.trim()) {
      toast.error("Poné un nombre al dataset");
      return;
    }
    if (!file) {
      toast.error("Seleccioná un archivo .zip");
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      toast.error(
        `El .zip pesa ${(file.size / 1024 / 1024).toFixed(0)} MB y supera el límite de ${MAX_UPLOAD_MB} MB para subir por la web.`,
      );
      return;
    }
    setProgress(0);
    try {
      const ds = await uploadDataset.mutateAsync({
        nombre: dsNombre,
        formato,
        archivo: file,
        onProgress: setProgress,
      });
      setDataset(ds);
      if (ds.estado === "invalido") {
        toast.error("El dataset no es válido");
      } else {
        toast.success("Dataset validado");
      }
    } catch (err) {
      toast.error(mensajeErrorUpload(err, "No se pudo subir el dataset"));
    }
  }

  async function onSubmit(values: FormValues) {
    if (!dataset || dataset.estado !== "valido") {
      toast.error("Subí y validá un dataset primero");
      return;
    }
    const payload = schema.parse(values);
    try {
      const modelo = await createModelo.mutateAsync({
        ...payload,
        dataset: dataset.id,
      });
      toast.success("Entrenamiento iniciado");
      router.push(`/modelos/${modelo.id}`);
    } catch (err) {
      toast.error(mensajeErrorUpload(err, "No se pudo iniciar el entrenamiento"));
    }
  }

  const datasetValido = dataset?.estado === "valido";

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/modelos">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Volver a modelos
        </Link>
      </Button>

      <div>
        <h2 className="text-2xl font-bold tracking-tight">
          Nuevo entrenamiento
        </h2>
        <p className="text-muted-foreground">
          Subí un dataset anotado y configurá el entrenamiento del modelo.
        </p>
      </div>

      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="flex gap-3 pt-6 text-sm text-amber-800">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p>
            El entrenamiento en CPU puede tardar de minutos a horas según el
            dataset. Recomendamos <strong>yolov8n</strong> y menos de 300
            imágenes para el MVP.
          </p>
        </CardContent>
      </Card>

      {/* Paso 1: dataset */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">1. Dataset anotado</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Nombre del dataset</label>
              <Input
                placeholder="Plantas lote norte"
                value={dsNombre}
                onChange={(e) => setDsNombre(e.target.value)}
                disabled={datasetValido}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Formato</label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={formato}
                onChange={(e) =>
                  setFormato(
                    e.target.value as DatasetEntrenamiento["formato"],
                  )
                }
                disabled={datasetValido}
              >
                {FORMATOS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={datasetValido}
            className="flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-input p-8 text-sm text-muted-foreground transition-colors hover:border-primary disabled:opacity-50"
          >
            <Upload className="h-8 w-8" />
            <span>{file ? file.name : "Seleccioná el export (.zip)"}</span>
            <span className="text-xs">
              Estructura YOLO: images/, labels/, classes.txt · máx. {MAX_UPLOAD_MB} MB
            </span>
          </button>

          {uploadDataset.isPending && <Progress value={progress} />}

          {!datasetValido && (
            <Button
              onClick={handleUpload}
              disabled={uploadDataset.isPending || !file}
            >
              {uploadDataset.isPending
                ? `Validando... ${progress}%`
                : "Subir y validar"}
            </Button>
          )}

          {dataset && (
            <ValidationReport dataset={dataset} />
          )}
        </CardContent>
      </Card>

      {/* Paso 2: configuración */}
      <Card className={datasetValido ? "" : "opacity-60"}>
        <CardHeader>
          <CardTitle className="text-base">
            2. Configuración del entrenamiento
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="space-y-4"
            >
              <FormField
                control={form.control}
                name="nombre"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombre del modelo</FormLabel>
                    <FormControl>
                      <Input placeholder="Detector plantas v1" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="base_model"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Modelo base</FormLabel>
                    <FormControl>
                      <select
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        {...field}
                      >
                        <option value="yolov8n.pt">
                          YOLOv8 Nano (más rápido, CPU)
                        </option>
                        <option value="yolov8s.pt">YOLOv8 Small</option>
                        <option value="yolov8m.pt">YOLOv8 Medium</option>
                      </select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="grid gap-4 sm:grid-cols-3">
                <FormField
                  control={form.control}
                  name="epochs"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Épocas</FormLabel>
                      <FormControl>
                        <Input type="number" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="img_size"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Tamaño imagen</FormLabel>
                      <FormControl>
                        <Input type="number" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="patience"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Patience</FormLabel>
                      <FormControl>
                        <Input type="number" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <FormField
                control={form.control}
                name="notas"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Notas (opcional)</FormLabel>
                    <FormControl>
                      <Input placeholder="Observaciones" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button
                type="submit"
                disabled={!datasetValido || createModelo.isPending}
              >
                {createModelo.isPending
                  ? "Iniciando..."
                  : "Iniciar entrenamiento"}
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}

function ValidationReport({
  dataset,
}: {
  dataset: DatasetEntrenamiento;
}) {
  if (dataset.estado === "invalido") {
    return (
      <div className="flex gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <AlertTriangle className="h-5 w-5 shrink-0" />
        <div>
          <p className="font-medium">Dataset inválido</p>
          <p>{dataset.reporte_validacion?.error}</p>
        </div>
      </div>
    );
  }

  const rep = dataset.reporte_validacion;
  return (
    <div className="space-y-2 rounded-md border border-green-200 bg-green-50 p-4 text-sm text-green-900">
      <div className="flex items-center gap-2 font-medium">
        <CheckCircle2 className="h-5 w-5" />
        Dataset válido
      </div>
      <p>
        {rep?.total_imagenes ?? dataset.num_imagenes} imágenes ·{" "}
        {rep?.total_anotaciones ?? 0} anotaciones · clases:{" "}
        {dataset.clases.join(", ") || "—"}
      </p>
      {rep?.distribucion_por_clase && (
        <p className="text-xs">
          {Object.entries(rep.distribucion_por_clase)
            .map(([c, n]) => `${c}: ${n}`)
            .join(" · ")}
        </p>
      )}
      {rep?.warnings && rep.warnings.length > 0 && (
        <ul className="list-inside list-disc text-xs text-amber-700">
          {rep.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
