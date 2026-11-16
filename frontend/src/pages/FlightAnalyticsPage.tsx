import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { getFleetAnalytics } from "../services/api";

const COLORS = ["#38bdf8", "#818cf8", "#c084fc", "#e879f9", "#f472b6", "#fb7185"];

export function FlightAnalyticsPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["fleet-analytics"],
    queryFn: getFleetAnalytics,
  });

  return (
    <section className="space-y-6">
      <div className="border-b border-line/60 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
          <span>Flight & Fleet Analytics</span>
          <span className="rounded bg-accent/15 px-2 py-0.5 text-xs font-mono text-accent">
            KINEMATICS
          </span>
        </h1>
        <p className="mt-1 text-xs text-muted">
          Statistical distribution of reported flight dynamics, flight level envelopes, and fleet aircraft categorizations.
        </p>
      </div>

      <NeedsToken />
      <ErrorNote error={error} />

      {isLoading && (
        <div className="flex h-64 items-center justify-center rounded border border-line bg-panel">
          <div className="flex flex-col items-center gap-2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-xs font-mono text-muted">Analyzing flight parameter distributions...</span>
          </div>
        </div>
      )}

      {data && (
        <>
          {/* Top Flight State Summary */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded border border-line bg-panel p-4">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Airborne Fixes
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-accent">
                {data.airborne_count.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted">active in flight</div>
            </div>

            <div className="rounded border border-line bg-panel p-4">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                On Ground Fixes
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-slate-300">
                {data.on_ground_count.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted">taxiing or parked</div>
            </div>

            <div className="rounded border border-line bg-panel p-4">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Airborne Ratio
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-ok">
                {(
                  (data.airborne_count / (data.airborne_count + data.on_ground_count || 1)) *
                  100
                ).toFixed(1)}
                %
              </div>
              <div className="mt-1 text-[10px] text-muted">airborne telemetry share</div>
            </div>

            <div className="rounded border border-line bg-panel p-4">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Aircraft Categories
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-white">
                {data.category_distribution.length}
              </div>
              <div className="mt-1 text-[10px] text-muted">distinct type classes</div>
            </div>
          </div>

          {/* Histograms: Altitudes & Ground Speeds */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Altitude Distribution Chart */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <div className="mb-4">
                <h2 className="text-sm font-bold text-white">Barometric Altitude Distribution</h2>
                <p className="text-[11px] text-muted">
                  Histogram of aircraft observation altitude bands (metres & Flight Level estimates)
                </p>
              </div>

              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.altitude_distribution}>
                    <CartesianGrid stroke="#1e2f4d" strokeDasharray="3 3" />
                    <XAxis dataKey="label" stroke="#7e8da6" fontSize={11} tickLine={false} />
                    <YAxis stroke="#7e8da6" fontSize={11} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: "#0d1524", borderColor: "#1e2f4d", borderRadius: 4, fontSize: 12 }}
                      labelStyle={{ color: "#38bdf8", fontWeight: "bold" }}
                      formatter={(val: any) => [Number(val).toLocaleString(), "Observations"]}
                    />
                    <Bar dataKey="count" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Speed Distribution Chart */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <div className="mb-4">
                <h2 className="text-sm font-bold text-white">Reported Ground Speed Distribution</h2>
                <p className="text-[11px] text-muted">
                  Histogram of reported horizontal velocity (m/s & knots equivalent)
                </p>
              </div>

              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.speed_distribution}>
                    <CartesianGrid stroke="#1e2f4d" strokeDasharray="3 3" />
                    <XAxis dataKey="label" stroke="#7e8da6" fontSize={11} tickLine={false} />
                    <YAxis stroke="#7e8da6" fontSize={11} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: "#0d1524", borderColor: "#1e2f4d", borderRadius: 4, fontSize: 12 }}
                      labelStyle={{ color: "#38bdf8", fontWeight: "bold" }}
                      formatter={(val: any) => [Number(val).toLocaleString(), "Observations"]}
                    />
                    <Bar dataKey="count" fill="#818cf8" radius={[4, 4, 0, 0]}>
                      {data.speed_distribution.map((_, i) => (
                        <Cell key={`cell-${i}`} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Categories and Fleet Manufacturers */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Categories Card */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <h2 className="text-sm font-bold text-white mb-3">Fleet Composition by Aircraft Category</h2>
              <div className="space-y-3">
                {data.category_distribution.map((cat) => {
                  const total = data.category_distribution.reduce((acc, c) => acc + c.count, 0);
                  const pct = (cat.count / (total || 1)) * 100;
                  return (
                    <div key={cat.category} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-200">{cat.category}</span>
                        <span className="font-mono text-muted">
                          {cat.count} aircraft ({pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-subpanel">
                        <div
                          className="h-full bg-accent transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Top Manufacturers */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <h2 className="text-sm font-bold text-white mb-3">Top Identified Airframe Manufacturers</h2>
              <div className="space-y-2">
                {data.top_manufacturers.map((m) => (
                  <div key={m.manufacturer} className="flex items-center justify-between rounded bg-subpanel p-2.5 text-xs">
                    <span className="font-medium text-slate-200">{m.manufacturer}</span>
                    <span className="rounded bg-accent/20 px-2 py-0.5 font-mono font-semibold text-accent">
                      {m.count} aircraft
                    </span>
                  </div>
                ))}
                {data.top_manufacturers.length === 0 && (
                  <p className="text-xs text-muted">No manufacturer metadata registered in active dataset.</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
