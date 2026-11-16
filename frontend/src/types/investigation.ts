export type CaseStatus =
  | "NEW"
  | "IN_PROGRESS"
  | "UNDER_REVIEW"
  | "ESCALATED"
  | "CLOSED"
  | "FALSE_POSITIVE";

export type CaseSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface CaseNote {
  id: number;
  author: string;
  claimed_name: string | null;
  body: string;
  created_at: string;
}

export interface TimelineEvent {
  timestamp: string;
  actor: string;
  action: string;
  details: Record<string, unknown>;
}

export interface CaseItem {
  id: number;
  title: string;
  description: string | null;
  status: CaseStatus;
  severity: CaseSeverity;
  opened_by: string;
  lead_analyst: string | null;
  opened_at: string;
  updated_at: string;
  closed_at: string | null;
  aircraft_id: number | null;
  icao24: string | null;
  anomaly_id: string | null;
  anomaly_title: string | null;
  notes_count: number;
}

export interface CaseDetail extends CaseItem {
  notes: CaseNote[];
  timeline: TimelineEvent[];
  aircraft_summary: Record<string, unknown> | null;
  anomaly_summary: Record<string, unknown> | null;
}
