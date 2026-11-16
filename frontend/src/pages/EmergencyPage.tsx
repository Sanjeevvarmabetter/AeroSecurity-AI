import { useState } from "react";
import { Link } from "react-router-dom";

import { SeverityBadge, WorkflowBadge } from "../components/Badges";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useEmergencies } from "../hooks/useSecurity";
import { fmtDuration, fmtTime, orDash } from "../utils/format";

const CODES = [
  { code: "7500", meaning: "Unlawful interference" },
  { code: "7700", meaning: "General emergency" },
  { code: "7600", meaning: "Radio communication failure" },
];

export function EmergencyPage() {
  const [squawk, setSquawk] = useState<string | undefined>();
  const [open, setOpen] = useState(false);
  const { data, error } = useEmergencies({ squawk, status: open ? ["OPEN", "INVESTIGATING"] : undefined });
  return (
    <section className="space-y-4">
      <h1 className="text-lg font-semibold">Emergency Intelligence</h1>
      <p className="max-w-3xl text-xs text-muted">
        Transponder codes 7500, 7600 and 7700 observed in stored data (DET-005). A squawk code shows what the crew or equipment
        selected; it does not establish the cause. Single observations may be a code passing through while being dialled.
      </p>
      <NeedsToken />
      <ErrorNote error={error} />
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button onClick={() => setSquawk(undefined)} className={`rounded border px-2 py-1 ${!squawk ? "border-accent bg-accent/20 text-accent" : "border-line text-muted"}`}>All codes</button>
        {CODES.map((c) => (
          <button key={c.code} onClick={() => setSquawk(c.code)} className={`rounded border px-2 py-1 ${squawk === c.code ? "border-accent bg-accent/20 text-accent" : "border-line text-muted"}`}>
            {c.code} · {c.meaning}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1"><input type="checkbox" checked={open} onChange={(e) => setOpen(e.target.checked)} /> Unresolved only</label>
      </div>
      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full text-left text-xs">
          <thead className="bg-panel text-muted">
            <tr>{["Squawk", "Aircraft", "Callsign", "First seen (UTC)", "Duration", "Observations", "Last known position", "Severity", "Status", ""].map((h) => <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {data?.items.map((e) => (
              <tr key={e.anomaly_id} className="border-t border-line align-top">
                <td className="px-2 py-2 font-mono font-semibold">{e.squawk}<div className="text-[11px] font-normal text-muted">{e.meaning}</div></td>
                <td className="px-2 font-mono"><Link className="underline" to={`/aircraft/${e.icao24}`}>{e.icao24}</Link><div className="text-[11px] text-muted">{e.registration ?? ""}</div></td>
                <td className="px-2 font-mono">{orDash(e.callsign)}</td>
                <td className="whitespace-nowrap px-2">{fmtTime(e.first_seen)}</td>
                <td className="px-2">{fmtDuration(e.duration_s)}{e.transient && <div className="text-[11px] text-sev-medium">single observation: possibly transient</div>}</td>
                <td className="px-2 font-mono">{e.observations}</td>
                <td className="px-2 font-mono">{e.last_known_position ? `${e.last_known_position.lat.toFixed(3)}, ${e.last_known_position.lon.toFixed(3)}` : "not available"}</td>
                <td className="px-2"><SeverityBadge severity={e.severity} /></td>
                <td className="px-2"><WorkflowBadge status={e.status} /></td>
                <td className="px-2"><Link className="rounded bg-accent/20 px-2 py-1 text-accent" to={`/anomalies/${e.anomaly_id}`}>Details</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <p className="p-4 text-sm text-muted">No emergency squawk events in stored data.</p>}
      </div>
    </section>
  );
}
