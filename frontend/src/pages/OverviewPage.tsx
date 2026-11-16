import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { SeverityBadge } from "../components/Badges";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { getOverviewAnalytics } from "../services/api";
import { fmtTime } from "../utils/format";

export function OverviewPage() {
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["overview-analytics"],
    queryFn: getOverviewAnalytics,
    refetchInterval: 15_000,
  });

  return (
    <section className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line/60 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>Mission Operations Dashboard</span>
            <span className="rounded bg-accent/15 px-2 py-0.5 text-xs font-mono text-accent">
              REAL-TIME
            </span>
          </h1>
          <p className="mt-1 text-xs text-muted">
            Global airspace intelligence, deterministic anomaly telemetry, and cyber-physical surveillance.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 rounded border border-line bg-subpanel px-3 py-1.5 text-xs text-slate-300 hover:border-accent hover:text-accent transition-all"
          >
            <span>🔄</span> Refresh Telemetry
          </button>
          <Link
            to="/radar"
            className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-ink shadow-md hover:bg-accent/90 transition-all"
          >
            Launch Live Radar →
          </Link>
        </div>
      </div>

      <NeedsToken />
      <ErrorNote error={error} />

      {isLoading && (
        <div className="flex h-64 items-center justify-center rounded border border-line bg-panel">
          <div className="flex flex-col items-center gap-2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-xs font-mono text-muted">Aggregating platform telemetry...</span>
          </div>
        </div>
      )}

      {data && (
        <>
          {/* Top Mission Metrics Grid */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded border border-line bg-panel p-3.5 shadow-sm">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Active In Airspace
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-white">
                {data.active_aircraft.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted">within snapshot window</div>
            </div>

            <div className="rounded border border-line bg-panel p-3.5 shadow-sm">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Total Fleet Tracked
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-white">
                {data.total_aircraft.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted">identified ICAO24 targets</div>
            </div>

            <div className="rounded border border-line bg-panel p-3.5 shadow-sm">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Total Observations
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-accent">
                {data.total_observations.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted">spatial ADS-B records</div>
            </div>

            <div className="rounded border border-line bg-panel p-3.5 shadow-sm">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Detected Anomalies
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-sev-high">
                {data.total_anomalies.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted">deterministic rule hits</div>
            </div>

            <div className="rounded border border-line bg-panel p-3.5 shadow-sm">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Emergency Squawks
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-sev-critical flex items-center gap-1">
                <span>{data.emergency_squawks}</span>
                {data.emergency_squawks > 0 && (
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sev-critical opacity-75"></span>
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sev-critical"></span>
                  </span>
                )}
              </div>
              <div className="mt-1 text-[10px] text-muted">7500 / 7600 / 7700</div>
            </div>

            <div className="rounded border border-line bg-panel p-3.5 shadow-sm">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                Global Airports
              </div>
              <div className="mt-1 font-mono text-2xl font-bold text-slate-300">
                {data.total_airports.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted">indexed with PostGIS</div>
            </div>
          </div>

          {/* Severity & Threat Breakdown Banners */}
          <div className="grid gap-4 lg:grid-cols-3">
            {/* Severity Distribution */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <h2 className="text-xs font-bold uppercase tracking-wider text-muted mb-3 flex items-center justify-between">
                <span>Anomaly Severity Breakdown</span>
                <Link to="/anomalies" className="text-accent hover:underline lowercase font-normal">view all →</Link>
              </h2>
              <div className="space-y-2.5">
                {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((s) => {
                  const count = data.by_severity[s] || 0;
                  const pct = data.total_anomalies ? (count / data.total_anomalies) * 100 : 0;
                  const color =
                    s === "CRITICAL"
                      ? "bg-sev-critical"
                      : s === "HIGH"
                      ? "bg-sev-high"
                      : s === "MEDIUM"
                      ? "bg-sev-medium"
                      : "bg-sev-low";

                  return (
                    <div key={s} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <SeverityBadge severity={s} />
                        <span className="font-mono text-slate-300">
                          {count} ({pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-subpanel">
                        <div
                          className={`h-full ${color} transition-all duration-500`}
                          style={{ width: `${Math.max(pct, count > 0 ? 3 : 0)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Event Category Breakdown */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <h2 className="text-xs font-bold uppercase tracking-wider text-muted mb-3">
                Detection Categories
              </h2>
              <div className="space-y-2">
                {Object.entries(data.by_detection_type).map(([cat, count]) => (
                  <div key={cat} className="flex items-center justify-between rounded bg-subpanel px-3 py-2 text-xs">
                    <span className="font-mono text-slate-300">{cat.replace("_", " ")}</span>
                    <span className="rounded bg-accent/20 px-2 py-0.5 font-mono font-semibold text-accent">
                      {count}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Top Fleet Aircraft Types */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <h2 className="text-xs font-bold uppercase tracking-wider text-muted mb-3 flex items-center justify-between">
                <span>Top Aircraft Types</span>
                <Link to="/analytics" className="text-accent hover:underline lowercase font-normal">fleet details →</Link>
              </h2>
              <div className="grid grid-cols-2 gap-2">
                {data.top_aircraft_types.map((t) => (
                  <div key={t.type} className="rounded border border-line/60 bg-subpanel p-2.5 text-center">
                    <div className="font-mono text-sm font-bold text-white">{t.type}</div>
                    <div className="text-[10px] text-muted">{t.count} target{t.count === 1 ? "" : "s"}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Recent Anomalies & Data Sources Section */}
          <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
            {/* Recent Anomaly Feed */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-bold tracking-tight text-white flex items-center gap-2">
                  <span>Recent Anomaly Feed</span>
                  <span className="rounded-full bg-sev-high/20 px-2 py-0.2 text-[10px] font-mono text-sev-high">
                    LATEST 6
                  </span>
                </h2>
                <Link to="/anomalies" className="text-xs text-accent hover:underline">
                  View Anomaly Center →
                </Link>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-subpanel text-muted">
                    <tr>
                      <th className="px-3 py-2 font-medium">Anomaly ID</th>
                      <th className="px-3 py-2 font-medium">Severity</th>
                      <th className="px-3 py-2 font-medium">Rule</th>
                      <th className="px-3 py-2 font-medium">Finding Title</th>
                      <th className="px-3 py-2 font-medium">Aircraft</th>
                      <th className="px-3 py-2 font-medium">Detected</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/60">
                    {data.recent_anomalies.map((anom) => (
                      <tr key={anom.id} className="hover:bg-subpanel/50 transition-colors">
                        <td className="px-3 py-2 font-mono font-semibold">
                          <Link to={`/anomalies/${anom.id}`} className="text-accent hover:underline">
                            {anom.id}
                          </Link>
                        </td>
                        <td className="px-3 py-2">
                          <SeverityBadge severity={anom.severity as any} />
                        </td>
                        <td className="px-3 py-2 font-mono text-muted">{anom.rule_id}</td>
                        <td className="max-w-xs truncate px-3 py-2 text-slate-200" title={anom.title}>
                          {anom.title}
                        </td>
                        <td className="px-3 py-2 font-mono">
                          {anom.icao24 ? (
                            <Link to={`/aircraft/${anom.icao24}`} className="hover:text-accent underline">
                              {anom.icao24.toUpperCase()}
                            </Link>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-muted">
                          {anom.event_start ? fmtTime(anom.event_start) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Provider Connectivity Monitor */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-bold tracking-tight text-white">
                  Data Provider Health
                </h2>
                <Link to="/data-sources" className="text-xs text-accent hover:underline">
                  Manage Sources →
                </Link>
              </div>

              <div className="space-y-3">
                {data.data_sources.map((ds) => (
                  <div key={ds.name} className="rounded border border-line/60 bg-subpanel p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-semibold text-slate-200">
                        {ds.name}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                          ds.enabled ? "bg-ok/20 text-ok" : "bg-muted/20 text-muted"
                        }`}
                      >
                        {ds.enabled ? "ACTIVE" : "DISABLED"}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted">
                      <span>Type: {ds.kind}</span>
                      <span>
                        {ds.last_success_at ? `Updated ${fmtTime(ds.last_success_at)}` : "No sync"}
                      </span>
                    </div>
                    {ds.last_error && (
                      <div className="mt-1.5 rounded bg-sev-critical/10 p-1.5 text-[10px] text-sev-critical">
                        {ds.last_error}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="mt-4 border-t border-line/60 pt-3 text-[11px] text-muted flex items-center justify-between">
                <span>Latest Refresh:</span>
                <span className="font-mono text-slate-300">
                  {data.latest_refresh_at ? fmtTime(data.latest_refresh_at) : "N/A"}
                </span>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
