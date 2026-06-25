"use client";

import L from "leaflet";
import { useEffect } from "react";
import { useMap } from "react-leaflet";

import type {
  DeteccionMapaProps,
  DeteccionOrigen,
  GeoFeatureCollection,
  RasterOverlay,
} from "@/types";

export interface EditorController {
  /** Persiste los cambios (POST/PUT/DELETE). Devuelve la cantidad de ops. */
  guardar: () => Promise<number>;
  /** Borra la caja seleccionada (marca para DELETE si ya existía). */
  borrarSeleccion: () => void;
  /** Quita la selección actual. */
  deseleccionar: () => void;
}

type Estado = "orig" | "new" | "edited";
type Corner = "nw" | "ne" | "sw" | "se";

interface MBox {
  key: string;
  id: number | null;
  imagen: number;
  origen: DeteccionOrigen;
  estado: Estado;
  borrada: boolean;
  bounds: L.LatLngBounds;
  rect: L.Rectangle;
  handles: L.Marker[];
}

const COLOR: Record<string, string> = {
  modelo: "#22c55e",
  manual: "#3b82f6",
  corregida: "#eab308",
};
const colorDe = (b: MBox) =>
  b.estado === "new" ? COLOR.manual : COLOR[b.origen] ?? COLOR.modelo;

let tmpId = 0;

interface Props {
  active: boolean;
  drawMode: boolean;
  features: GeoFeatureCollection<DeteccionMapaProps>["features"];
  overlays: RasterOverlay[];
  controllerRef: React.MutableRefObject<EditorController | null>;
  onChange: (info: { dirty: number; seleccion: boolean }) => void;
  onSaveOps: (ops: {
    crear: { imagen: number; geo: [number, number, number, number] }[];
    editar: { id: number; geo: [number, number, number, number] }[];
    borrar: number[];
  }) => Promise<number>;
}

function cornerLatLng(b: L.LatLngBounds, c: Corner): L.LatLng {
  const lat = c.includes("n") ? b.getNorth() : b.getSouth();
  const lng = c.includes("w") ? b.getWest() : b.getEast();
  return L.latLng(lat, lng);
}

function opuesto(c: Corner): Corner {
  return { nw: "se", se: "nw", ne: "sw", sw: "ne" }[c] as Corner;
}

const CORNERS: Corner[] = ["nw", "ne", "sw", "se"];

/**
 * Capa de edición de detecciones directamente sobre el mapa (ortofoto).
 * Dibuja/mueve/redimensiona/borra recuadros en coordenadas geográficas y los
 * persiste vía el backend (que convierte geo→píxel con el GeoTIFF).
 *
 * Es imperativo (maneja capas Leaflet a mano) para que el arrastre sea fluido;
 * sincroniza con React sólo al terminar cada gesto.
 */
export default function EditorMapaLayer({
  active,
  drawMode,
  features,
  overlays,
  controllerRef,
  onChange,
  onSaveOps,
}: Props) {
  const map = useMap();

  useEffect(() => {
    if (!active) return;

    const grupo = L.featureGroup().addTo(map);
    const model = new Map<string, MBox>();
    const drawModeRef = { current: drawMode };
    let seleccion: string | null = null;

    const emitir = () => {
      let dirty = 0;
      model.forEach((b) => {
        if (b.borrada || b.estado === "new" || b.estado === "edited") dirty++;
      });
      onChange({ dirty, seleccion: seleccion !== null });
    };

    const handleIcon = (color: string) =>
      L.divIcon({
        className: "",
        iconSize: [14, 14],
        iconAnchor: [7, 7],
        html: `<div style="width:14px;height:14px;background:${color};border:2px solid #fff;border-radius:3px;box-shadow:0 0 0 1px ${color}"></div>`,
      });

    const quitarHandles = (b: MBox) => {
      b.handles.forEach((h) => grupo.removeLayer(h));
      b.handles = [];
    };

    const reposicionarHandles = (b: MBox, omitir?: Corner) => {
      b.handles.forEach((h, i) => {
        const c = CORNERS[i];
        if (c === omitir) return;
        h.setLatLng(cornerLatLng(b.bounds, c));
      });
    };

    const crearHandles = (b: MBox) => {
      const color = colorDe(b);
      b.handles = CORNERS.map((c) => {
        const m = L.marker(cornerLatLng(b.bounds, c), {
          icon: handleIcon(color),
          draggable: true,
          keyboard: false,
        });
        let opp: L.LatLng | null = null;
        m.on("dragstart", () => {
          opp = cornerLatLng(b.bounds, opuesto(c));
          if (b.estado !== "new") b.estado = "edited";
        });
        m.on("drag", () => {
          if (!opp) return;
          b.bounds = L.latLngBounds(opp, m.getLatLng());
          b.rect.setBounds(b.bounds);
          reposicionarHandles(b, c);
        });
        m.on("dragend", emitir);
        m.addTo(grupo);
        return m;
      });
    };

    const seleccionar = (key: string | null) => {
      if (seleccion === key) return;
      const prev = seleccion ? model.get(seleccion) : null;
      if (prev) {
        quitarHandles(prev);
        prev.rect.setStyle({ weight: 2, fillOpacity: 0 });
      }
      seleccion = key;
      const b = key ? model.get(key) : null;
      if (b) {
        b.rect.setStyle({ weight: 3, fillOpacity: 0.15 });
        crearHandles(b);
      }
      emitir();
    };

    const iniciarMover = (b: MBox, ev: L.LeafletMouseEvent) => {
      if (drawModeRef.current) return;
      L.DomEvent.stop(ev.originalEvent);
      seleccionar(b.key);
      map.dragging.disable();
      const start = ev.latlng;
      const orig = b.bounds;
      const onMove = (e: L.LeafletMouseEvent) => {
        const dLat = e.latlng.lat - start.lat;
        const dLng = e.latlng.lng - start.lng;
        b.bounds = L.latLngBounds(
          [orig.getSouth() + dLat, orig.getWest() + dLng],
          [orig.getNorth() + dLat, orig.getEast() + dLng],
        );
        b.rect.setBounds(b.bounds);
        reposicionarHandles(b);
      };
      const onUp = () => {
        map.off("mousemove", onMove);
        map.off("mouseup", onUp);
        map.dragging.enable();
        if (b.estado !== "new") b.estado = "edited";
        emitir();
      };
      map.on("mousemove", onMove);
      map.on("mouseup", onUp);
    };

    const wireRect = (b: MBox) => {
      b.rect.on("mousedown", (e) => iniciarMover(b, e as L.LeafletMouseEvent));
    };

    // Cargar detecciones existentes (sólo las que tienen bbox geográfico).
    features.forEach((f) => {
      const bbox = f.properties.bbox;
      if (!bbox) return;
      const [w, s, e, n] = bbox;
      const id = typeof f.id === "number" ? f.id : Number(f.id);
      const b: MBox = {
        key: `d${id}`,
        id,
        imagen: f.properties.imagen,
        origen: f.properties.origen ?? "modelo",
        estado: "orig",
        borrada: false,
        bounds: L.latLngBounds([s, w], [n, e]),
        rect: L.rectangle(
          [
            [s, w],
            [n, e],
          ],
          { color: COLOR[f.properties.origen] ?? COLOR.modelo, weight: 2, fillOpacity: 0 },
        ),
        handles: [],
      };
      b.rect.addTo(grupo);
      wireRect(b);
      model.set(b.key, b);
    });

    // Resolver a qué imagen pertenece una caja nueva (overlay que la contiene).
    const imagenPara = (centro: L.LatLng): number | null => {
      for (const ov of overlays) {
        const ob = L.latLngBounds(ov.bounds);
        if (ob.contains(centro)) return ov.imagen_id;
      }
      return overlays.length > 0 ? overlays[0].imagen_id : null;
    };

    const finalizarDibujo = (rect: L.Rectangle) => {
      const bounds = rect.getBounds();
      const p1 = map.latLngToContainerPoint(bounds.getNorthWest());
      const p2 = map.latLngToContainerPoint(bounds.getSouthEast());
      if (Math.abs(p2.x - p1.x) < 6 || Math.abs(p2.y - p1.y) < 6) {
        grupo.removeLayer(rect);
        return;
      }
      const imagen = imagenPara(bounds.getCenter());
      if (imagen === null) {
        grupo.removeLayer(rect);
        return;
      }
      rect.setStyle({ color: COLOR.manual, weight: 2, fillOpacity: 0 });
      const b: MBox = {
        key: `n${tmpId++}`,
        id: null,
        imagen,
        origen: "manual",
        estado: "new",
        borrada: false,
        bounds,
        rect,
        handles: [],
      };
      wireRect(b);
      model.set(b.key, b);
      seleccionar(b.key);
    };

    // ── Modo dibujar caja nueva ──────────────────────────────────────────
    let temp: L.Rectangle | null = null;
    let start: L.LatLng | null = null;
    const onDrawMove = (e: L.LeafletMouseEvent) => {
      if (temp && start) temp.setBounds(L.latLngBounds(start, e.latlng));
    };
    const onDrawUp = () => {
      map.off("mousemove", onDrawMove);
      map.off("mouseup", onDrawUp);
      if (temp) finalizarDibujo(temp);
      temp = null;
      start = null;
      emitir();
    };
    const onDrawDown = (e: L.LeafletMouseEvent) => {
      start = e.latlng;
      temp = L.rectangle(L.latLngBounds(e.latlng, e.latlng), {
        color: COLOR.manual,
        weight: 2,
        dashArray: "4",
        fillOpacity: 0.1,
      }).addTo(grupo);
      map.on("mousemove", onDrawMove);
      map.on("mouseup", onDrawUp);
    };

    const aplicarDrawMode = (on: boolean) => {
      drawModeRef.current = on;
      if (on) {
        seleccionar(null);
        map.dragging.disable();
        map.getContainer().style.cursor = "crosshair";
        map.on("mousedown", onDrawDown);
      } else {
        map.off("mousedown", onDrawDown);
        map.dragging.enable();
        map.getContainer().style.cursor = "";
      }
    };
    aplicarDrawMode(drawMode);

    const onDrawModeEvent = (ev: L.LeafletEvent) => {
      aplicarDrawMode(Boolean((ev as L.LeafletEvent & { on?: boolean }).on));
    };
    map.on("editor:drawmode", onDrawModeEvent);

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") seleccionar(null);
      if ((e.key === "Delete" || e.key === "Backspace") && seleccion) {
        e.preventDefault();
        controllerRef.current?.borrarSeleccion();
      }
    };
    window.addEventListener("keydown", onKey);

    // ── Controlador expuesto al padre ────────────────────────────────────
    controllerRef.current = {
      deseleccionar: () => seleccionar(null),
      borrarSeleccion: () => {
        if (!seleccion) return;
        const b = model.get(seleccion);
        if (!b) return;
        quitarHandles(b);
        grupo.removeLayer(b.rect);
        if (b.id != null) {
          b.borrada = true;
        } else {
          model.delete(b.key);
        }
        seleccion = null;
        emitir();
      },
      guardar: async () => {
        const crear: { imagen: number; geo: [number, number, number, number] }[] =
          [];
        const editar: { id: number; geo: [number, number, number, number] }[] =
          [];
        const borrar: number[] = [];
        model.forEach((b) => {
          const geo: [number, number, number, number] = [
            b.bounds.getWest(),
            b.bounds.getSouth(),
            b.bounds.getEast(),
            b.bounds.getNorth(),
          ];
          if (b.borrada && b.id != null) borrar.push(b.id);
          else if (b.estado === "new") crear.push({ imagen: b.imagen, geo });
          else if (b.estado === "edited" && b.id != null)
            editar.push({ id: b.id, geo });
        });
        return onSaveOps({ crear, editar, borrar });
      },
    };

    emitir();

    return () => {
      window.removeEventListener("keydown", onKey);
      map.off("editor:drawmode", onDrawModeEvent);
      aplicarDrawMode(false);
      map.removeLayer(grupo);
      controllerRef.current = null;
    };
    // Re-inicializa la capa sólo al entrar/salir de edición.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Propagar cambios de drawMode sin re-inicializar la capa.
  useEffect(() => {
    if (!active) return;
    map.fire("editor:drawmode", { on: drawMode });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawMode, active]);

  return null;
}
