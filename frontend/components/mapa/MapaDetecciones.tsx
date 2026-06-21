"use client";

import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { useEffect, useState } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import "leaflet.markercluster";

import { Slider } from "@/components/ui/slider";
import api from "@/services/api";
import type { DeteccionMapaProps, GeoFeatureCollection } from "@/types";

interface Props {
  vueloId: number;
}

const COLOR_POR_CLASE: Record<string, string> = {
  planta: "#22c55e",
  maleza: "#ef4444",
  faltante: "#eab308",
};

function colorClase(clase: string): string {
  return COLOR_POR_CLASE[clase] ?? COLOR_POR_CLASE.planta;
}

/**
 * Agrega las detecciones como CircleMarkers dentro de un markerClusterGroup
 * (agrupa plantas cercanas para no saturar el mapa en zoom alejado).
 */
function ClusterDetecciones({
  features,
}: {
  features: GeoFeatureCollection<DeteccionMapaProps>["features"];
}) {
  const map = useMap();

  useEffect(() => {
    if (features.length === 0) return;

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

    const bounds = L.latLngBounds(
      features.map((d) => [
        d.geometry.coordinates[1],
        d.geometry.coordinates[0],
      ])
    );
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 20 });
    }

    return () => {
      map.removeLayer(cluster);
    };
  }, [map, features]);

  return null;
}

export default function MapaDetecciones({ vueloId }: Props) {
  const [minConfianza, setMinConfianza] = useState(0.5);

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

  const features = data?.features ?? [];

  if (isLoading) {
    return <div className="h-[600px] animate-pulse rounded-lg bg-muted" />;
  }

  if (features.length === 0) {
    return (
      <div className="space-y-3">
        <FiltroConfianza
          minConfianza={minConfianza}
          setMinConfianza={setMinConfianza}
          total={0}
        />
        <div className="flex h-[300px] items-center justify-center rounded-lg border p-6 text-center text-sm text-muted-foreground">
          Este vuelo no tiene detecciones georreferenciadas todavía. Verificá
          que las imágenes provienen de un GeoTIFF procesado con el módulo
          Convertir TIFF (necesario para tener coordenadas geográficas).
        </div>
      </div>
    );
  }

  const centro: [number, number] = [
    features[0].geometry.coordinates[1],
    features[0].geometry.coordinates[0],
  ];

  return (
    <div className="space-y-3">
      <FiltroConfianza
        minConfianza={minConfianza}
        setMinConfianza={setMinConfianza}
        total={features.length}
      />
      <MapContainer
        center={centro}
        zoom={18}
        scrollWheelZoom
        style={{ height: "600px", width: "100%", borderRadius: "0.5rem" }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
          maxZoom={22}
          maxNativeZoom={19}
        />
        <ClusterDetecciones features={features} />
      </MapContainer>
    </div>
  );
}

function FiltroConfianza({
  minConfianza,
  setMinConfianza,
  total,
}: {
  minConfianza: number;
  setMinConfianza: (v: number) => void;
  total: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
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
      <span className="text-sm text-muted-foreground">
        {total} {total === 1 ? "planta" : "plantas"} en el mapa
      </span>
    </div>
  );
}
