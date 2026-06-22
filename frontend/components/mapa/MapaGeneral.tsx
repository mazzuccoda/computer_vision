"use client";

import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import Link from "next/link";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import { useEffect } from "react";

import "leaflet/dist/leaflet.css";

import api from "@/services/api";
import type { MapaGeneralResponse } from "@/types";

// Fix del ícono default de Leaflet roto en bundlers modernos (sin esto los
// pines no se ven con webpack/Next).
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })
  ._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

const ICONO_CAMPO = new L.Icon({
  iconUrl:
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [0, -38],
  className: "hue-rotate-[120deg]",
});

const FALLBACK_CENTRO: [number, number] = [-26.8083, -65.2176]; // Tucumán

function AjustarVista({ puntos }: { puntos: Array<[number, number]> }) {
  const map = useMap();
  useEffect(() => {
    if (puntos.length === 1) {
      map.setView(puntos[0], 13);
    } else if (puntos.length > 1) {
      map.fitBounds(L.latLngBounds(puntos), { padding: [40, 40] });
    }
  }, [map, puntos]);
  return null;
}

export default function MapaGeneral() {
  const { data, isLoading } = useQuery<MapaGeneralResponse>({
    queryKey: ["mapa-general"],
    queryFn: () => api.get("/mapa/campos-y-vuelos/").then((r) => r.data),
  });

  if (isLoading) {
    return <div className="h-[600px] animate-pulse rounded-lg bg-muted" />;
  }

  const campos = data?.campos.features ?? [];
  const vuelos = data?.vuelos.features ?? [];

  // [lat, lon] para Leaflet a partir de [lon, lat] de GeoJSON.
  const puntos: Array<[number, number]> = [
    ...campos.map(
      (c) =>
        [c.geometry.coordinates[1], c.geometry.coordinates[0]] as [
          number,
          number,
        ]
    ),
    ...vuelos.map(
      (v) =>
        [v.geometry.coordinates[1], v.geometry.coordinates[0]] as [
          number,
          number,
        ]
    ),
  ];

  const centro = puntos.length > 0 ? puntos[0] : FALLBACK_CENTRO;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
        <span className="flex items-center gap-2">
          <span className="inline-block h-3 w-3 rounded-full bg-emerald-500" />
          {campos.length} campos
        </span>
        <span className="flex items-center gap-2">
          <span className="inline-block h-3 w-3 rounded-full bg-blue-500" />
          {vuelos.length} vuelos georreferenciados
        </span>
      </div>

      <MapContainer
        center={centro}
        zoom={puntos.length > 0 ? 10 : 6}
        scrollWheelZoom
        style={{ height: "600px", width: "100%", borderRadius: "0.5rem" }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
        <AjustarVista puntos={puntos} />

        {campos.map((campo) => (
          <Marker
            key={`campo-${campo.id}`}
            position={[
              campo.geometry.coordinates[1],
              campo.geometry.coordinates[0],
            ]}
            icon={ICONO_CAMPO}
          >
            <Popup>
              <strong>{campo.properties.nombre}</strong>
              {campo.properties.ubicacion ? (
                <>
                  <br />
                  {campo.properties.ubicacion}
                </>
              ) : null}
              <br />
              <Link
                href={`/campos/${campo.id}`}
                className="text-blue-600 underline"
              >
                Ver campo
              </Link>
            </Popup>
          </Marker>
        ))}

        {vuelos.map((vuelo) => (
          <Marker
            key={`vuelo-${vuelo.id}`}
            position={[
              vuelo.geometry.coordinates[1],
              vuelo.geometry.coordinates[0],
            ]}
          >
            <Popup>
              <strong>{vuelo.properties.nombre}</strong>
              <br />
              Estado: {vuelo.properties.estado}
              <br />
              Plantas: {vuelo.properties.total_plantas}
              <br />
              <Link
                href={`/vuelos/${vuelo.id}`}
                className="text-blue-600 underline"
              >
                Ver vuelo
              </Link>
              {" · "}
              <Link
                href={`/vuelos/${vuelo.id}/mapa`}
                className="text-blue-600 underline"
              >
                Ver detecciones
              </Link>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
