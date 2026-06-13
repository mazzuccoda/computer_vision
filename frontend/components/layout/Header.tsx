"use client";

import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

export function Header() {
  const { logout } = useAuth();

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      <h1 className="text-base font-medium text-muted-foreground">
        Sistema de Detección de Plantas con IA
      </h1>
      <Button variant="outline" size="sm" onClick={() => logout()}>
        <LogOut className="mr-2 h-4 w-4" />
        Cerrar sesión
      </Button>
    </header>
  );
}
