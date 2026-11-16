export type ProviderName = "ollama" | "openrouter";

export interface Analysis {
  analysis_id: number;
  kind: "anomaly_explanation" | "aircraft_investigation" | "threat_correlation";
  subject: string;
  provider: string;
  model: string;
  prompt_version: string;
  status: "OK" | "INVALID_OUTPUT" | "PROVIDER_ERROR";
  ai_generated: true;
  disclaimer: string;
  output: Record<string, unknown> | null;
  warnings: string[];
  error: string | null;
  requested_by: string;
  created_at: string;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  deterministic: { anomaly_id: string; severity: string; status: string; confidence: number; rule: string } | null;
}
export interface ProviderStatus {
  name: ProviderName;
  configured: boolean;
  current_model: string | null;
  healthy: boolean | null;
  detail: string | null;
  models: string[] | null;
  base_url: string | null;
}
export interface AISettings {
  provider: ProviderName;
  source: "environment" | "database";
  providers: ProviderStatus[];
  limits: Record<string, number>;
}
