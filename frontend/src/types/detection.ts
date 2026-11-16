export interface DetectionRuleOut {
  id: string;
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  config: Record<string, unknown>;
  findings_count: number;
  category: string;
}

export interface DetectionRunReport {
  aircraft_processed: number;
  airports_processed: number;
  observations_read: number;
  rules: Record<
    string,
    {
      findings: number;
      created: number;
      updated: number;
      unchanged: number;
    }
  >;
}
