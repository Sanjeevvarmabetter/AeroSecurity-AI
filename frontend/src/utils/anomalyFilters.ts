import type { AnomalyQuery } from "../services/api";
import { SEVERITIES, STATUSES } from "../types/anomaly";

const HEX = /^[0-9a-fA-F]{0,6}$/;

/** Parse the URL search string into a validated query. Unknown or malformed values are dropped, never sent. */
export function parseFilters(sp: URLSearchParams): AnomalyQuery {
  const q: AnomalyQuery = {};
  const sev = sp.getAll("severity").filter((s) => (SEVERITIES as string[]).includes(s));
  const st = sp.getAll("status").filter((s) => (STATUSES as string[]).includes(s));
  if (sev.length) q.severity = sev;
  if (st.length) q.status = st;
  const type = sp.get("detection_type");
  if (type && /^[A-Z_]{1,32}$/.test(type)) q.detection_type = type;
  const rule = sp.get("rule_id");
  if (rule && /^DET-\d{3}$/.test(rule)) q.rule_id = rule;
  const ac = sp.get("icao24");
  if (ac && HEX.test(ac) && ac.length > 0) q.icao24 = ac.toLowerCase();
  const conf = Number(sp.get("min_confidence"));
  if (sp.get("min_confidence") && conf >= 0 && conf <= 1) q.min_confidence = conf;
  const sort = sp.get("sort");
  q.sort = ["detected_at", "event_start", "severity", "confidence"].includes(sort ?? "") ? sort! : "severity";
  q.order = sp.get("order") === "asc" ? "asc" : "desc";
  const off = Number(sp.get("offset"));
  q.offset = Number.isInteger(off) && off > 0 ? off : 0;
  return q;
}

export function toSearch(q: AnomalyQuery): URLSearchParams {
  const sp = new URLSearchParams();
  q.severity?.forEach((s) => sp.append("severity", s));
  q.status?.forEach((s) => sp.append("status", s));
  for (const k of ["detection_type", "rule_id", "icao24", "min_confidence", "sort", "order"] as const) {
    const v = q[k];
    if (v !== undefined && v !== "") sp.set(k, String(v));
  }
  if (q.offset) sp.set("offset", String(q.offset));
  return sp;
}

export const toggle = (list: string[] | undefined, v: string): string[] =>
  list?.includes(v) ? list.filter((x) => x !== v) : [...(list ?? []), v];
