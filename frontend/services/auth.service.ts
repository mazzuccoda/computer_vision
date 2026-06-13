import api from "./api";
import { AuthTokens } from "@/types";

export const authService = {
  async login(username: string, password: string): Promise<AuthTokens> {
    const { data } = await api.post<AuthTokens>("/auth/login/", {
      username,
      password,
    });
    localStorage.setItem("access_token", data.access);
    localStorage.setItem("refresh_token", data.refresh);
    return data;
  },

  async logout(): Promise<void> {
    const refresh = localStorage.getItem("refresh_token");
    try {
      if (refresh) await api.post("/auth/logout/", { refresh });
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  },

  isAuthenticated(): boolean {
    if (typeof window === "undefined") return false;
    return Boolean(localStorage.getItem("access_token"));
  },
};
