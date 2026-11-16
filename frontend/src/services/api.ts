import { getToken } from "../stores/auth";
import type { AISettings, Analysis, ProviderName } from "../types/ai";
import type { ChatReply, Conversation, ConversationDetail, IntelItem, Report, ReportMeta } from "../types/assistant";
import type {
  Anomaly,
  AnomalyDetail,
  AnomalyStats,
  Emergency,
  InvestigationItem,
  Me,
  Note,
  WorkflowStatus,
} from "../types/anomaly";
import type {
  AircraftDetail,
  AircraftSummary,
  Airport,
  DataSource,
  LiveResponse,
  Observation,
  Page,
  Trajectory,
} from "../types/aviation";
import type { AirportTraffic, FleetAnalytics, OverviewAnalytics } from "../types/analytics";
import type { DetectionRuleOut, DetectionRunReport } from "../types/detection";
import type { CaseDetail, CaseItem, CaseNote } from "../types/investigation";
import type { HealthResponse } from "../types/health";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Method = "GET" | "POST" | "PATCH" | "PUT";
type ParamValue = string | number | boolean | null | undefined | (string | number)[];

async function request<T>(
  method: Method,
  path: string,
  params: Record<string, ParamValue> = {},
  acceptStatuses: number[] = [],
  body?: unknown,
): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, String(x)));
    else if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api/v1${path}${qs.size ? `?${qs}` : ""}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok && !acceptStatuses.includes(res.status)) {
    let msg = `Request failed (${res.status})`;
    if (res.status === 401) msg = "Authentication required";
    else {
      try {
        const err = await res.json();
        if (err?.error?.message) msg = err.error.message;
        if (res.status === 422 && Array.isArray(err?.error?.details) && err.error.details[0]?.msg)
          msg = `Invalid input: ${err.error.details[0].msg}`;
      } catch {
        /* keep generic message */
      }
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

const get = <T>(path: string, params: Record<string, ParamValue> = {}, accept: number[] = []) =>
  request<T>("GET", path, params, accept);

// The backend answers 503 with a valid health body when a dependency is down.
export const getHealth = () => get<HealthResponse>("/system/health", {}, [503]);
export const getDataSources = () => get<DataSource[]>("/data-sources");
export const getOverviewAnalytics = () => get<OverviewAnalytics>("/analytics/overview");
export const getFleetAnalytics = () => get<FleetAnalytics>("/analytics/fleet");
export const searchAircraft = (q: string, limit = 25, offset = 0) =>
  get<Page<AircraftSummary>>("/aviation/aircraft", { q, limit, offset });
export const getAircraft = (icao24: string) => get<AircraftDetail>(`/aviation/aircraft/${icao24}`);
export const getHistory = (icao24: string, p: { start?: string; end?: string; limit: number; offset: number }) =>
  get<Page<Observation>>(`/aviation/aircraft/${icao24}/history`, p);
export const getTrajectory = (icao24: string, p: { start?: string; end?: string; gap_s?: number }) =>
  get<Trajectory>("/analytics/trajectories", { icao24, ...p });
export const getLive = (p: {
  at?: string;
  max_age_s?: number;
  lamin?: number;
  lomin?: number;
  lamax?: number;
  lomax?: number;
}) => get<LiveResponse>("/aviation/aircraft/live", p);
export const getAirports = (q?: string, limit = 50, offset = 0) =>
  get<Page<Airport>>("/aviation/airports", { q, limit, offset });
export const getAirport = (code: string) => get<Airport>(`/aviation/airports/${code}`);
export const getAirportTraffic = (code: string, radius_km = 25) =>
  get<AirportTraffic>(`/aviation/airports/${code}/traffic`, { radius_km });

// -- detection rules ------------------------------------------------------------------------------
export const getDetectionRules = () => get<DetectionRuleOut[]>("/detection/rules");
export const getDetectionRule = (id: string) => get<DetectionRuleOut>(`/detection/rules/${id}`);
export const updateDetectionRule = (id: string, body: { enabled?: boolean; config?: Record<string, unknown> }) =>
  request<DetectionRuleOut>("PATCH", `/detection/rules/${id}`, {}, [], body);
export const runDetection = (body?: { rule_ids?: string[]; icao24?: string }) =>
  request<DetectionRunReport>("POST", "/detection/run", {}, [], body);

// -- investigation cases --------------------------------------------------------------------------
export const getCases = (p?: { status?: string[]; severity?: string[]; icao24?: string; limit?: number; offset?: number }) =>
  get<Page<CaseItem>>("/investigations/cases", (p as Record<string, ParamValue>) || {});
export const getCaseDetail = (id: number) => get<CaseDetail>(`/investigations/${id}`);
export const createCase = (body: {
  title: string;
  description?: string;
  icao24?: string;
  anomaly_id?: string;
  severity?: string;
  initial_note?: string;
  claimed_name?: string;
}) => request<CaseDetail>("POST", "/investigations", {}, [], body);
export const updateCaseStatus = (id: number, body: { status: string; reason?: string; claimed_name?: string }) =>
  request<CaseDetail>("PATCH", `/investigations/${id}/status`, {}, [], body);
export const addCaseNote = (id: number, body: { body: string; claimed_name?: string }) =>
  request<CaseNote>("POST", `/investigations/${id}/notes`, {}, [], body);

// -- security operations --------------------------------------------------------------------------
export interface AnomalyQuery {
  severity?: string[];
  status?: string[];
  detection_type?: string;
  rule_id?: string;
  icao24?: string;
  min_confidence?: number;
  start?: string;
  end?: string;
  sort?: string;
  order?: string;
  limit?: number;
  offset?: number;
}
export const getAnomalies = (q: AnomalyQuery) => get<Page<Anomaly>>("/anomalies", { ...q });
export const getAnomalyStats = () => get<AnomalyStats>("/anomalies/stats");
export const getAnomaly = (id: string) => get<AnomalyDetail>(`/anomalies/${id}`);
export const getEmergencies = (q: { squawk?: string; status?: string[]; limit?: number; offset?: number }) =>
  get<Page<Emergency>>("/emergencies", { ...q });
export const getInvestigations = (q: { status?: string[]; limit?: number; offset?: number }) =>
  get<Page<InvestigationItem>>("/investigations", { ...q });
export const getMe = () => get<Me>("/auth/me");
export const startInvestigation = (id: string, note: string, claimed_name?: string) =>
  request<AnomalyDetail>("POST", `/anomalies/${id}/investigate`, {}, [], { note, claimed_name: claimed_name || null });
export const setStatus = (id: string, status: WorkflowStatus, reason: string, claimed_name?: string) =>
  request<AnomalyDetail>("PATCH", `/anomalies/${id}/status`, {}, [], { status, reason, claimed_name: claimed_name || null });
export const addNote = (id: string, body: string, claimed_name?: string) =>
  request<Note>("POST", `/anomalies/${id}/notes`, {}, [], { body, claimed_name: claimed_name || null });

// -- AI ----------------------------------------------------------------------------------------------
export interface AiTarget {
  provider?: ProviderName;
  model?: string;
}
export const explainAnomaly = (anomaly_id: string, t: AiTarget) =>
  request<Analysis>("POST", "/intelligence/anomaly-explanation", {}, [], { anomaly_id, provider: t.provider || null, model: t.model || null });
export const investigateAircraft = (icao24: string, t: AiTarget) =>
  request<Analysis>("POST", "/intelligence/aircraft-investigation", {}, [], { icao24, provider: t.provider || null, model: t.model || null });
export const getAnalyses = (q: { anomaly_id?: string; icao24?: string }) => get<Analysis[]>("/intelligence/analyses", { ...q, limit: 10 });
export const getAISettings = (check: boolean) => get<AISettings>("/settings/ai", { check });
export const putAISettings = (body: { provider?: ProviderName; ollama_model?: string; openrouter_model?: string }) =>
  request<AISettings>("PUT", "/settings/ai", {}, [], body);

// -- assistant, threat intel, reports ---------------------------------------------------------------
export const sendChat = (message: string, conversation_id: string | null, t: AiTarget) =>
  request<ChatReply>("POST", "/intelligence/chat", {}, [], { message, conversation_id, provider: t.provider || null, model: t.model || null });
export const getConversations = () => get<Conversation[]>("/intelligence/conversations");
export const getConversation = (id: string) => get<ConversationDetail>(`/intelligence/conversations/${id}`);
export const correlateThreats = (anomaly_id: string, t: AiTarget) =>
  request<Analysis>("POST", "/intelligence/threat-correlation", {}, [], { anomaly_id, provider: t.provider || null, model: t.model || null });
export const getIntel = (q: string, offset = 0) => get<Page<IntelItem>>("/threat-intel", { q, limit: 20, offset });
export const importArxiv = (query: string, max_results: number) =>
  request<{ found: number; added: number; skipped_existing: number }>("POST", "/threat-intel/import/arxiv", {}, [], { query, max_results });
export const addIntel = (body: Record<string, unknown>) => request<IntelItem>("POST", "/threat-intel", {}, [], body);
export const createReport = (subject: { anomaly_id?: string; icao24?: string }, include_ai: boolean) =>
  request<Report>("POST", "/intelligence/reports", {}, [], { ...subject, include_ai });
export const getReports = () => get<ReportMeta[]>("/intelligence/reports");
export const getReport = (id: number) => get<Report>(`/intelligence/reports/${id}`);

/** Download an export. The endpoint needs the bearer token, so a plain link would not work. */
export async function downloadReport(id: number, format: "md" | "pdf"): Promise<void> {
  const token = getToken();
  const res = await fetch(`/api/v1/intelligence/reports/${id}/export?format=${format}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, `Export failed (${res.status})`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `aerosecurity-report-${id}.${format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
