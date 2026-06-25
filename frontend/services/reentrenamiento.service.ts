import api from "./api";
import type {
  CicloReentrenamiento,
  ConfigReentrenamiento,
  EstadoReentrenamiento,
  PaginatedResponse,
} from "@/types";

export type ConfigInput = Partial<
  Pick<
    ConfigReentrenamiento,
    | "auto_reentrenar"
    | "umbral_correcciones"
    | "auto_activar_modelo"
    | "margen_map50"
    | "epochs"
    | "base_model"
  >
>;

export const reentrenamientoService = {
  async estado(): Promise<EstadoReentrenamiento> {
    const { data } = await api.get<EstadoReentrenamiento>(
      "/reentrenamiento/estado/",
    );
    return data;
  },

  async getConfig(): Promise<ConfigReentrenamiento> {
    const { data } = await api.get<ConfigReentrenamiento>(
      "/reentrenamiento/config/",
    );
    return data;
  },

  async updateConfig(payload: ConfigInput): Promise<ConfigReentrenamiento> {
    const { data } = await api.put<ConfigReentrenamiento>(
      "/reentrenamiento/config/",
      payload,
    );
    return data;
  },

  async disparar(): Promise<CicloReentrenamiento> {
    const { data } = await api.post<CicloReentrenamiento>(
      "/reentrenamiento/disparar/",
      {},
    );
    return data;
  },

  async activar(cicloId: number): Promise<CicloReentrenamiento> {
    const { data } = await api.post<CicloReentrenamiento>(
      "/reentrenamiento/activar/",
      { ciclo_id: cicloId },
    );
    return data;
  },

  async ciclos(): Promise<CicloReentrenamiento[]> {
    const { data } = await api.get<
      PaginatedResponse<CicloReentrenamiento> | CicloReentrenamiento[]
    >("/reentrenamiento/ciclos/");
    return Array.isArray(data) ? data : data.results;
  },
};
