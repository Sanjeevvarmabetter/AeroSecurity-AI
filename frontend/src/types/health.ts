export type Status = "ok" | "degraded" | "down";

export interface ComponentHealth {
  status: Status;
  detail: string | null;
}

export interface HealthResponse {
  status: Status;
  version: string;
  environment: string;
  components: Record<string, ComponentHealth>;
}
