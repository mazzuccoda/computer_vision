"use client";

import L from "leaflet";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";

import "leaflet/dist/leaflet.css";

// Fix del ícono default de Leaflet (igual que en MapaGeneral).
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

interface Props {
  latitud: number | null;
  longitud: number | null;
  onPick: (lat: number, lon: number) => void;
}

const FALLBACK: [number, number] = [-26.8083, -65.2176]; // Tucumán

function ClickHandler({ onPick }: { onPick: Props["onPick"] }) {
  useMapEvents({
    click(e) {
      onPick(
        Number(e.latlng.lat.toFixed(6)),
        Number(e.latlng.lng.toFixed(6))
      );
    },
  });
  return null;
}

export default function MapaPicker({ latitud, longitud, onPick }: Props) {
  const tienenPunto = latitud !== null && longitud !== null;
  const centro: [number, number] = tienenPunto
    ? [latitud as number, longitud as number]
    : FALLBACK;

  return (
    <MapContainer
      center={centro}
      zoom={tienenPunto ? 13 : 5}
      scrollWheelZoom
      style={{ height: "240px", width: "100%", borderRadius: "0.5rem" }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />
      <ClickHandler onPick={onPick} />
      {tienenPunto && (
        <Marker position={[latitud as number, longitud as number]} />
      )}
    </MapContainer>
  );
}
