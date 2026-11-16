import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateReport } from "../hooks/useAssistant";
import { useMe } from "../hooks/useSecurity";
import { ErrorNote } from "./QueryNotice";

export function ReportButton({ subject }: { subject: { anomaly_id?: string; icao24?: string } }) {
  const me = useMe();
  const canWrite = me.data?.role === "analyst" || me.data?.role === "admin";
  const create = useCreateReport();
  const nav = useNavigate();
  const [withAi, setWithAi] = useState(false);
  return (
    <section className="rounded border border-line bg-panel p-4" aria-label="Report generation">
      <h2 className="mb-1 text-sm font-semibold">Intelligence report</h2>
      <p className="mb-2 text-xs text-muted">
        Platform data and AI content are assembled into clearly separated, labelled sections. Reports are always marked UNREVIEWED.
      </p>
      <ErrorNote error={create.error} />
      <label className="mb-2 flex items-center gap-2 text-xs">
        <input type="checkbox" checked={withAi} onChange={(e) => setWithAi(e.target.checked)} disabled={!canWrite} />
        Include existing AI analysis (labelled unverified)
      </label>
      <button
        disabled={!canWrite || create.isPending}
        onClick={() => create.mutate({ subject, includeAi: withAi }, { onSuccess: (r) => nav(`/reports/${r.id}`) })}
        className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-ink disabled:opacity-40"
      >
        {create.isPending ? "Generating…" : "Generate report"}
      </button>
      {!canWrite && <p className="mt-2 text-xs text-sev-medium">An analyst-role token is required to generate reports.</p>}
    </section>
  );
}
