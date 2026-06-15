"use client";

import { ArrowLeft, Info, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useCreateSesion, useImagenesTiff } from "@/hooks/useConverter";

type Fuente = "upload" | "vuelo";

export default function NuevaConversionPage() {
  const router = useRouter();
  const createSesion = useCreateSesion();
  const { data: imagenesTiff } = useImagenesTiff();

  const [nombre, setNombre] = useState("");
  const [fuente, setFuente] = useState<Fuente>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [imagenVuelo, setImagenVuelo] = useState<number | "">("");
  const [tileSize, setTileSize] = useState(640);
  const [overlap, setOverlap] = useState(64);
  const [calidad, setCalidad] = useState(85);
  const [saltarVacios, setSaltarVacios] = useState(true);
  const [notas, setNotas] = useState("");
  const [progress, setProgress] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleSubmit() {
    if (nombre.trim().length < 3) {
      toast.error("El nombre debe tener al menos 3 caracteres");
      return;
    }
    if (fuente === "upload" && !file) {
      toast.error("Seleccioná un archivo GeoTIFF");
      return;
    }
    if (fuente === "vuelo" && !imagenVuelo) {
      toast.error("Seleccioná una imagen de vuelo");
      return;
    }
    if (overlap >= Math.floor(tileSize / 2)) {
      toast.error("El solapamiento debe ser menor a tile_size / 2");
      return;
    }
    setProgress(0);
    try {
      const sesion = await createSesion.mutateAsync({
        payload: {
          nombre,
          fuente,
          archivo_tiff: fuente === "upload" ? file ?? undefined : undefined,
          imagen_vuelo:
            fuente === "vuelo" ? Number(imagenVuelo) : undefined,
          tile_size: tileSize,
          overlap_px: overlap,
          calidad_jpg: calidad,
          saltar_vacios: saltarVacios,
          notas: notas || undefined,
        },
        onProgress: setProgress,
      });
      toast.success("Conversión iniciada");
      router.push(`/converter/${sesion.id}`);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { error?: string } } })?.response?.data
          ?.error ?? "No se pudo iniciar la conversión";
      toast.error(msg);
    }
  }

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/converter">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Volver a conversiones
        </Link>
      </Button>

      <div>
        <h2 className="text-2xl font-bold tracking-tight">Nueva conversión</h2>
        <p className="text-muted-foreground">
          Convertí un GeoTIFF en tiles JPG listos para CVAT.
        </p>
      </div>

      <Card className="border-blue-200 bg-blue-50">
        <CardContent className="flex gap-3 pt-6 text-sm text-blue-800">
          <Info className="h-5 w-5 shrink-0" />
          <p>
            Los tiles JPG no contienen coordenadas GPS (CVAT no las necesita).
            Los metadatos geoespaciales se guardan en el servidor para uso
            futuro con mapas.
          </p>
        </CardContent>
      </Card>

      {/* Paso 1: fuente */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">1. Fuente del GeoTIFF</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Nombre de la sesión</label>
            <Input
              placeholder="Ortomosaico lote norte"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
            />
          </div>

          <div className="flex gap-2">
            <Button
              type="button"
              variant={fuente === "upload" ? "default" : "outline"}
              onClick={() => setFuente("upload")}
            >
              Upload nuevo TIFF
            </Button>
            <Button
              type="button"
              variant={fuente === "vuelo" ? "default" : "outline"}
              onClick={() => setFuente("vuelo")}
            >
              Imagen de vuelo existente
            </Button>
          </div>

          {fuente === "upload" ? (
            <>
              <input
                ref={inputRef}
                type="file"
                accept=".tif,.tiff"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-input p-8 text-sm text-muted-foreground transition-colors hover:border-primary"
              >
                <Upload className="h-8 w-8" />
                <span>{file ? file.name : "Seleccioná el GeoTIFF (.tif / .tiff)"}</span>
                <span className="text-xs">
                  Archivos grandes (100 MB–2 GB) soportados
                </span>
              </button>
            </>
          ) : (
            <div className="space-y-2">
              <label className="text-sm font-medium">
                Imagen TIFF de vuelo
              </label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={imagenVuelo}
                onChange={(e) =>
                  setImagenVuelo(
                    e.target.value ? Number(e.target.value) : "",
                  )
                }
              >
                <option value="">Seleccioná una imagen…</option>
                {imagenesTiff?.map((img) => (
                  <option key={img.id} value={img.id}>
                    {img.nombre_original}
                  </option>
                ))}
              </select>
              {imagenesTiff && imagenesTiff.length === 0 && (
                <p className="text-xs text-amber-700">
                  No hay imágenes .tif/.tiff cargadas en vuelos.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Paso 2: parámetros de tiles */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            2. Parámetros de los tiles
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Tamaño de tile</label>
              <span className="text-sm text-muted-foreground">
                {tileSize} × {tileSize} px
              </span>
            </div>
            <input
              type="range"
              min={128}
              max={2048}
              step={32}
              value={tileSize}
              onChange={(e) => setTileSize(Number(e.target.value))}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              640×640 = óptimo para YOLOv8.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Solapamiento</label>
              <span className="text-sm text-muted-foreground">
                {overlap} px
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={512}
              step={16}
              value={overlap}
              onChange={(e) => setOverlap(Number(e.target.value))}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Evita cortar objetos en los bordes (debe ser &lt; tile_size / 2).
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Calidad JPG</label>
              <span className="text-sm text-muted-foreground">{calidad}%</span>
            </div>
            <input
              type="range"
              min={50}
              max={100}
              step={1}
              value={calidad}
              onChange={(e) => setCalidad(Number(e.target.value))}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              85 es un buen balance tamaño/calidad.
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={saltarVacios}
              onChange={(e) => setSaltarVacios(e.target.checked)}
              className="h-4 w-4"
            />
            Saltar tiles vacíos (omite zonas negras sin imagen)
          </label>

          <div className="space-y-2">
            <label className="text-sm font-medium">Notas (opcional)</label>
            <Input
              placeholder="Observaciones"
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
            />
          </div>

          {createSesion.isPending && progress > 0 && (
            <Progress value={progress} />
          )}

          <Button onClick={handleSubmit} disabled={createSesion.isPending}>
            {createSesion.isPending
              ? progress < 100
                ? `Subiendo... ${progress}%`
                : "Iniciando..."
              : "Iniciar conversión"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
