import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AiPanel } from "../components/AiPanel";
import { ReportButton } from "../components/ReportButton";
import { Field, Stat } from "../components/Field";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { TrackCharts } from "../components/TrackCharts";
import { TrackMap } from "../components/TrackMap";
import { useAircraft, useAircraftSearch, useHistory, useTrajectory, type Range } from "../hooks/useAviation";
import { fmtAlt, fmtDistance, fmtDuration, fmtSpeed, fmtTime, fmtVRate, orDash } from "../utils/format";

const SEARCH = /^[A-Za-z0-9-]{0,16}$/;

function SearchPanel({ selected }: { selected?: string }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(id);
  }, [q]);
  const valid = SEARCH.test(debounced);
  const { data, error, isFetching } = useAircraftSearch(valid ? debounced : "");
  return (
    <aside className="w-full shrink-0 lg:w-72">
      <input
        aria-label="Search aircraft"
        placeholder="ICAO24, registration or callsign"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full rounded border border-line bg-panel px-3 py-2 text-sm"
      />
      {!valid && <p className="mt-1 text-xs text-sev-medium">Use letters, digits and “-” only (max 16).</p>}
      <ErrorNote error={error} />
      <ul className="mt-2 divide-y divide-line rounded border border-line bg-panel">
        {data?.items.map((a) => (
          <li key={a.icao24}>
            <Link to={`/aircraft/${a.icao24}`} className={`block px-3 py-2 text-sm hover:bg-line ${a.icao24 === selected ? "bg-accent/15" : ""}`}>
              <span className="font-mono">{a.icao24}</span>{" "}
              <span className="text-slate-300">{a.last_callsign ?? ""}</span>
              <div className="text-xs text-muted">{[a.registration, a.aircraft_type, a.origin_country].filter(Boolean).join(" · ") || "no metadata"}</div>
            </Link>
          </li>
        ))}
        {data && data.items.length === 0 && <li className="px-3 py-2 text-sm text-muted">No matching aircraft in stored data.</li>}
      </ul>
      {data && <p className="mt-1 text-xs text-muted">{data.total} match{data.total === 1 ? "" : "es"}{isFetching ? " · updating…" : ""}</p>}
    </aside>
  );
}

const toIso = (local: string) => (local ? `${local}:00Z` : undefined);

function RangePicker({ onChange }: { onChange: (r: Range) => void }) {
  const [s, setS] = useState("");
  const [e, setE] = useState("");
  const bad = s && e && s >= e;
  return (
    <form
      className="flex flex-wrap items-end gap-3 text-xs"
      onSubmit={(ev) => {
        ev.preventDefault();
        if (!bad) onChange({ start: toIso(s), end: toIso(e) });
      }}
    >
      <label>
        <div className="text-muted">From (UTC)</div>
        <input type="datetime-local" value={s} onChange={(ev) => setS(ev.target.value)} className="rounded border border-line bg-ink px-2 py-1" />
      </label>
      <label>
        <div className="text-muted">To (UTC)</div>
        <input type="datetime-local" value={e} onChange={(ev) => setE(ev.target.value)} className="rounded border border-line bg-ink px-2 py-1" />
      </label>
      <button className="rounded bg-accent/20 px-3 py-1 text-accent" disabled={!!bad}>Apply</button>
      <button type="button" className="rounded px-3 py-1 text-muted underline" onClick={() => { setS(""); setE(""); onChange({}); }}>Full history</button>
      {bad && <span className="text-sev-critical">“From” must be earlier than “To”.</span>}
    </form>
  );
}

function Detail({ icao24 }: { icao24: string }) {
  const [range, setRange] = useState<Range>({});
  const [offset, setOffset] = useState(0);
  const ac = useAircraft(icao24);
  const traj = useTrajectory(icao24, range);
  const hist = useHistory(icao24, range, offset);
  useEffect(() => {
    setOffset(0);
  }, [icao24, range]);
  const a = ac.data;
  const sm = traj.data?.summary;

  return (
    <div className="min-w-0 flex-1 space-y-4">
      <ErrorNote error={ac.error} />
      {a && (
        <section className="rounded border border-line bg-panel p-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h1 className="text-lg font-semibold flex items-center gap-2">
              <span className="font-mono text-accent">{a.icao24.toUpperCase()}</span>{" "}
              <span className="text-slate-300">{a.last_callsign ?? ""}</span>
              {a.category && (
                <span className="rounded bg-sky-500/10 border border-sky-500/30 px-2 py-0.5 text-xs font-mono text-sky-400">
                  {a.category}
                </span>
              )}
            </h1>
            <div className="flex items-center gap-2">
              <Link
                to={`/trajectories?icao24=${a.icao24}`}
                className="rounded border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-semibold text-accent hover:bg-accent/20"
              >
                Kinematic Trajectory &rarr;
              </Link>
              <Link
                to={`/investigations`}
                className="rounded border border-line bg-card px-2.5 py-1 text-xs text-slate-300 hover:border-slate-500"
              >
                Investigate Case
              </Link>
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Field label="Registration" value={a.registration} hint="From the aircraft database, never inferred" />
            <Field label="Type" value={a.aircraft_type} />
            <Field label="Manufacturer / model" value={[a.manufacturer, a.model].filter(Boolean).join(" ") || null} />
            <Field label="Operator" value={a.operator} />
            <Field label="Origin country" value={a.origin_country} hint="Country of ICAO registration block, as reported" />
            <Field label="First seen" value={fmtTime(a.first_seen)} />
            <Field label="Last seen" value={fmtTime(a.last_seen)} />
            <Field label="Observations" value={`${a.observation_count.toLocaleString()} (${a.positioned_count.toLocaleString()} with position)`} />
          </dl>
          <p className="mt-3 text-xs text-muted">
            Provenance — observations: {a.observation_sources.join(", ") || "none"} · metadata: {a.metadata_source ?? "none (fields left blank)"}.
            Callsigns seen: {a.callsigns.join(", ") || "—"}.
          </p>
          {a.squawks.length > 0 && (
            <p className="mt-1 text-xs text-muted">
              Squawk history: {a.squawks.map((s) => `${s.squawk} ×${s.observations}`).join(", ")}
            </p>
          )}
        </section>
      )}

      {a && <AiPanel kind="aircraft" subject={a.icao24} />}
      {a && <ReportButton subject={{ icao24: a.icao24 }} />}

      <RangePicker onChange={setRange} />
      <ErrorNote error={traj.error} />
      {sm && (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Stat label="Positions" value={sm.points.toLocaleString()} />
            <Stat label="Duration" value={fmtDuration(sm.duration_s)} />
            <Stat label="Observed distance" value={fmtDistance(sm.observed_distance_m)} />
            <Stat label="Median interval" value={sm.median_interval_s == null ? "—" : `${sm.median_interval_s.toFixed(1)} s`} />
            <Stat label="Altitude range" value={sm.min_baro_altitude_m == null ? "—" : `${Math.round(sm.min_baro_altitude_m)}–${Math.round(sm.max_baro_altitude_m!)} m`} />
            <Stat label="Max reported speed" value={fmtSpeed(sm.max_reported_speed_ms)} />
            <Stat label="Observation gaps" value={`${sm.gap_count} (${fmtDuration(sm.gap_total_s)})`} />
            <Stat label="Longest gap" value={fmtDuration(sm.longest_gap_s)} />
          </div>
          <TrackMap trajectory={traj.data} className="h-[420px]" />
          <TrackCharts trajectory={traj.data!} />
          <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
            {traj.data!.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        </>
      )}
      {sm && sm.points === 0 && <p className="text-sm text-muted">No positions in this range.</p>}

      <section>
        <h2 className="mb-2 text-sm font-semibold">Observation timeline</h2>
        <ErrorNote error={hist.error} />
        <div className="overflow-x-auto rounded border border-line">
          <table className="w-full text-left text-xs">
            <thead className="bg-panel text-muted">
              <tr>
                {["Time (UTC)", "Callsign", "Lat", "Lon", "Baro alt", "Reported speed", "Heading", "V/rate (reported)", "Squawk", "Source", "Data issues"].map((h) => (
                  <th key={h} className="whitespace-nowrap px-2 py-1.5 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono">
              {hist.data?.items.map((o) => (
                <tr key={o.id} className="border-t border-line">
                  <td className="whitespace-nowrap px-2 py-1">{fmtTime(o.observed_at)}</td>
                  <td className="px-2">{orDash(o.callsign)}</td>
                  <td className="px-2">{o.lat?.toFixed(4) ?? "—"}</td>
                  <td className="px-2">{o.lon?.toFixed(4) ?? "—"}</td>
                  <td className="whitespace-nowrap px-2">{fmtAlt(o.baro_altitude_m)}</td>
                  <td className="whitespace-nowrap px-2">{fmtSpeed(o.velocity_ms)}</td>
                  <td className="px-2">{o.heading_deg?.toFixed(0) ?? "—"}</td>
                  <td className="whitespace-nowrap px-2">{fmtVRate(o.vertical_rate_ms)}</td>
                  <td className="px-2">{orDash(o.squawk)}</td>
                  <td className="px-2">{o.source}</td>
                  <td className="px-2 text-sev-medium">{o.validation_issues.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {hist.data && (
          <div className="mt-2 flex items-center gap-3 text-xs text-muted">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))} className="rounded border border-line px-2 py-1 disabled:opacity-40">Newer</button>
            <span>{hist.data.total === 0 ? 0 : offset + 1}–{Math.min(offset + 50, hist.data.total)} of {hist.data.total.toLocaleString()} (newest first)</span>
            <button disabled={offset + 50 >= hist.data.total} onClick={() => setOffset(offset + 50)} className="rounded border border-line px-2 py-1 disabled:opacity-40">Older</button>
          </div>
        )}
      </section>
    </div>
  );
}

export function AircraftPage() {
  const { icao24 } = useParams();
  const nav = useNavigate();
  useEffect(() => {
    if (icao24 && !/^[0-9a-fA-F]{6}$/.test(icao24)) nav("/aircraft", { replace: true });
  }, [icao24, nav]);
  return (
    <section>
      <h1 className="sr-only">Aircraft Intelligence</h1>
      <NeedsToken />
      <div className="mt-2 flex flex-col gap-4 lg:flex-row">
        <SearchPanel selected={icao24} />
        {icao24 && /^[0-9a-fA-F]{6}$/.test(icao24) ? (
          <Detail icao24={icao24.toLowerCase()} />
        ) : (
          <p className="text-sm text-muted">Search for an aircraft by ICAO24 address, registration or callsign.</p>
        )}
      </div>
    </section>
  );
}
