"use client";

import {
  BrainCircuit,
  Grid2x2,
  LayoutDashboard,
  Layers,
  MapPin,
  Plane,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/campos", label: "Campos", icon: MapPin },
  { href: "/modulos", label: "Módulos", icon: Layers },
  { href: "/vuelos", label: "Vuelos", icon: Plane },
  { href: "/modelos", label: "Modelos", icon: BrainCircuit },
  { href: "/converter", label: "Convertir TIFF", icon: Grid2x2 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-64 flex-col border-r bg-card md:flex">
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <Plane className="h-6 w-6 text-primary" />
        <span className="text-lg font-semibold">PlantVision IA</span>
      </div>
      <nav className="flex-1 space-y-1 p-4">
        {navItems.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
