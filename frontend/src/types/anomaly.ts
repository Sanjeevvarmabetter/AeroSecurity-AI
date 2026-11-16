export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type WorkflowStatus = "OPEN" | "INVESTIGATING" | "FALSE_POSITIVE" | "RESOLVED";

export const SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const STATUSES: WorkflowStatus[] = ["OPEN", "INVESTIGATING", "FALSE_POSITIVE", "RESOLVED"];

export interface Anomaly {
  anomaly_id: string;
  id: number;
  rule_id: string;
  rule_name: string;
  rule_version: string;
  detection_type: string;
  title: string;
  severity: Severity;
  confidence: number;
  data_quality: "GOOD" | "PARTIAL" | "DEGRADED";
  status: WorkflowStatus;
  icao24: string | null;
  registration: string | null;
  airport_ident: string | null;
  event_start: string;
  event_end: string;
  detected_at: string;
  source_refs: string[];
  has_investigation: boolean;
  notes_count: number;
}
export interface Evidence {
  ordinal: number;
  kind: "observation" | "metric" | "context";
  observation_id: number | null;
  payload: Record<string, unknown>;
}
export interface Note {
  id: number;
  author: string;
  claimed_name: string | null;
  body: string;
  created_at: string;
}
export interface TimelineEntry {
  at: string;
  kind: "detected" | "investigation_opened" | "status_changed" | "note";
  actor: string | null;
  text: string;
  data: Record<string, unknown>;
}
export interface AnomalyDetail extends Anomaly {
  description: string;
  summary: Record<string, unknown>;
  alternatives: string[];
  rule: { id: string; name: string; description: string; version: string };
  evidence: Evidence[];
  investigation: { id: number; opened_by: string; opened_at: string; closed_at: string | null } | null;
  notes: Note[];
  timeline: TimelineEntry[];
  allowed_transitions: WorkflowStatus[];
}
export interface AnomalyStats {
  total: number;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_rule: Record<string, number>;
}
export interface Emergency {
  anomaly_id: string;
  icao24: string;
  registration: string | null;
  callsign: string | null;
  squawk: string;
  meaning: string;
  severity: Severity;
  status: WorkflowStatus;
  confidence: number;
  transient: boolean;
  first_seen: string;
  last_seen: string;
  duration_s: number;
  observations: number;
  last_known_position: { lat: number; lon: number } | null;
  sources: string[];
}
export interface InvestigationItem {
  id: number;
  anomaly_id: string;
  anomaly_title: string;
  severity: Severity;
  status: WorkflowStatus;
  icao24: string | null;
  opened_by: string;
  opened_at: string;
  closed_at: string | null;
  notes_count: number;
  last_activity: string;
}
export interface Me {
  role: "viewer" | "analyst" | "admin";
  key_id: string;
}
