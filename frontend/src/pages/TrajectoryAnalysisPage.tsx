import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useTrajectory } from "../hooks/useAviation";
import { fmtDistance, fmtSpeed, fmtTime } from "../utils/format";

const PRESETS = [
  { icao24: "440604", label: "OS82 (Austrian A320 - Squawk 7700)" },
  { icao24: "a9ab17", label: "N722BD (Learjet 55 - Extreme Dive)" },
  { icao24: "aceb1b", label: "N931TT (PA-46 - Speed Exceedance)" },
  { icao24: "a001a1", label: "XAUCI (Incident Analysis)" },
  { icao24: "8964e5", label: "FZ1073 (FlyDubai B738)" },
];

export function TrajectoryAnalysisPage() {
  const [sp, setSp] = useSearchParams();
  const selectedIcao = sp.get("icao24") || "440604";
  const [inputIcao, setInputIcao] = useState(selectedIcao);
  const gapThreshold = 120;

  const { data: traj, error, isLoading } = useTrajectory(selectedIcao, { gap_s: gapThreshold });

  const handleSelect = (icao: string) => {
    setSp({ icao24: icao });
    setInputIcao(icao);
  };

  // Prepare chart series comparing derived vs reported
  const chartData = (traj?.segments || [])
    .filter((s) => !s.is_gap && s.derived_speed_ms !== null)
    .slice(0, 300)
    .map((s, idx) => ({
      index: idx,
      time: s.start.slice(11, 19),
      derived_speed: s.derived_speed_ms !== null ? Math.round(s.derived_speed_ms) : null,
      reported_speed: s.reported_speed_ms !== null ? Math.round(s.reported_speed_ms) : null,
      derived_vrate: s.derived_vertical_rate_ms != null ? Math.round(s.derived_vertical_rate_ms * 10) / 10 : null,
      reported_vrate: s.reported_vertical_rate_ms != null ? Math.round(s.reported_vertical_rate_ms * 10) / 10 : null,
      acceleration: s.derived_acceleration_ms2 != null ? Math.round(s.derived_acceleration_ms2 * 10) / 10 : null,
      bearing: s.derived_bearing_deg != null ? Math.round(s.derived_bearing_deg) : null,
    }));

  return (
    <section className="space-y-6">
      {/* Header */}
      <div className="border-b border-line/60 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
          <span>Trajectory Analytics Engine</span>
          <span className="rounded bg-accent/15 px-2 py-0.5 text-xs font-mono text-accent">
            GEODESIC & KINEMATICS
          </span>
        </h1>
        <p className="mt-1 text-xs text-muted">
          High-precision comparison of provider-reported flight parameters versus derived geospatial displacement and altitude differentials.
        </p>
      </div>

      <NeedsToken />
      <ErrorNote error={error} />

      {/* Target Selector Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-line bg-panel p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-muted">Target Aircraft:</span>
          {PRESETS.map((p) => (
            <button
              key={p.icao24}
              onClick={() => handleSelect(p.icao24)}
              className={`rounded px-2.5 py-1 text-xs font-mono transition-all ${
                selectedIcao === p.icao24
                  ? "border border-accent bg-accent/20 font-bold text-accent"
                  : "border border-line bg-subpanel text-slate-300 hover:bg-line"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (/^[0-9a-fA-F]{6}$/.test(inputIcao)) handleSelect(inputIcao.toLowerCase());
          }}
          className="flex items-center gap-2"
        >
          <input
            value={inputIcao}
            onChange={(e) => setInputIcao(e.target.value)}
            placeholder="Custom ICAO24"
            className="w-28 rounded border border-line bg-ink px-2 py-1 font-mono text-xs uppercase text-white"
            maxLength={6}
          />
          <button className="rounded border border-line bg-subpanel px-3 py-1 text-xs hover:border-accent hover:text-accent">
            Load
          </button>
        </form>
      </div>

      {isLoading && (
        <div className="flex h-64 items-center justify-center rounded border border-line bg-panel">
          <div className="flex flex-col items-center gap-2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-xs font-mono text-muted">Calculating geodesic trajectories...</span>
          </div>
        </div>
      )}

      {traj && (
        <>
          {/* Kinematic Summary Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded border border-line bg-panel p-3">
              <div className="text-[10px] font-semibold uppercase text-muted">Observed Points</div>
              <div className="mt-1 font-mono text-xl font-bold text-white">
                {traj.summary.points.toLocaleString()}
              </div>
              <div className="text-[10px] text-muted">{traj.summary.segments} segments</div>
            </div>

            <div className="rounded border border-line bg-panel p-3">
              <div className="text-[10px] font-semibold uppercase text-muted">Continuous Distance</div>
              <div className="mt-1 font-mono text-xl font-bold text-accent">
                {fmtDistance(traj.summary.observed_distance_m)}
              </div>
              <div className="text-[10px] text-muted">gaps excluded</div>
            </div>

            <div className="rounded border border-line bg-panel p-3">
              <div className="text-[10px] font-semibold uppercase text-muted">Max Derived Speed</div>
              <div className="mt-1 font-mono text-xl font-bold text-slate-200">
                {fmtSpeed(traj.summary.max_derived_speed_ms)}
              </div>
              <div className="text-[10px] text-muted">ground displacement</div>
            </div>

            <div className="rounded border border-line bg-panel p-3">
              <div className="text-[10px] font-semibold uppercase text-muted">Max Reported Speed</div>
              <div className="mt-1 font-mono text-xl font-bold text-slate-200">
                {fmtSpeed(traj.summary.max_reported_speed_ms)}
              </div>
              <div className="text-[10px] text-muted">transponder velocity</div>
            </div>

            <div className="rounded border border-line bg-panel p-3">
              <div className="text-[10px] font-semibold uppercase text-muted">Max Acceleration</div>
              <div className="mt-1 font-mono text-xl font-bold text-sev-medium">
                {traj.summary.max_acceleration_ms2 !== null && traj.summary.max_acceleration_ms2 !== undefined
                  ? `${traj.summary.max_acceleration_ms2.toFixed(1)} m/s²`
                  : "—"}
              </div>
              <div className="text-[10px] text-muted">dv / dt</div>
            </div>

            <div className="rounded border border-line bg-panel p-3">
              <div className="text-[10px] font-semibold uppercase text-muted">Observation Gaps</div>
              <div className="mt-1 font-mono text-xl font-bold text-sev-high">
                {traj.summary.gap_count}
              </div>
              <div className="text-[10px] text-muted">longest: {traj.summary.longest_gap_s.toFixed(0)} s</div>
            </div>
          </div>

          {/* Critical Aviation Engineering Callout */}
          <div className="rounded border border-accent/40 bg-accent/5 p-3.5 text-xs">
            <span className="font-bold text-accent">Engineering Separation Notice:</span>{" "}
            <span className="text-slate-300">
              Provider-reported velocity (v_rep) and derived displacement speed (d / Δt) are strictly decoupled.
              A divergence between these two parameters is an explicit signature of sensor delay, severe headwinds/tails, or spoofed ADS-B positioning.
            </span>
          </div>

          {/* Kinematic Charts */}
          <div className="space-y-6">
            {/* Chart 1: Ground Speed vs Derived Speed */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold text-white">
                    Ground Speed Dynamics: Derived Displacement vs. Reported Velocity
                  </h2>
                  <p className="text-[11px] text-muted">
                    Blue: Derived Speed (d / Δt) · Violet: Reported Broadcast Velocity (v_rep) in metres/second
                  </p>
                </div>
              </div>

              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid stroke="#1e2f4d" strokeDasharray="3 3" />
                    <XAxis dataKey="time" stroke="#7e8da6" fontSize={10} tickLine={false} />
                    <YAxis stroke="#7e8da6" fontSize={10} tickLine={false} unit=" m/s" />
                    <Tooltip
                      contentStyle={{ background: "#0d1524", borderColor: "#1e2f4d", borderRadius: 4, fontSize: 11 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line
                      type="monotone"
                      dataKey="derived_speed"
                      name="Derived Speed (m/s)"
                      stroke="#38bdf8"
                      dot={false}
                      strokeWidth={1.5}
                    />
                    <Line
                      type="monotone"
                      dataKey="reported_speed"
                      name="Reported Speed (m/s)"
                      stroke="#c084fc"
                      dot={false}
                      strokeWidth={1.5}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 2: Vertical Rate Comparison & Acceleration */}
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded border border-line bg-panel p-4 shadow-sm">
                <h2 className="text-sm font-bold text-white mb-1">
                  Vertical Rate: Derived Climb/Descent vs. Broadcast
                </h2>
                <p className="text-[11px] text-muted mb-3">
                  Cyan: Altitude Differential ($\Delta h / \Delta t$) · Amber: Reported Vertical Rate
                </p>
                <div className="h-56 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid stroke="#1e2f4d" strokeDasharray="3 3" />
                      <XAxis dataKey="time" stroke="#7e8da6" fontSize={10} tickLine={false} />
                      <YAxis stroke="#7e8da6" fontSize={10} tickLine={false} unit=" m/s" />
                      <Tooltip
                        contentStyle={{ background: "#0d1524", borderColor: "#1e2f4d", borderRadius: 4, fontSize: 11 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="derived_vrate"
                        name="Derived V-Rate"
                        stroke="#38bdf8"
                        dot={false}
                        strokeWidth={1.5}
                      />
                      <Line
                        type="monotone"
                        dataKey="reported_vrate"
                        name="Reported V-Rate"
                        stroke="#eab308"
                        dot={false}
                        strokeWidth={1.5}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded border border-line bg-panel p-4 shadow-sm">
                <h2 className="text-sm font-bold text-white mb-1">
                  Kinematic Acceleration Profile (m/s²)
                </h2>
                <p className="text-[11px] text-muted mb-3">
                  Rate of velocity change between consecutive observation fixes
                </p>
                <div className="h-56 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid stroke="#1e2f4d" strokeDasharray="3 3" />
                      <XAxis dataKey="time" stroke="#7e8da6" fontSize={10} tickLine={false} />
                      <YAxis stroke="#7e8da6" fontSize={10} tickLine={false} unit=" m/s²" />
                      <Tooltip
                        contentStyle={{ background: "#0d1524", borderColor: "#1e2f4d", borderRadius: 4, fontSize: 11 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="acceleration"
                        name="Acceleration (m/s²)"
                        stroke="#f97316"
                        dot={false}
                        strokeWidth={1.5}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>

          {/* Segment Data Table */}
          <div className="rounded border border-line bg-panel p-4 shadow-sm">
            <h2 className="text-sm font-bold text-white mb-3">
              Consecutive Segment Records (First 50 Segments)
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-subpanel text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">Timestamp (UTC)</th>
                    <th className="px-3 py-2 font-medium">Δt (s)</th>
                    <th className="px-3 py-2 font-medium">Distance</th>
                    <th className="px-3 py-2 font-medium">Derived Speed</th>
                    <th className="px-3 py-2 font-medium">Reported Speed</th>
                    <th className="px-3 py-2 font-medium">Δ Alt (Baro)</th>
                    <th className="px-3 py-2 font-medium">Derived V-Rate</th>
                    <th className="px-3 py-2 font-medium">Bearing</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60 font-mono">
                  {traj.segments.slice(0, 50).map((s, idx) => (
                    <tr key={idx} className={s.is_gap ? "bg-sev-medium/10 text-sev-medium" : "hover:bg-subpanel/50"}>
                      <td className="whitespace-nowrap px-3 py-1.5">{fmtTime(s.start)}</td>
                      <td className="px-3 py-1.5">{s.dt_s.toFixed(1)}</td>
                      <td className="px-3 py-1.5">{fmtDistance(s.distance_m)}</td>
                      <td className="px-3 py-1.5">{s.derived_speed_ms !== null ? fmtSpeed(s.derived_speed_ms) : "—"}</td>
                      <td className="px-3 py-1.5">{s.reported_speed_ms !== null ? fmtSpeed(s.reported_speed_ms) : "—"}</td>
                      <td className="px-3 py-1.5">{s.baro_delta_m !== null ? `${s.baro_delta_m.toFixed(0)} m` : "—"}</td>
                      <td className="px-3 py-1.5">{s.derived_vertical_rate_ms !== null ? `${s.derived_vertical_rate_ms.toFixed(1)} m/s` : "—"}</td>
                      <td className="px-3 py-1.5">{s.derived_bearing_deg !== null && s.derived_bearing_deg !== undefined ? `${s.derived_bearing_deg.toFixed(0)}°` : "—"}</td>
                      <td className="px-3 py-1.5">
                        {s.is_gap ? (
                          <span className="rounded bg-sev-medium/20 px-1.5 py-0.5 text-[10px] font-bold text-sev-medium">
                            GAP
                          </span>
                        ) : (
                          <span className="rounded bg-ok/20 px-1.5 py-0.5 text-[10px] font-bold text-ok">
                            CONTINUOUS
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
