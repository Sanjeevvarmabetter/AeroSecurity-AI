import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Trajectory } from "../types/aviation";
import { thin } from "../utils/geojson";

const MAX_POINTS = 1500;
const AX = { stroke: "#8a97ad", fontSize: 11 };
const GRID = "#1f2b42";
const hhmm = (t: number) => new Date(t).toISOString().slice(11, 16);

function Frame({ title, note, footer, children }: { title: string; note?: string; footer?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded border border-line bg-panel p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">{title}</h3>
        {note && <span className="text-[11px] text-muted">{note}</span>}
      </div>
      <div className="h-56">{children}</div>
      {footer}
    </div>
  );
}

export function TrackCharts({ trajectory }: { trajectory: Trajectory }) {
  const [hideSubSecond, setHide] = useState(true);
  const alt = thin(trajectory.points, MAX_POINTS).map((p) => ({
    t: Date.parse(p.t), baro: p.baro_altitude_m, geo: p.geo_altitude_m,
  }));
  const reported = thin(trajectory.points, MAX_POINTS).map((p) => ({ t: Date.parse(p.t), v: p.reported_velocity_ms }));
  const derived = thin(
    trajectory.segments.filter((s) => !s.is_gap && s.derived_speed_ms != null && (!hideSubSecond || s.dt_s >= 1)),
    MAX_POINTS,
  ).map((s) => ({ t: Date.parse(s.end), d: s.derived_speed_ms }));
  const speed = [...reported.map((r) => ({ t: r.t, reported: r.v })), ...derived.map((d) => ({ t: d.t, derived: d.d }))]
    .sort((a, b) => a.t - b.t);
  const shown = (a: unknown[]) => (a.length >= MAX_POINTS ? "thinned for display" : undefined);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Frame title="Altitude (m)" note={shown(alt)}>
        <ResponsiveContainer>
          <LineChart data={alt}>
            <CartesianGrid stroke={GRID} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={hhmm} {...AX} />
            <YAxis {...AX} width={50} />
            <Tooltip labelFormatter={(t) => new Date(Number(t)).toISOString().replace("T", " ").slice(0, 19) + " UTC"}
              contentStyle={{ background: "#111a2b", border: "1px solid #1f2b42" }} />
            <Legend />
            <Line dataKey="baro" name="barometric" stroke="#4c8dff" dot={false} connectNulls={false} isAnimationActive={false} />
            <Line dataKey="geo" name="geometric" stroke="#22c55e" dot={false} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Frame>
      <Frame title="Speed (m/s): reported vs derived from positions" note={shown(speed)} footer={
        <label className="mt-2 flex items-start gap-2 text-[11px] text-muted">
          <input type="checkbox" className="mt-0.5" checked={hideSubSecond} onChange={(e) => setHide(e.target.checked)} />
          Hide intervals shorter than 1 s (position timestamps jitter there, so derived speed is unreliable)
        </label>
      }>
        <ResponsiveContainer>
          <LineChart data={speed}>
            <CartesianGrid stroke={GRID} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={hhmm} {...AX} />
            <YAxis {...AX} width={50} />
            <Tooltip labelFormatter={(t) => new Date(Number(t)).toISOString().replace("T", " ").slice(0, 19) + " UTC"}
              contentStyle={{ background: "#111a2b", border: "1px solid #1f2b42" }} />
            <Legend />
            <Line dataKey="reported" name="reported (ADS-B)" stroke="#4c8dff" dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="derived" name="derived (displacement/Δt)" stroke="#f97316" dot={false} strokeWidth={1} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Frame>
    </div>
  );
}
