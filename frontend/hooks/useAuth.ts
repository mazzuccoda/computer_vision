"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { authService } from "@/services/auth.service";

export function useAuth() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setIsAuthenticated(authService.isAuthenticated());
    setLoading(false);
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      await authService.login(username, password);
      setIsAuthenticated(true);
      router.push("/dashboard");
    },
    [router],
  );

  const logout = useCallback(async () => {
    await authService.logout();
    setIsAuthenticated(false);
    toast.success("Sesión cerrada");
    router.push("/login");
  }, [router]);

  return { isAuthenticated, loading, login, logout };
}
