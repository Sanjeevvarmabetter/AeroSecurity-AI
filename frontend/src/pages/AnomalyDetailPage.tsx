import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AiPanel } from "../components/AiPanel";
import { ReportButton } from "../components/ReportButton";
import { QualityBadge, SeverityBadge, WorkflowBadge } from "../components/Badges";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { TrackMap } from "../components/TrackMap";
import { useTrajectory } from "../hooks/useAviation";
import { useAddNote, useAnomaly, useMe, useSetStatus, useStartInvestigation } from "../hooks/useSecurity";
import type { AnomalyDetail, WorkflowStatus } from "../types/anomaly";
import { fmtAlt, fmtSpeed, fmtTime, orDash } from "../utils/format";

const ID = /^ANM-\d{1,9}$/;
const CLOSING: WorkflowStatus[] = ["FALSE_POSITIVE", "RESOLVED"];
const LABEL: Record<WorkflowStatus, string> = {
  OPEN: "Reopen",
  INVESTIGATING: "Mark investigating",
  FALSE_POSITIVE: "Mark false positive",
  RESOLVED: "Mark resolved",
};
const inputCls = "w-full rounded border border-line bg-ink px-2 py-1 text-sm";

function Workflow({ a, canWrite }: { a: AnomalyDetail; canWrite: boolean }) {
  const id = a.anomaly_id;
  const start = useStartInvestigation(id);
  const status = useSetStatus(id);
  const note = useAddNote(id);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [target, setTarget] = useState<WorkflowStatus | null>(null);
  const err = start.error ?? status.error ?? note.error;
  const needsReason = target !== null && CLOSING.includes(target);

  return (
    <section className="rounded border border-line bg-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Investigation</h2>
        <WorkflowBadge status={a.status} />
      </div>
      {!canWrite && <p className="mb-2 text-xs text-sev-medium">Read-only: an analyst-role token is required to change status or add notes.</p>}
      <ErrorNote error={err} />
      <label className="mb-3 block text-xs text-muted">
        Your name (optional, recorded as self-asserted)
        <input aria-label="Your name" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} className={`${inputCls} mt-1`} disabled={!canWrite} />
      </label>

      {!a.investigation ? (
        <button disabled={!canWrite || a.status !== "OPEN" || start.isPending} onClick={() => start.mutate({ note: "", name: name || undefined })} className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-ink disabled:opacity-40">
          Start investigation
        </button>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">Opened {fmtTime(a.investigation.opened_at)} by <span className="font-mono">{a.investigation.opened_by}</span>{a.investigation.closed_at && ` · closed ${fmtTime(a.investigation.closed_at)}`}</p>
          <Link
            to={`/investigations/${a.investigation.id}`}
            className="mb-3 block text-center rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20 transition-colors"
          >
            Open Full Case Dossier (CASE-{a.investigation.id.toString().padStart(4, "0")}) &rarr;
          </Link>
          <div className="mb-3 flex flex-wrap gap-2">
            {a.allowed_transitions.map((t) => (
              <button key={t} disabled={!canWrite} onClick={() => { setTarget(t === target ? null : t); setReason(""); }} className={`rounded border px-2 py-1 text-xs ${target === t ? "border-accent bg-accent/20 text-accent" : "border-line"} disabled:opacity-40`}>
                {LABEL[t]}
              </button>
            ))}
          </div>
          {target && (
            <form className="mb-3 space-y-2" onSubmit={(e) => { e.preventDefault(); status.mutate({ status: target, reason, name: name || undefined }, { onSuccess: () => { setTarget(null); setReason(""); } }); }}>
              <label className="block text-xs text-muted">
                Reason {needsReason ? "(required)" : "(optional)"}
                <textarea aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} rows={2} className={`${inputCls} mt-1`} />
              </label>
              <button disabled={status.isPending || (needsReason && !reason.trim())} className="rounded bg-accent px-3 py-1 text-sm font-medium text-ink disabled:opacity-40">Confirm: {LABEL[target]}</button>
            </form>
          )}
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) note.mutate({ body: text, name: name || undefined }, { onSuccess: () => setText("") }); }}>
            <label className="block text-xs text-muted">
              Add note (plain text)
              <textarea aria-label="Note" value={text} onChange={(e) => setText(e.target.value)} maxLength={5000} rows={3} className={`${inputCls} mt-1`} disabled={!canWrite} />
            </label>
            <button disabled={!canWrite || !text.trim() || note.isPending} className="rounded border border-line px-3 py-1 text-sm disabled:opacity-40">Add note</button>
          </form>
        </>
      )}
    </section>
  );
}

function MetricList({ data }: { data: Record<string, unknown> }) {
  const rows = Object.entries(data).filter(([, v]) => v !== null && typeof v !== "object");
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs md:grid-cols-3">
      {rows.map(([k, v]) => (
        <div key={k}><dt className="text-muted">{k.replaceAll("_", " ")}</dt><dd className="font-mono">{String(v)}</dd></div>
      ))}
    </dl>
  );
}

export function AnomalyDetailPage() {
  const { id } = useParams();
  const valid = !!id && ID.test(id);
  const { data: a, error } = useAnomaly(valid ? id : undefined);
  const me = useMe();
  const canWrite = me.data?.role === "analyst" || me.data?.role === "admin";
  const [full, setFull] = useState(false);
  const range = useMemo(() => {
    if (!a || full) return {};
    const pad = 10 * 60_000;
    return { start: new Date(Date.parse(a.event_start) - pad).toISOString(), end: new Date(Date.parse(a.event_end) + pad).toISOString() };
  }, [a, full]);
  const traj = useTrajectory(a?.icao24 ?? undefined, range);
  const highlights = useMemo(
    () => (a?.evidence ?? []).filter((e) => e.kind === "observation" && typeof e.payload.lat === "number" && typeof e.payload.lon === "number").map((e) => ({ lat: e.payload.lat as number, lon: e.payload.lon as number })),
    [a],
  );

  if (!valid) return <p className="text-sev-critical">Invalid anomaly id.</p>;
  return (
    <section className="space-y-4">
      <p className="text-xs"><Link to="/anomalies" className="text-accent underline">← Anomaly Center</Link></p>
      <NeedsToken />
      <ErrorNote error={error} />
      {a && (
        <>
          <header className="rounded border border-line bg-panel p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-muted">{a.anomaly_id}</span>
              <SeverityBadge severity={a.severity} />
              <WorkflowBadge status={a.status} />
              <QualityBadge quality={a.data_quality} />
            </div>
            <h1 className="mt-1 text-lg font-semibold">{a.title}</h1>
            <p className="mt-1 text-sm">{a.description}</p>
            <p className="mt-2 text-[11px] text-muted">
              Confidence reflects how sure the rule is that this <em>data pattern</em> is real as described. It is not the probability of malicious activity, and a detection is not a verdict.
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
              <div><dt className="text-muted">Aircraft</dt><dd className="font-mono">{a.icao24 ? <Link className="text-accent underline" to={`/aircraft/${a.icao24}`}>{a.icao24}</Link> : orDash(a.airport_ident)} {a.registration}</dd></div>
              <div><dt className="text-muted">Event</dt><dd className="font-mono">{fmtTime(a.event_start)} → {fmtTime(a.event_end)}</dd></div>
              <div><dt className="text-muted">Confidence (data pattern)</dt><dd className="font-mono" title="How sure the rule is that this data pattern is real as described. Not the probability of malicious activity.">{a.confidence.toFixed(2)}</dd></div>
              <div><dt className="text-muted">Rule</dt><dd className="font-mono">{a.rule.id} v{a.rule.version} · {a.rule.name}</dd></div>
              <div><dt className="text-muted">Sources</dt><dd className="font-mono">{a.source_refs.join(", ") || "—"}</dd></div>
            </dl>
          </header>

          <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
            <div className="min-w-0 space-y-4">
              {a.icao24 && (
                <div>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="text-muted">{full ? "Entire recorded track" : "Track around the event (±10 min)"}; evidence observations are ringed</span>
                    <button className="text-accent underline" onClick={() => setFull(!full)}>{full ? "Show event window" : "Compare with full history"}</button>
                  </div>
                  <TrackMap trajectory={traj.data} highlights={highlights} className="h-[360px]" />
                </div>
              )}

              <section className="rounded border border-line bg-panel p-4">
                <h2 className="mb-2 text-sm font-semibold">Detection metrics</h2>
                <MetricList data={a.summary} />
              </section>

              <section className="rounded border border-line bg-panel p-4">
                <h2 className="mb-1 text-sm font-semibold">Alternative explanations</h2>
                <p className="mb-2 text-xs text-muted">A detection is a data pattern. These explanations, benign and otherwise, have not been ruled out.</p>
                <ul className="list-disc space-y-1 pl-5 text-sm">{a.alternatives.map((x) => <li key={x}>{x}</li>)}</ul>
              </section>

              <AiPanel kind="anomaly" subject={a.anomaly_id} />
              <AiPanel kind="correlation" subject={a.anomaly_id} />

              <section className="rounded border border-line bg-panel p-4">
                <h2 className="mb-2 text-sm font-semibold">Evidence ({a.evidence.length})</h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-muted"><tr>{["#", "Kind", "Time (UTC)", "Position", "Altitude", "Speed", "Squawk"].map((h) => <th key={h} className="px-2 py-1 font-medium">{h}</th>)}</tr></thead>
                    <tbody className="font-mono">
                      {a.evidence.map((e) => (
                        <tr key={e.ordinal} id={`ev-${e.ordinal}`} className="border-t border-line align-top transition-colors">
                          <td className="px-2 py-1">{e.ordinal}</td>
                          <td className="px-2">{e.kind === "observation" ? "obs" : e.kind}{typeof e.payload.role === "string" ? ` (${e.payload.role})` : ""}</td>
                          {e.kind === "observation" ? (
                            <>
                              <td className="whitespace-nowrap px-2">{fmtTime(String(e.payload.t)).replace(" UTC", "")}</td>
                              <td className="px-2">{typeof e.payload.lat === "number" ? `${e.payload.lat.toFixed(4)}, ${(e.payload.lon as number).toFixed(4)}` : "—"}</td>
                              <td className="whitespace-nowrap px-2">{fmtAlt(e.payload.baro_altitude_m as number | null)}</td>
                              <td className="whitespace-nowrap px-2">{fmtSpeed(e.payload.velocity_ms as number | null)}</td>
                              <td className="px-2">{orDash(e.payload.squawk as string | null)}</td>
                            </>
                          ) : (
                            <td colSpan={5} className="px-2"><pre className="whitespace-pre-wrap break-words text-[11px] text-slate-300">{JSON.stringify(e.payload, null, 1)}</pre></td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>

            <div className="space-y-4">
              <Workflow a={a} canWrite={canWrite} />
              <ReportButton subject={{ anomaly_id: a.anomaly_id }} />
              <section className="rounded border border-line bg-panel p-4">
                <h2 className="mb-2 text-sm font-semibold">Timeline</h2>
                <ol className="space-y-3 border-l border-line pl-3">
                  {a.timeline.map((t, i) => (
                    <li key={i} className="text-xs">
                      <div className="text-muted">{fmtTime(t.at)} · <span className="font-mono">{t.actor ?? "—"}</span></div>
                      {/* Notes are untrusted text: rendered as a text node, never as HTML. */}
                      <div className={t.kind === "note" ? "whitespace-pre-wrap break-words rounded bg-ink p-2" : ""}>{t.text}</div>
                    </li>
                  ))}
                </ol>
              </section>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
