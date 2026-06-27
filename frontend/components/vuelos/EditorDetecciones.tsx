"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Plus, Save, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { deteccionesService } from "@/services/detecciones.service";
import api from "@/services/api";
import type { Deteccion, DeteccionOrigen, Imagen } from "@/types";

type EstadoBox = "orig" | "new" | "edited";

interface EditBox {
  key: string;
  id: number | null;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
  origen: DeteccionOrigen;
  estado: EstadoBox;
}

type Corner = "nw" | "ne" | "sw" | "se";

interface Gesture {
  type: "draw" | "move" | "resize";
  key: string;
  corner?: Corner;
  startX: number;
  startY: number;
  orig: { x_min: number; y_min: number; x_max: number; y_max: number };
}

const COLOR: Record<string, string> = {
  modelo: "#22c55e",
  manual: "#3b82f6",
  corregida: "#eab308",
};
const colorBox = (b: EditBox) =>
  b.estado === "new" ? COLOR.manual : COLOR[b.origen] ?? COLOR.modelo;

interface Props {
  imagen: Imagen;
  detecciones: Deteccion[];
  onClose: () => void;
}

let tmpId = 0;

export default function EditorDetecciones({
  imagen,
  detecciones,
  onClose,
}: Props) {
  const qc = useQueryClient();
  const overlayRef = useRef<HTMLDivElement>(null);
  const gesture = useRef<Gesture | null>(null);

  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [boxes, setBoxes] = useState<EditBox[]>([]);
  const [deleted, setDeleted] = useState<number[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [revisada, setRevisada] = useState(imagen.revisada);

  // Copia editable de las detecciones.
  useEffect(() => {
    setBoxes(
      detecciones.map((d) => ({
        key: `d${d.id}`,
        id: d.id,
        x_min: d.x_min,
        y_min: d.y_min,
        x_max: d.x_max,
        y_max: d.y_max,
        origen: d.origen,
        estado: "orig" as EstadoBox,
      })),
    );
    setDeleted([]);
  }, [detecciones]);

  // Cargar la imagen base (JPG directo / TIFF via /annotated/ sin cajas).
  useEffect(() => {
    let revoked: string | null = null;
    const esTiff = /\.(tif|tiff)$/i.test(imagen.nombre_original ?? "");

    // El JPG del TIFF puede venir decimado (ortofotos gigapíxel): las cajas se
    // guardan en píxeles nativos, así que el lienzo trabaja en coordenadas
    // nativas (dims = tamaño nativo = tamaño mostrado / escala).
    const cargar = (url: string, revoke: boolean, escala = 1) => {
      const img = new Image();
      if (!revoke) img.crossOrigin = "anonymous";
      img.onload = () => {
        setDims({
          w: Math.round(img.naturalWidth / escala),
          h: Math.round(img.naturalHeight / escala),
        });
        setImgUrl(url);
      };
      img.onerror = () => {
        if (revoke) URL.revokeObjectURL(url);
        toast.error("No se pudo cargar la imagen para editar.");
      };
      img.src = url;
      if (revoke) revoked = url;
    };

    if (esTiff) {
      api
        .get(`/imagenes/${imagen.id}/annotated/?min_confidence=1`, {
          responseType: "blob",
        })
        .then((res) => {
          const escala = parseFloat(res.headers["x-annotated-scale"]) || 1;
          cargar(URL.createObjectURL(res.data), true, escala);
        })
        .catch(() => toast.error("No se pudo cargar el TIFF para editar."));
    } else {
      cargar(imagen.archivo, false);
    }
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [imagen]);

  const toNatural = useCallback(
    (clientX: number, clientY: number) => {
      const el = overlayRef.current;
      if (!el || !dims) return { x: 0, y: 0 };
      const r = el.getBoundingClientRect();
      const fx = (clientX - r.left) / r.width;
      const fy = (clientY - r.top) / r.height;
      return {
        x: Math.min(Math.max(fx * dims.w, 0), dims.w),
        y: Math.min(Math.max(fy * dims.h, 0), dims.h),
      };
    },
    [dims],
  );

  // ── Gestos globales (move / up) ──────────────────────────────────────────
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const g = gesture.current;
      if (!g || !dims) return;
      const { x, y } = toNatural(e.clientX, e.clientY);
      setBoxes((prev) =>
        prev.map((b) => {
          if (b.key !== g.key) return b;
          const estado: EstadoBox = b.estado === "new" ? "new" : "edited";
          if (g.type === "move") {
            const dx = x - g.startX;
            const dy = y - g.startY;
            let nx = g.orig.x_min + dx;
            let ny = g.orig.y_min + dy;
            const w = g.orig.x_max - g.orig.x_min;
            const h = g.orig.y_max - g.orig.y_min;
            nx = Math.min(Math.max(nx, 0), dims.w - w);
            ny = Math.min(Math.max(ny, 0), dims.h - h);
            return { ...b, x_min: nx, y_min: ny, x_max: nx + w, y_max: ny + h, estado };
          }
          // draw / resize: mover una esquina
          const corner = g.corner ?? "se";
          let { x_min, y_min, x_max, y_max } = g.orig;
          if (corner.includes("w")) x_min = x;
          else x_max = x;
          if (corner.includes("n")) y_min = y;
          else y_max = y;
          return {
            ...b,
            x_min: Math.min(x_min, x_max),
            x_max: Math.max(x_min, x_max),
            y_min: Math.min(y_min, y_max),
            y_max: Math.max(y_min, y_max),
            estado,
          };
        }),
      );
    };

    const onUp = () => {
      const g = gesture.current;
      gesture.current = null;
      if (!g) return;
      // Descartar cajas nuevas demasiado chicas.
      if (g.type === "draw") {
        setBoxes((prev) =>
          prev.filter(
            (b) =>
              b.key !== g.key ||
              (b.x_max - b.x_min > 4 && b.y_max - b.y_min > 4),
          ),
        );
      }
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dims, toNatural]);

  // ── Iniciar dibujo de caja nueva sobre el fondo ──────────────────────────
  const onBackgroundDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const { x, y } = toNatural(e.clientX, e.clientY);
    const key = `n${tmpId++}`;
    const nuevo: EditBox = {
      key,
      id: null,
      x_min: x,
      y_min: y,
      x_max: x,
      y_max: y,
      origen: "manual",
      estado: "new",
    };
    setBoxes((prev) => [...prev, nuevo]);
    setSelected(key);
    gesture.current = {
      type: "draw",
      key,
      corner: "se",
      startX: x,
      startY: y,
      orig: { x_min: x, y_min: y, x_max: x, y_max: y },
    };
  };

  const onBoxDown = (e: React.PointerEvent, b: EditBox) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    setSelected(b.key);
    const { x, y } = toNatural(e.clientX, e.clientY);
    gesture.current = {
      type: "move",
      key: b.key,
      startX: x,
      startY: y,
      orig: { x_min: b.x_min, y_min: b.y_min, x_max: b.x_max, y_max: b.y_max },
    };
  };

  const onHandleDown = (e: React.PointerEvent, b: EditBox, corner: Corner) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    setSelected(b.key);
    const { x, y } = toNatural(e.clientX, e.clientY);
    gesture.current = {
      type: "resize",
      key: b.key,
      corner,
      startX: x,
      startY: y,
      orig: { x_min: b.x_min, y_min: b.y_min, x_max: b.x_max, y_max: b.y_max },
    };
  };

  const eliminarSeleccionada = useCallback(() => {
    if (!selected) return;
    setBoxes((prev) => {
      const b = prev.find((x) => x.key === selected);
      if (b?.id != null) setDeleted((d) => [...d, b.id as number]);
      return prev.filter((x) => x.key !== selected);
    });
    setSelected(null);
  }, [selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "Delete" || e.key === "Backspace") && selected) {
        e.preventDefault();
        eliminarSeleccionada();
      }
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, eliminarSeleccionada]);

  const guardar = async () => {
    setGuardando(true);
    try {
      const nuevos = boxes.filter((b) => b.estado === "new");
      const editados = boxes.filter(
        (b) => b.estado === "edited" && b.id != null,
      );
      const ops: Promise<unknown>[] = [];
      for (const b of nuevos) {
        ops.push(
          deteccionesService.create(imagen.id, {
            x_min: b.x_min,
            y_min: b.y_min,
            x_max: b.x_max,
            y_max: b.y_max,
          }),
        );
      }
      for (const b of editados) {
        ops.push(
          deteccionesService.update(b.id as number, {
            x_min: b.x_min,
            y_min: b.y_min,
            x_max: b.x_max,
            y_max: b.y_max,
          }),
        );
      }
      for (const id of deleted) ops.push(deteccionesService.remove(id));

      const total = ops.length;
      if (total === 0) {
        toast.info("No hay cambios para guardar.");
        setGuardando(false);
        return;
      }
      await Promise.all(ops);
      toast.success(`${total} corrección(es) guardada(s)`, {
        description: "Se actualizó el conteo y el contador de reentrenamiento.",
      });
      qc.invalidateQueries({ queryKey: ["detecciones", imagen.id] });
      qc.invalidateQueries({ queryKey: ["vuelo"] });
      qc.invalidateQueries({ queryKey: ["vuelo-imagenes"] });
      qc.invalidateQueries({ queryKey: ["reentrenamiento"] });
      onClose();
    } catch {
      toast.error("No se pudieron guardar las correcciones.");
    } finally {
      setGuardando(false);
    }
  };

  const toggleRevisada = async () => {
    try {
      const next = !revisada;
      await deteccionesService.marcarRevisada(imagen.id, next);
      setRevisada(next);
      toast.success(next ? "Imagen marcada como revisada" : "Marca quitada");
      qc.invalidateQueries({ queryKey: ["vuelo-imagenes"] });
      qc.invalidateQueries({ queryKey: ["reentrenamiento"] });
    } catch {
      toast.error("No se pudo actualizar el estado de revisión.");
    }
  };

  const cambios =
    boxes.filter((b) => b.estado !== "orig").length + deleted.length;

  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b bg-muted/40">
        <span className="text-sm font-medium">Editor de detecciones</span>
        <Badge variant="secondary">{boxes.length} cajas</Badge>
        {cambios > 0 && (
          <Badge className="bg-amber-500 hover:bg-amber-500">
            {cambios} cambio(s)
          </Badge>
        )}
        <span className="text-xs text-muted-foreground ml-2 hidden sm:inline">
          Arrastrá en vacío para crear · clic para seleccionar · esquinas para
          redimensionar · Supr para borrar
        </span>
        <div className="flex items-center gap-2 ml-auto">
          <Button
            size="sm"
            variant="outline"
            onClick={eliminarSeleccionada}
            disabled={!selected}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Eliminar
          </Button>
          <Button
            size="sm"
            variant={revisada ? "default" : "outline"}
            onClick={toggleRevisada}
          >
            <Check className="mr-1 h-4 w-4" />
            {revisada ? "Revisada" : "Marcar revisada"}
          </Button>
          <Button size="sm" onClick={guardar} disabled={guardando}>
            {guardando ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-1 h-4 w-4" />
            )}
            Guardar
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose}>
            <X className="mr-1 h-4 w-4" />
            Cerrar
          </Button>
        </div>
      </div>

      <div className="p-3">
        <div className="relative bg-black rounded overflow-hidden select-none">
          {!imgUrl && (
            <div className="flex h-64 items-center justify-center text-xs text-white/60">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Cargando imagen…
            </div>
          )}
          {imgUrl && dims && (
            // eslint-disable-next-line jsx-a11y/no-static-element-interactions
            <div
              ref={overlayRef}
              className="relative w-full touch-none"
              style={{ aspectRatio: `${dims.w} / ${dims.h}` }}
              onPointerDown={onBackgroundDown}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imgUrl}
                alt={imagen.nombre_original}
                className="absolute inset-0 h-full w-full object-contain pointer-events-none"
                draggable={false}
              />
              {boxes.map((b) => {
                const color = colorBox(b);
                const sel = b.key === selected;
                const left = (b.x_min / dims.w) * 100;
                const top = (b.y_min / dims.h) * 100;
                const w = ((b.x_max - b.x_min) / dims.w) * 100;
                const h = ((b.y_max - b.y_min) / dims.h) * 100;
                return (
                  <div
                    key={b.key}
                    onPointerDown={(e) => onBoxDown(e, b)}
                    className="absolute cursor-move"
                    style={{
                      left: `${left}%`,
                      top: `${top}%`,
                      width: `${w}%`,
                      height: `${h}%`,
                      border: `2px solid ${color}`,
                      background: sel ? `${color}22` : "transparent",
                      boxShadow: sel ? `0 0 0 1px ${color}` : "none",
                    }}
                  >
                    {sel &&
                      (["nw", "ne", "sw", "se"] as Corner[]).map((c) => (
                        <div
                          key={c}
                          onPointerDown={(e) => onHandleDown(e, b, c)}
                          className="absolute h-3 w-3 rounded-sm border border-white"
                          style={{
                            background: color,
                            cursor: `${c}-resize`,
                            left: c.includes("w") ? -6 : undefined,
                            right: c.includes("e") ? -6 : undefined,
                            top: c.includes("n") ? -6 : undefined,
                            bottom: c.includes("s") ? -6 : undefined,
                          }}
                        />
                      ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ background: COLOR.modelo }}
            />
            modelo
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ background: COLOR.manual }}
            />
            manual / nueva
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ background: COLOR.corregida }}
            />
            corregida
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-7"
            onClick={() => setSelected(null)}
          >
            <Plus className="mr-1 h-3 w-3 rotate-45" />
            Deseleccionar
          </Button>
        </div>
      </div>
    </div>
  );
}
