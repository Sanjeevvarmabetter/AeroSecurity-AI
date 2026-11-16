import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useReport, useReports } from "../hooks/useAssistant";
import { downloadReport } from "../services/api";
import type { Block, ReportSection } from "../types/assistant";
import { fmtTime } from "../utils/format";

const TAG: Record<ReportSection["provenance"], { label: string; cls: string }> = {
  VERIFIED_PLATFORM_DATA: { label: "VERIFIED PLATFORM DATA", cls: "border-ok/50 text-ok" },
  AI_GENERATED_UNVERIFIED: { label: "AI-GENERATED · UNVERIFIED", cls: "border-sev-medium/60 bg-sev-medium/10 text-sev-medium" },
};

function Blocks({ blocks }: { blocks: Block[] }) {
  // All content is untrusted text and is rendered as React text nodes.
  return (
    <div className="space-y-2">
      {blocks.map((b, i) =>
        b.type === "paragraph" ? <p key={i} className="text-sm">{b.text}</p>
        : b.type === "bullets" ? <ul key={i} className="list-disc space-y-1 pl-5 text-sm">{b.items.map((x, j) => <li key={j}>{x}</li>)}</ul>
        : (
          <div key={i} className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted"><tr>{b.columns.map((c) => <th key={c} className="px-2 py-1 font-medium">{c}</th>)}</tr></thead>
              <tbody>{b.rows.map((r, j) => <tr key={j} className="border-t border-line align-top">{r.map((c, k) => <td key={k} className="px-2 py-1 font-mono">{c}</td>)}</tr>)}</tbody>
            </table>
          </div>
        ),
      )}
    </div>
  );
}

function Viewer({ id }: { id: number }) {
  const { data: r, error } = useReport(id);
  const [dlError, setDlError] = useState<string | null>(null);
  const dl = (f: "md" | "pdf") => downloadReport(id, f).then(() => setDlError(null), (e: Error) => setDlError(e.message));
  return (
    <div className="space-y-4">
      <ErrorNote error={error} />
      {dlError && <p role="alert" className="text-sm text-sev-critical">{dlError}</p>}
      {r && (
        <>
          <header className="rounded border border-line bg-panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h1 className="text-lg font-semibold">{r.structured.title}</h1>
              <div className="flex gap-2 text-xs">
                <button onClick={() => dl("md")} className="rounded border border-line px-3 py-1.5 hover:bg-line">Download Markdown</button>
                <button onClick={() => dl("pdf")} className="rounded bg-accent px-3 py-1.5 font-medium text-ink">Download PDF</button>
              </div>
            </div>
            <p className="mt-2 rounded border border-sev-medium/40 bg-sev-medium/10 p-2 text-xs text-sev-medium"><strong>{r.structured.status}.</strong> {r.structured.notice}</p>
            <p className="mt-2 text-[11px] text-muted">Report #{r.id} · {r.subject_type} {r.subject} · generated {fmtTime(r.created_at)} by <span className="font-mono">{r.created_by}</span> · {r.includes_ai ? "includes AI content" : "no AI content"}</p>
          </header>
          {r.structured.sections.map((s) => (
            <section key={s.id} className="rounded border border-line bg-panel p-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">{s.title}</h2>
                <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${TAG[s.provenance].cls}`}>{TAG[s.provenance].label}</span>
              </div>
              <Blocks blocks={s.blocks} />
            </section>
          ))}
        </>
      )}
    </div>
  );
}

export function ReportsPage() {
  const { id } = useParams();
  const rid = id && /^\d+$/.test(id) ? Number(id) : null;
  const list = useReports();
  return (
    <section className="space-y-3">
      <NeedsToken />
      <div className="flex flex-col gap-4 lg:flex-row">
        <aside className="w-full shrink-0 lg:w-72">
          <h2 className="mb-2 text-sm font-semibold">Reports</h2>
          <ErrorNote error={list.error} />
          <ul className="divide-y divide-line rounded border border-line bg-panel text-xs">
            {list.data?.map((r) => (
              <li key={r.id}>
                <Link to={`/reports/${r.id}`} className={`block px-2 py-2 hover:bg-line ${r.id === rid ? "bg-accent/15" : ""}`}>
                  <div className="truncate">{r.title.replace("Intelligence report: ", "")}</div>
                  <div className="text-[10px] text-muted">#{r.id} · {fmtTime(r.created_at)}{r.includes_ai ? " · AI content" : ""}</div>
                </Link>
              </li>
            ))}
            {list.data?.length === 0 && <li className="px-2 py-2 text-muted">No reports yet. Generate one from an anomaly or aircraft page.</li>}
          </ul>
        </aside>
        <div className="min-w-0 flex-1">{rid ? <Viewer id={rid} /> : <p className="text-sm text-muted">Select a report, or generate a new one from an anomaly or aircraft page.</p>}</div>
      </div>
    </section>
  );
}
