"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { Pencil } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import EditorDetecciones from "@/components/vuelos/EditorDetecciones";
import api from "@/services/api";
import type { Deteccion, Imagen } from "@/types";

// ---------------------------------------------------------------------------
// Colores por clase (CSS / canvas). Deben coincidir visualmente con OpenCV.
// ---------------------------------------------------------------------------
const COLORES: Record<string, string> = {
  planta: "#22c55e",
  maleza: "#ef4444",
  faltante: "#eab308",
  default: "#22c55e",
};
const colorPorClase = (clase: string) =>
  COLORES[clase.toLowerCase()] ?? COLORES.default;

interface Props {
  vueloId: number;
  imagenes: Imagen[]; // solo las que tienen procesada === true
}

export default function VisorDetecciones({ imagenes }: Props) {
  const [idx, setIdx] = useState(0);
  const [minConfianza, setMinConfianza] = useState(0.5);
  const [mostrarEtiquetas, setMostrarEtiquetas] = useState(true);
  const [descargando, setDescargando] = useState(false);
  const [editando, setEditando] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const imagenActiva = imagenes[idx] ?? null;

  // ── Detecciones de la imagen activa ──────────────────────────────────────
  const { data: detecciones = [], isLoading: cargandoDets } = useQuery<
    Deteccion[]
  >({
    queryKey: ["detecciones", imagenActiva?.id],
    queryFn: async () => {
      const res = await api.get(
        `/detecciones/?imagen_id=${imagenActiva!.id}`
      );
      return res.data.results ?? res.data;
    },
    enabled: !!imagenActiva,
    staleTime: 60_000,
  });

  // ── Dibujar en canvas ────────────────────────────────────────────────────
  const dibujar = useCallback(
    (
      ctx: CanvasRenderingContext2D,
      imgEl: HTMLImageElement,
      dets: Deteccion[],
      confianza: number,
      etiquetas: boolean,
      // Factor de decimado del JPG (ortofotos gigapíxel se sirven reducidas):
      // las coordenadas de detección están en píxeles nativos, hay que escalarlas.
      escala = 1
    ) => {
      const { naturalWidth: W, naturalHeight: H } = imgEl;
      ctx.canvas.width = W;
      ctx.canvas.height = H;
      ctx.drawImage(imgEl, 0, 0);

      const grosor = Math.max(1.5, W / 500);
      const fs = Math.max(11, W / 90);

      const filtradas = dets.filter((d) => d.confianza >= confianza);

      filtradas.forEach((det) => {
        const x1 = Math.max(0, det.x_min * escala);
        const y1 = Math.max(0, det.y_min * escala);
        const w = det.x_max * escala - x1;
        const h = det.y_max * escala - y1;
        if (w <= 0 || h <= 0) return;

        const color = colorPorClase(det.clase);

        // Caja
        ctx.strokeStyle = color;
        ctx.lineWidth = grosor;
        ctx.strokeRect(x1, y1, w, h);

        if (etiquetas) {
          const label = `${det.clase} ${(det.confianza * 100).toFixed(0)}%`;
          ctx.font = `500 ${fs}px sans-serif`;
          const tw = ctx.measureText(label).width;
          const pad = 5;

          // Posición etiqueta: arriba del box si hay espacio, sino abajo
          const ly =
            y1 - pad - 2 >= fs ? y1 - pad - 2 : det.y_max + fs + pad;

          // Fondo
          ctx.fillStyle = color;
          ctx.fillRect(x1, ly - fs - pad, tw + pad * 2 + 2, fs + pad * 2);

          // Texto oscuro sobre fondo de color
          ctx.fillStyle = "#052e16";
          ctx.fillText(label, x1 + pad, ly);
        }
      });

      // Watermark conteo
      const wm = `${filtradas.length} plantas detectadas`;
      const wfs = Math.max(11, W / 120);
      ctx.font = `${wfs}px sans-serif`;
      const ww = ctx.measureText(wm).width;
      ctx.fillStyle = "rgba(0,0,0,0.55)";
      ctx.fillRect(8, H - wfs - 14, ww + 16, wfs + 10);
      ctx.fillStyle = "#d1fae5";
      ctx.fillText(wm, 16, H - 8);
    },
    []
  );

  // ── Cargar imagen y redibujar ─────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !imagenActiva || cargandoDets) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const esTiff = /\.(tif|tiff)$/i.test(imagenActiva.nombre_original ?? "");

    if (esTiff) {
      // TIFF: el navegador no los renderiza; pedir JPG base sin boxes al backend
      // (min_confidence=1 → sin boxes) y dibujar los boxes encima en canvas.
      api
        .get(`/imagenes/${imagenActiva.id}/annotated/?min_confidence=1`, {
          responseType: "blob",
        })
        .then((res) => {
          const escala = parseFloat(res.headers["x-annotated-scale"]) || 1;
          const url = URL.createObjectURL(res.data);
          const img = new Image();
          img.onload = () => {
            dibujar(
              ctx,
              img,
              detecciones,
              minConfianza,
              mostrarEtiquetas,
              escala
            );
            URL.revokeObjectURL(url);
          };
          img.onerror = () => URL.revokeObjectURL(url);
          img.src = url;
        })
        .catch((err) => {
          console.error("Error cargando TIFF via /annotated/:", err);
        });
    } else {
      // JPG / PNG: cargar directamente en canvas
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () =>
        dibujar(ctx, img, detecciones, minConfianza, mostrarEtiquetas);
      img.onerror = () => {
        console.warn("No se pudo cargar la imagen:", imagenActiva.archivo);
      };
      img.src = imagenActiva.archivo;
    }
  }, [
    imagenActiva,
    detecciones,
    minConfianza,
    mostrarEtiquetas,
    cargandoDets,
    dibujar,
  ]);

  // ── Descargar JPG anotado generado por OpenCV ────────────────────────────
  const descargarJpg = useCallback(async () => {
    if (!imagenActiva) return;
    setDescargando(true);
    try {
      const res = await api.get(
        `/imagenes/${imagenActiva.id}/annotated/` +
          `?min_confidence=${minConfianza}&download=true`,
        { responseType: "blob" }
      );
      const url = URL.createObjectURL(res.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `anotada_${(imagenActiva.nombre_original ?? "imagen").replace(
        /\.[^/.]+$/,
        ""
      )}.jpg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Error al descargar", {
        description:
          "No se pudo generar la imagen anotada. Intenta de nuevo.",
      });
    } finally {
      setDescargando(false);
    }
  }, [imagenActiva, minConfianza]);

  // ── Guards ────────────────────────────────────────────────────────────────
  if (!imagenActiva) return null;

  if (editando) {
    return (
      <EditorDetecciones
        imagen={imagenActiva}
        detecciones={detecciones}
        onClose={() => setEditando(false)}
      />
    );
  }

  const detsFiltradas = detecciones.filter(
    (d) => d.confianza >= minConfianza
  );

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="border rounded-lg overflow-hidden">
      {/* ── Toolbar ── */}
      <div
        className="flex flex-wrap items-center gap-3 px-4 py-2
                   border-b bg-muted/40"
      >
        <span className="text-sm font-medium">Visor de detecciones</span>

        <Badge variant="secondary">
          imagen {idx + 1} / {imagenes.length}
        </Badge>
        <Badge variant="secondary">{detsFiltradas.length} plantas</Badge>

        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setEditando(true)}
          >
            <Pencil className="mr-1 h-4 w-4" />
            Editar
          </Button>
          {imagenActiva.revisada && (
            <Badge className="bg-emerald-600 hover:bg-emerald-600">
              revisada
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">Etiquetas</span>
          <Switch
            checked={mostrarEtiquetas}
            onCheckedChange={setMostrarEtiquetas}
          />
          <span className="text-xs text-muted-foreground">
            Umbral: {(minConfianza * 100).toFixed(0)}%
          </span>
          <Slider
            value={[Math.round(minConfianza * 100)]}
            onValueChange={([v]) => setMinConfianza(v / 100)}
            min={10}
            max={95}
            step={5}
            className="w-28"
          />
        </div>
      </div>

      {/* ── Canvas + panel lateral ── */}
      <div className="grid grid-cols-[1fr_128px]">
        {/* Canvas */}
        <div className="p-3 space-y-3">
          <div className="relative bg-black rounded overflow-hidden">
            {cargandoDets && (
              <div
                className="absolute inset-0 flex items-center justify-center
                           bg-black/40 z-10"
              >
                <span className="text-xs text-white/70">
                  Cargando detecciones…
                </span>
              </div>
            )}
            <canvas
              ref={canvasRef}
              style={{ width: "100%", height: "auto", display: "block" }}
            />
          </div>

          {/* Miniaturas */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={idx === 0}
              onClick={() => setIdx((i) => i - 1)}
            >
              ‹
            </Button>

            <div className="flex gap-1.5 overflow-x-auto flex-1 py-0.5">
              {imagenes.map((img, i) => (
                <button
                  key={img.id}
                  onClick={() => setIdx(i)}
                  className={`shrink-0 w-12 h-12 rounded overflow-hidden
                              border-2 transition-all
                              ${
                                i === idx
                                  ? "border-blue-500 opacity-100"
                                  : "border-transparent opacity-50 hover:opacity-80"
                              }`}
                >
                  {/* Intentar mostrar miniatura; si es TIFF, mostrar placeholder */}
                  {/\.(tif{1,2})$/i.test(img.nombre_original ?? "") ? (
                    <div
                      className="w-full h-full bg-muted flex items-center
                                 justify-center text-[9px] text-muted-foreground"
                    >
                      TIFF
                    </div>
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={img.archivo}
                      alt={img.nombre_original}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  )}
                </button>
              ))}
            </div>

            <Button
              variant="outline"
              size="sm"
              disabled={idx === imagenes.length - 1}
              onClick={() => setIdx((i) => i + 1)}
            >
              ›
            </Button>
          </div>
        </div>

        {/* Panel lateral: lista de detecciones + botón descarga */}
        <div
          className="border-l p-3 flex flex-col gap-1.5
                     overflow-y-auto max-h-[520px]"
        >
          <p className="text-xs font-medium text-muted-foreground mb-1">
            detecciones
          </p>

          {detsFiltradas.length === 0 && !cargandoDets && (
            <p className="text-xs text-muted-foreground">
              Sin detecciones con umbral {(minConfianza * 100).toFixed(0)}%
            </p>
          )}

          {detsFiltradas.map((det, i) => (
            <div
              key={det.id}
              className="flex justify-between items-center
                         border-b border-border/40 pb-1 last:border-0"
            >
              <span className="text-xs text-muted-foreground">#{i + 1}</span>
              <span
                className="text-xs font-medium px-1.5 py-0.5 rounded"
                style={{
                  background: colorPorClase(det.clase) + "22",
                  color: colorPorClase(det.clase),
                }}
              >
                {(det.confianza * 100).toFixed(0)}%
              </span>
            </div>
          ))}

          <div className="mt-auto pt-2 border-t">
            <Button
              size="sm"
              className="w-full"
              onClick={descargarJpg}
              disabled={descargando || !imagenActiva.procesada}
            >
              {descargando ? "Generando…" : "↓ Bajar JPG"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
