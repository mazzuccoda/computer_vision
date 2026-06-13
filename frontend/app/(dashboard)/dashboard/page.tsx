"use client";

import { Layers, Leaf, MapPin, Plane } from "lucide-react";

import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDashboardStats } from "@/hooks/useDashboard";

export default function DashboardPage() {
  const { data, isLoading } = useDashboardStats();

  if (isLoading) return <LoadingSpinner />;

  const stats = [
    {
      label: "Campos",
      value: data?.total_campos ?? 0,
      icon: MapPin,
    },
    {
      label: "Módulos",
      value: data?.total_modulos ?? 0,
      icon: Layers,
    },
    {
      label: "Vuelos",
      value: data?.total_vuelos ?? 0,
      icon: Plane,
    },
    {
      label: "Plantas detectadas",
      value: data?.total_plantas ?? 0,
      icon: Leaf,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">
          Resumen general del sistema de detección.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {s.label}
                </CardTitle>
                <Icon className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{s.value}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Vuelos procesados hoy</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">
              {data?.vuelos_procesados_hoy ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Vuelos en procesamiento
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-blue-600">
              {data?.vuelos_procesando ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
