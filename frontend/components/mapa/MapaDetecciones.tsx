"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import L from "leaflet";
import { Loader2, Pencil, Save, Square, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import { toast } from "sonner";

import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import "leaflet.markercluster";

import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import api from "@/services/api";
import { deteccionesService } from "@/services/detecciones.service";
import type {
  DeteccionMapaProps,
  GeoFeatureCollection,
  RasterOverlay,
  RasterOverlayResponse,
} from "@/types";

import EditorMapaLayer, { type EditorController } from "./EditorMapaLayer";

interface Props {
  vueloId: number;
}

type Vista = "cluster" | "cajas";

const COLOR_POR_CLASE: Record<string, string> = {
  planta: "#22c55e",
  maleza: "#ef4444",
  faltante: "#eab308",
};

function colorClase(clase: string): string {
  return COLOR_POR_CLASE[clase] ?? COLOR_POR_CLASE.planta;
}

// Zoom máximo de overzoom permitido en el mapa: por encima del maxNativeZoom de
// la ortofoto, Leaflet sobre-escala los tiles nativos (siguen más nítidos que
// el JPG único anterior).
const MAX_ZOOM = 24;

/**
 * Capa de tiles XYZ que pide cada tile autenticado (JWT) vía axios y lo entrega
 * a Leaflet como objectURL. Necesario porque la API exige Authorization y un
 * `L.tileLayer` normal hace requests <img> sin cabeceras.
 */
const TileLayerAutenticada = L.GridLayer.extend({
  createTile(coords: L.Coords, done: L.DoneCallback) {
    const tile = document.createElement("img");
    tile.setAttribute("role", "presentation");
    const imagenId = (this.options as { imagenId: number }).imagenId;
    const { z, x, y } = coords;

    api
      .get(`/imagenes/${imagenId}/tiles/${z}/${x}/${y}.png`, {
        responseType: "blob",
        validateStatus: (s) => s === 200 || s === 204,
      })
      .then((res) => {
        // 204 = tile fuera de la ortofoto: se deja transparente.
        if (res.status === 204 || !res.data || res.data.size === 0) {
          done(undefined, tile);
          return;
        }
        const url = URL.createObjectURL(res.data);
        tile.onload = () => {
          URL.revokeObjectURL(url);
          done(undefined, tile);
        };
        tile.onerror = () => {
          URL.revokeObjectURL(url);
          done(undefined, tile);
        };
        tile.src = url;
      })
      .catch(() => {
        done(undefined, tile);
      });

    return tile;
  },
}) as unknown as new (options: L.GridLayerOptions & {
  imagenId: number;
}) => L.GridLayer;

/**
 * Superpone la(s) ortofoto(s) del GeoTIFF como capa de tiles XYZ leídos a
 * resolución nativa del raster. A diferencia del imageOverlay anterior (un JPG
 * estirado y borroso al hacer zoom), cada nivel de zoom carga sólo la ventana
 * visible a su detalle nativo, así se ven las plantas para marcarlas a mano.
 */
function OrtofotoLayer({
  overlays,
  visible,
}: {
  overlays: RasterOverlay[];
  visible: boolean;
}) {
  const map = useMap();

  useEffect(() => {
    if (!visible) return;
    const capas = overlays.map((ov) => {
      const bounds = L.latLngBounds(ov.bounds);
      const capa = new TileLayerAutenticada({
        imagenId: ov.imagen_id,
        bounds,
        tileSize: 256,
        minNativeZoom: 0,
        maxNativeZoom: ov.max_native_zoom ?? 22,
        maxZoom: MAX_ZOOM,
        noWrap: true,
        pane: "tilePane",
      });
      capa.addTo(map);
      return capa;
    });

    return () => {
      capas.forEach((c) => map.removeLayer(c));
    };
  }, [map, overlays, visible]);

  return null;
}

/** Agrupa detecciones cercanas en clusters (vista alejada). */
function ClusterLayer({
  features,
  visible,
}: {
  features: GeoFeatureCollection<DeteccionMapaProps>["features"];
  visible: boolean;
}) {
  const map = useMap();

  useEffect(() => {
    if (!visible || features.length === 0) return;

    const cluster = L.markerClusterGroup({
      maxClusterRadius: 45,
      showCoverageOnHover: false,
    });

    features.forEach((det) => {
      const [lon, lat] = det.geometry.coordinates;
      const color = colorClase(det.properties.clase);
      const marker = L.circleMarker([lat, lon], {
        radius: 6,
        color,
        fillColor: color,
        fillOpacity: 0.8,
        weight: 1.5,
      });
      marker.bindPopup(
        `${det.properties.clase} — ${(det.properties.confianza * 100).toFixed(0)}%`
      );
      cluster.addLayer(marker);
    });

    map.addLayer(cluster);
    return () => {
      map.removeLayer(cluster);
    };
  }, [map, features, visible]);

  return null;
}

/** Dibuja un recuadro por detección sobre la ortofoto (vista de detalle). */
function CajasLayer({
  features,
  visible,
}: {
  features: GeoFeatureCollection<DeteccionMapaProps>["features"];
  visible: boolean;
}) {
  const map = useMap();

  useEffect(() => {
    if (!visible || features.length === 0) return;

    const grupo = L.layerGroup();
    features.forEach((det) => {
      const bbox = det.properties.bbox;
      const color = colorClase(det.properties.clase);
      let capa: L.Layer;
      if (bbox) {
        const [w, s, e, n] = bbox;
        capa = L.rectangle(
          [
            [s, w],
            [n, e],
          ],
          { color, weight: 2, fill: false }
        );
      } else {
        // sin bbox geográfico: fallback a un punto
        const [lon, lat] = det.geometry.coordinates;
        capa = L.circleMarker([lat, lon], {
          radius: 5,
          color,
          fillColor: color,
          fillOpacity: 0.8,
          weight: 1.5,
        });
      }
      capa.bindPopup(
        `${det.properties.clase} — ${(det.properties.confianza * 100).toFixed(0)}%`
      );
      grupo.addLayer(capa);
    });

    grupo.addTo(map);
    return () => {
      map.removeLayer(grupo);
    };
  }, [map, features, visible]);

  return null;
}

/** Ajusta el encuadre a la ortofoto si existe, si no a las detecciones. */
function FitBounds({
  overlays,
  features,
}: {
  overlays: RasterOverlay[];
  features: GeoFeatureCollection<DeteccionMapaProps>["features"];
}) {
  const map = useMap();
  const hecho = useRef(false);

  useEffect(() => {
    if (hecho.current) return;

    let bounds: L.LatLngBounds | null = null;
    if (overlays.length > 0) {
      bounds = L.latLngBounds(overlays[0].bounds);
      overlays.slice(1).forEach((ov) => bounds!.extend(ov.bounds));
    } else if (features.length > 0) {
      bounds = L.latLngBounds(
        features.map((d) => [
          d.geometry.coordinates[1],
          d.geometry.coordinates[0],
        ])
      );
    }

    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 20 });
      hecho.current = true;
    }
  }, [map, overlays, features]);

  return null;
}

export default function MapaDetecciones({ vueloId }: Props) {
  const qc = useQueryClient();
  const [minConfianza, setMinConfianza] = useState(0.5);
  const [vista, setVista] = useState<Vista>("cajas");
  const [mostrarOrto, setMostrarOrto] = useState(true);

  const [editMode, setEditMode] = useState(false);
  const [drawMode, setDrawMode] = useState(false);
  const [editInfo, setEditInfo] = useState({ dirty: 0, seleccion: false });
  const [guardando, setGuardando] = useState(false);
  const controllerRef = useRef<EditorController | null>(null);

  const { data, isLoading } = useQuery<
    GeoFeatureCollection<DeteccionMapaProps>
  >({
    queryKey: ["detecciones-mapa", vueloId, minConfianza],
    queryFn: () =>
      api
        .get(
          `/vuelos/${vueloId}/detecciones-mapa/?min_confidence=${minConfianza}`
        )
        .then((r) => r.data),
  });

  const { data: overlayData } = useQuery<RasterOverlayResponse>({
    queryKey: ["raster-overlay", vueloId],
    queryFn: () =>
      api.get(`/vuelos/${vueloId}/raster-overlay/`).then((r) => r.data),
  });

  const features = data?.features ?? [];
  const overlays = overlayData?.overlays ?? [];
  const hayOrto = overlays.length > 0;

  const onSaveOps: React.ComponentProps<
    typeof EditorMapaLayer
  >["onSaveOps"] = async ({ crear, editar, borrar }) => {
    const ops: Promise<unknown>[] = [];
    crear.forEach((c) => ops.push(deteccionesService.createGeo(c.imagen, c.geo)));
    editar.forEach((e) => ops.push(deteccionesService.updateGeo(e.id, e.geo)));
    borrar.forEach((id) => ops.push(deteccionesService.remove(id)));
    if (ops.length === 0) {
      toast.info("No hay cambios para guardar.");
      return 0;
    }
    await Promise.all(ops);
    toast.success(`${ops.length} corrección(es) guardada(s)`, {
      description: "Se actualizó el conteo y el contador de reentrenamiento.",
    });
    qc.invalidateQueries({ queryKey: ["detecciones-mapa", vueloId] });
    qc.invalidateQueries({ queryKey: ["raster-overlay", vueloId] });
    qc.invalidateQueries({ queryKey: ["reentrenamiento"] });
    qc.invalidateQueries({ queryKey: ["vuelo"] });
    return ops.length;
  };

  const guardar = async () => {
    if (!controllerRef.current) return;
    setGuardando(true);
    try {
      const n = await controllerRef.current.guardar();
      if (n > 0) {
        setEditMode(false);
        setDrawMode(false);
      }
    } catch {
      toast.error("No se pudieron guardar las correcciones.");
    } finally {
      setGuardando(false);
    }
  };

  const cerrarEdicion = () => {
    setEditMode(false);
    setDrawMode(false);
  };

  if (isLoading) {
    return <div className="h-[600px] animate-pulse rounded-lg bg-muted" />;
  }

  if (features.length === 0 && !hayOrto) {
    return (
      <div className="space-y-3">
        <Controles
          minConfianza={minConfianza}
          setMinConfianza={setMinConfianza}
          vista={vista}
          setVista={setVista}
          mostrarOrto={mostrarOrto}
          setMostrarOrto={setMostrarOrto}
          hayOrto={false}
          total={0}
          puedeEditar={false}
          onEditar={() => {}}
        />
        <div className="flex h-[300px] items-center justify-center rounded-lg border p-6 text-center text-sm text-muted-foreground">
          Este vuelo no tiene detecciones georreferenciadas todavía. Verificá
          que las imágenes provienen de un GeoTIFF con coordenadas (CRS), o
          volvé a procesar el vuelo para recalcular la georreferenciación.
        </div>
      </div>
    );
  }

  let centro: [number, number];
  if (features.length > 0) {
    centro = [
      features[0].geometry.coordinates[1],
      features[0].geometry.coordinates[0],
    ];
  } else {
    const c = L.latLngBounds(overlays[0].bounds).getCenter();
    centro = [c.lat, c.lng];
  }

  return (
    <div className="space-y-3">
      {editMode ? (
        <BarraEdicion
          drawMode={drawMode}
          setDrawMode={setDrawMode}
          dirty={editInfo.dirty}
          seleccion={editInfo.seleccion}
          guardando={guardando}
          onBorrar={() => controllerRef.current?.borrarSeleccion()}
          onGuardar={guardar}
          onCerrar={cerrarEdicion}
        />
      ) : (
        <Controles
          minConfianza={minConfianza}
          setMinConfianza={setMinConfianza}
          vista={vista}
          setVista={setVista}
          mostrarOrto={mostrarOrto}
          setMostrarOrto={setMostrarOrto}
          hayOrto={hayOrto}
          total={features.length}
          puedeEditar={hayOrto}
          onEditar={() => setEditMode(true)}
        />
      )}
      <MapContainer
        center={centro}
        zoom={18}
        maxZoom={MAX_ZOOM}
        scrollWheelZoom
        style={{ height: "600px", width: "100%", borderRadius: "0.5rem" }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
          maxZoom={MAX_ZOOM}
          maxNativeZoom={19}
        />
        <OrtofotoLayer overlays={overlays} visible={mostrarOrto || editMode} />
        <ClusterLayer
          features={features}
          visible={!editMode && vista === "cluster"}
        />
        <CajasLayer
          features={features}
          visible={!editMode && vista === "cajas"}
        />
        {editMode && (
          <EditorMapaLayer
            active={editMode}
            drawMode={drawMode}
            features={features}
            overlays={overlays}
            controllerRef={controllerRef}
            onChange={setEditInfo}
            onSaveOps={onSaveOps}
          />
        )}
        <FitBounds overlays={overlays} features={features} />
      </MapContainer>
    </div>
  );
}

function BarraEdicion({
  drawMode,
  setDrawMode,
  dirty,
  seleccion,
  guardando,
  onBorrar,
  onGuardar,
  onCerrar,
}: {
  drawMode: boolean;
  setDrawMode: (v: boolean) => void;
  dirty: number;
  seleccion: boolean;
  guardando: boolean;
  onBorrar: () => void;
  onGuardar: () => void;
  onCerrar: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
      <span className="text-sm font-medium">Editor sobre el mapa</span>
      {dirty > 0 && (
        <Badge className="bg-amber-500 hover:bg-amber-500">
          {dirty} cambio(s)
        </Badge>
      )}
      <span className="ml-2 hidden text-xs text-muted-foreground sm:inline">
        Activá “Dibujar” y arrastrá sobre la ortofoto · clic para
        seleccionar/mover · esquinas para redimensionar · Supr para borrar
      </span>
      <div className="ml-auto flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant={drawMode ? "default" : "outline"}
          onClick={() => setDrawMode(!drawMode)}
        >
          <Square className="mr-1 h-4 w-4" />
          {drawMode ? "Dibujando…" : "Dibujar"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onBorrar}
          disabled={!seleccion}
        >
          <Trash2 className="mr-1 h-4 w-4" />
          Eliminar
        </Button>
        <Button size="sm" onClick={onGuardar} disabled={guardando}>
          {guardando ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-1 h-4 w-4" />
          )}
          Guardar
        </Button>
        <Button size="sm" variant="ghost" onClick={onCerrar}>
          <X className="mr-1 h-4 w-4" />
          Cerrar
        </Button>
      </div>
    </div>
  );
}

function Controles({
  minConfianza,
  setMinConfianza,
  vista,
  setVista,
  mostrarOrto,
  setMostrarOrto,
  hayOrto,
  total,
  puedeEditar,
  onEditar,
}: {
  minConfianza: number;
  setMinConfianza: (v: number) => void;
  vista: Vista;
  setVista: (v: Vista) => void;
  mostrarOrto: boolean;
  setMostrarOrto: (v: boolean) => void;
  hayOrto: boolean;
  total: number;
  puedeEditar: boolean;
  onEditar: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex items-center gap-1 rounded-md border p-0.5">
        <Button
          type="button"
          size="sm"
          variant={vista === "cajas" ? "default" : "ghost"}
          onClick={() => setVista("cajas")}
        >
          Cajas
        </Button>
        <Button
          type="button"
          size="sm"
          variant={vista === "cluster" ? "default" : "ghost"}
          onClick={() => setVista("cluster")}
        >
          Cluster
        </Button>
      </div>

      <label
        className={`flex items-center gap-2 text-sm ${
          hayOrto ? "" : "opacity-50"
        }`}
      >
        <Switch
          checked={mostrarOrto && hayOrto}
          onCheckedChange={setMostrarOrto}
          disabled={!hayOrto}
        />
        Ortofoto
      </label>

      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">
          Umbral: {(minConfianza * 100).toFixed(0)}%
        </span>
        <Slider
          value={[Math.round(minConfianza * 100)]}
          onValueChange={([v]) => setMinConfianza(v / 100)}
          min={10}
          max={95}
          step={5}
          className="w-40"
        />
      </div>

      <span className="text-sm text-muted-foreground">
        {total} {total === 1 ? "planta" : "plantas"} en el mapa
      </span>

      {puedeEditar && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="ml-auto"
          onClick={onEditar}
        >
          <Pencil className="mr-1 h-4 w-4" />
          Editar en el mapa
        </Button>
      )}
    </div>
  );
}
