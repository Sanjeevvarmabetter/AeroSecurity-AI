import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { QualityBadge, SeverityBadge, WorkflowBadge } from "../components/Badges";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useAnomalies, useAnomalyStats } from "../hooks/useSecurity";
import { SEVERITIES, STATUSES } from "../types/anomaly";
import { parseFilters, toSearch, toggle } from "../utils/anomalyFilters";
import { fmtTime } from "../utils/format";

const PAGE = 50;
const chip = (on: boolean) =>
  `rounded border px-2 py-1 text-xs ${on ? "border-accent bg-accent/20 text-accent" : "border-line text-muted hover:bg-line"}`;

export function AnomalyCenterPage() {
  const [sp, setSp] = useSearchParams();
  const q = parseFilters(sp);
  const set = (patch: Partial<typeof q>) => setSp(toSearch({ ...q, offset: 0, ...patch }), { replace: true });
  const stats = useAnomalyStats();
  const { data, error, isFetching } = useAnomalies({ ...q, limit: PAGE });
  const [ac, setAc] = useState(q.icao24 ?? "");
  useEffect(() => {
    setAc(q.icao24 ?? "");
  }, [q.icao24]);
  const acValid = /^[0-9a-fA-F]{0,6}$/.test(ac);

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">Anomaly Center</h1>
        <p className="text-xs text-muted">Deterministic detections. Confidence is confidence in the data pattern, not the probability of malicious activity.</p>
      </div>
      <NeedsToken />
      <ErrorNote error={error ?? stats.error} />

      {stats.data && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <div className="rounded border border-line bg-panel px-3 py-2">
            <div className="text-[11px] uppercase text-muted">Total</div>
            <div className="font-mono text-lg">{stats.data.total}</div>
          </div>
          {SEVERITIES.map((s) => (
            <button key={s} onClick={() => set({ severity: toggle(q.severity, s) })} className={`rounded border px-3 py-2 text-left ${q.severity?.includes(s) ? "border-accent bg-accent/10" : "border-line bg-panel"}`}>
              <SeverityBadge severity={s} />
              <div className="font-mono text-lg">{stats.data.by_severity[s] ?? 0}</div>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3 rounded border border-line bg-panel p-3 text-xs">
        <div>
          <div className="mb-1 text-muted">Status</div>
          <div className="flex gap-1">
            {STATUSES.map((s) => (
              <button key={s} className={chip(!!q.status?.includes(s))} onClick={() => set({ status: toggle(q.status, s) })}>
                {s.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
        <label>
          <div className="mb-1 text-muted">Event category</div>
          <select aria-label="Event category" value={q.detection_type ?? ""} onChange={(e) => set({ detection_type: e.target.value || undefined })} className="rounded border border-line bg-ink px-2 py-1">
            <option value="">All</option>
            {Object.keys(stats.data?.by_type ?? {}).sort().map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          <div className="mb-1 text-muted">Rule</div>
          <select aria-label="Rule" value={q.rule_id ?? ""} onChange={(e) => set({ rule_id: e.target.value || undefined })} className="rounded border border-line bg-ink px-2 py-1">
            <option value="">All</option>
            {Object.keys(stats.data?.by_rule ?? {}).sort().map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <form onSubmit={(e) => { e.preventDefault(); if (acValid) set({ icao24: ac || undefined }); }}>
          <label>
            <div className="mb-1 text-muted">Aircraft (ICAO24 prefix)</div>
            <input aria-label="Aircraft" value={ac} onChange={(e) => setAc(e.target.value.trim())} placeholder="e.g. 4406" className={`w-32 rounded border bg-ink px-2 py-1 font-mono ${acValid ? "border-line" : "border-sev-critical"}`} />
          </label>
        </form>
        <label>
          <div className="mb-1 text-muted">Min confidence</div>
          <select aria-label="Min confidence" value={q.min_confidence ?? ""} onChange={(e) => set({ min_confidence: e.target.value ? Number(e.target.value) : undefined })} className="rounded border border-line bg-ink px-2 py-1">
            <option value="">Any</option>
            {[0.5, 0.7, 0.9].map((c) => <option key={c} value={c}>≥ {c}</option>)}
          </select>
        </label>
        <label>
          <div className="mb-1 text-muted">Sort</div>
          <select aria-label="Sort" value={`${q.sort}:${q.order}`} onChange={(e) => { const [sort, order] = e.target.value.split(":"); set({ sort, order }); }} className="rounded border border-line bg-ink px-2 py-1">
            <option value="severity:desc">Severity (high first)</option>
            <option value="detected_at:desc">Newest detected</option>
            <option value="event_start:desc">Latest event</option>
            <option value="event_start:asc">Earliest event</option>
            <option value="confidence:desc">Confidence (high first)</option>
          </select>
        </label>
        <button className="ml-auto text-muted underline" onClick={() => { setSp({}, { replace: true }); setAc(""); }}>Reset</button>
      </div>

      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full text-left text-xs">
          <thead className="bg-panel text-muted">
            <tr>{["ID", "Severity", "Detection", "Aircraft", "Event time (UTC)", "Confidence", "Data quality", "Status", ""].map((h) => <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {data?.items.map((a) => (
              <tr key={a.anomaly_id} className="border-t border-line hover:bg-panel/60">
                <td className="whitespace-nowrap px-2 py-2 font-mono"><Link className="text-accent underline" to={`/anomalies/${a.anomaly_id}`}>{a.anomaly_id}</Link></td>
                <td className="px-2"><SeverityBadge severity={a.severity} /></td>
                <td className="px-2"><div className="max-w-sm">{a.title}</div><div className="text-[11px] text-muted">{a.rule_id} · {a.detection_type}</div></td>
                <td className="px-2 font-mono">{a.icao24 ? <Link className="underline" to={`/aircraft/${a.icao24}`}>{a.icao24}</Link> : a.airport_ident ?? "—"}<div className="text-[11px] text-muted">{a.registration ?? ""}</div></td>
                <td className="whitespace-nowrap px-2">{fmtTime(a.event_start)}</td>
                <td className="px-2 font-mono">{a.confidence.toFixed(2)}</td>
                <td className="px-2"><QualityBadge quality={a.data_quality} /></td>
                <td className="px-2"><WorkflowBadge status={a.status} />{a.notes_count > 0 && <span className="ml-1 text-muted">· {a.notes_count} note{a.notes_count > 1 ? "s" : ""}</span>}</td>
                <td className="px-2"><Link className="rounded bg-accent/20 px-2 py-1 text-accent" to={`/anomalies/${a.anomaly_id}`}>{a.has_investigation ? "Open" : "Investigate"}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <p className="p-4 text-sm text-muted">No anomalies match these filters.</p>}
      </div>
      {data && (
        <div className="flex items-center gap-3 text-xs text-muted">
          <button disabled={!q.offset} onClick={() => set({ offset: Math.max(0, (q.offset ?? 0) - PAGE) })} className="rounded border border-line px-2 py-1 disabled:opacity-40">Previous</button>
          <span>{data.total === 0 ? 0 : (q.offset ?? 0) + 1}–{Math.min((q.offset ?? 0) + PAGE, data.total)} of {data.total}{isFetching ? " · updating…" : ""}</span>
          <button disabled={(q.offset ?? 0) + PAGE >= data.total} onClick={() => set({ offset: (q.offset ?? 0) + PAGE })} className="rounded border border-line px-2 py-1 disabled:opacity-40">Next</button>
        </div>
      )}
    </section>
  );
}
