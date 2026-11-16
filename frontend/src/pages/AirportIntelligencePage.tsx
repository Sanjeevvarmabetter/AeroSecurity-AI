import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { NeedsToken } from "../components/QueryNotice";
import { getAirport, getAirports, getAirportTraffic } from "../services/api";
import type { Airport } from "../types/aviation";
import type { AirportTraffic } from "../types/analytics";
import { fmtAlt, fmtSpeed, fmtTime, orDash } from "../utils/format";

const PRESET_AIRPORTS = [
  { code: "KUES", name: "Waukesha County Airport (Active Dataset)" },
  { code: "KPHL", name: "Philadelphia International" },
  { code: "EGLL", name: "London Heathrow" },
  { code: "LOWW", name: "Vienna International" },
  { code: "LBSF", name: "Sofia Airport" },
  { code: "LLBG", name: "Tel Aviv Ben Gurion" },
];

export function AirportIntelligencePage() {
  const [sp, setSp] = useSearchParams();
  const currentCode = sp.get("code") || "KUES";
  const [radiusKm, setRadiusKm] = useState(25);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Airport[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  const [airport, setAirport] = useState<Airport | null>(null);
  const [traffic, setTraffic] = useState<AirportTraffic | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setError(null);

    Promise.all([
      getAirport(currentCode),
      getAirportTraffic(currentCode, radiusKm),
    ])
      .then(([ap, tr]) => {
        if (!cancel) {
          setAirport(ap);
          setTraffic(tr);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancel) {
          setError(err.message || "Failed to load airport intelligence");
          setLoading(false);
        }
      });

    return () => {
      cancel = true;
    };
  }, [currentCode, radiusKm]);

  // Debounced airport search
  useEffect(() => {
    if (!searchQuery.trim() || searchQuery.length < 2) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(() => {
      setIsSearching(true);
      getAirports(searchQuery.trim(), 8)
        .then((res: { items: Airport[] }) => {
          setSearchResults(res.items);
          setIsSearching(false);
        })
        .catch(() => setIsSearching(false));
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  const selectAirport = (code: string) => {
    setSp({ code });
    setSearchQuery("");
    setSearchResults([]);
  };

  return (
    <section className="space-y-6">
      {/* Header */}
      <div className="border-b border-line/60 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
          <span>Airport Intelligence & Terminal Traffic</span>
          <span className="rounded bg-accent/15 px-2 py-0.5 text-xs font-mono text-accent">
            POSTGIS SPATIAL
          </span>
        </h1>
        <p className="mt-1 text-xs text-muted">
          Global airport spatial queries, proximity density metrics, and nearby aircraft observation tracking.
        </p>
      </div>

      <NeedsToken />
      {error && <p className="text-xs text-sev-critical">{error}</p>}

      {/* Airport Selector & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-line bg-panel p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-muted">Preset Terminals:</span>
          {PRESET_AIRPORTS.map((p) => (
            <button
              key={p.code}
              onClick={() => selectAirport(p.code)}
              className={`rounded px-2.5 py-1 text-xs font-mono transition-all ${
                currentCode === p.code
                  ? "border border-accent bg-accent/20 font-bold text-accent"
                  : "border border-line bg-subpanel text-slate-300 hover:bg-line"
              }`}
            >
              {p.code}
            </button>
          ))}
        </div>

        {/* Airport Search Input */}
        <div className="relative">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search ICAO / IATA / Name..."
            className="w-64 rounded border border-line bg-ink px-3 py-1.5 text-xs text-white placeholder-muted focus:border-accent"
          />
          {isSearching && (
            <span className="absolute right-2.5 top-2 text-[10px] text-muted">searching...</span>
          )}

          {searchResults.length > 0 && (
            <ul className="absolute right-0 top-8 z-20 mt-1 max-h-56 w-72 overflow-y-auto rounded border border-line bg-panel shadow-2xl divide-y divide-line/60">
              {searchResults.map((ap) => (
                <li key={ap.ident}>
                  <button
                    onClick={() => selectAirport(ap.ident)}
                    className="w-full text-left px-3 py-2 text-xs hover:bg-subpanel transition-colors"
                  >
                    <div className="flex items-center justify-between font-mono font-semibold text-accent">
                      <span>{ap.ident} {ap.iata_code ? `(${ap.iata_code})` : ""}</span>
                      <span className="text-[10px] text-muted">{ap.iso_country}</span>
                    </div>
                    <div className="truncate text-[11px] text-slate-300">{ap.name}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex h-64 items-center justify-center rounded border border-line bg-panel">
          <div className="flex flex-col items-center gap-2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-xs font-mono text-muted">Calculating spatial airport radius fixes...</span>
          </div>
        </div>
      )}

      {airport && traffic && (
        <>
          {/* Airport Details & Radius Controls */}
          <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
            {/* Terminal Info Card */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line/60 pb-3">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2 font-mono">
                    <span>{airport.ident}</span>
                    {airport.iata_code && (
                      <span className="text-sm font-normal text-slate-300">/ {airport.iata_code}</span>
                    )}
                  </h2>
                  <div className="text-sm font-medium text-slate-200 mt-0.5">{airport.name}</div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted">Surveillance Radius:</span>
                  {[10, 25, 50].map((r) => (
                    <button
                      key={r}
                      onClick={() => setRadiusKm(r)}
                      className={`rounded px-2 py-1 text-xs font-mono ${
                        radiusKm === r
                          ? "bg-accent font-bold text-ink"
                          : "border border-line bg-subpanel text-slate-300 hover:bg-line"
                      }`}
                    >
                      {r} km
                    </button>
                  ))}
                </div>
              </div>

              {/* Terminal Specs */}
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
                <div>
                  <div className="text-[10px] font-semibold uppercase text-muted">Terminal Type</div>
                  <div className="font-mono text-slate-200 mt-0.5">{airport.airport_type?.replace("_", " ") || "—"}</div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase text-muted">Elevation</div>
                  <div className="font-mono text-slate-200 mt-0.5">
                    {airport.elevation_ft !== null ? `${airport.elevation_ft.toLocaleString()} ft` : "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase text-muted">Coordinates</div>
                  <div className="font-mono text-slate-200 mt-0.5">
                    {airport.lat.toFixed(4)}, {airport.lon.toFixed(4)}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase text-muted">Country Code</div>
                  <div className="font-mono text-slate-200 mt-0.5">{airport.iso_country || "—"}</div>
                </div>
              </div>
            </div>

            {/* Proximity Stats */}
            <div className="rounded border border-line bg-panel p-4 shadow-sm flex flex-col justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted">
                Proximity Telemetry ({radiusKm} km)
              </h3>
              <div className="my-2 grid grid-cols-2 gap-2 text-center">
                <div className="rounded bg-subpanel p-2.5">
                  <div className="text-[10px] uppercase text-muted">Observed Fixes</div>
                  <div className="font-mono text-xl font-bold text-accent mt-0.5">
                    {traffic.total_observations.toLocaleString()}
                  </div>
                </div>
                <div className="rounded bg-subpanel p-2.5">
                  <div className="text-[10px] uppercase text-muted">Distinct Targets</div>
                  <div className="font-mono text-xl font-bold text-white mt-0.5">
                    {traffic.distinct_aircraft_count}
                  </div>
                </div>
              </div>
              <div className="rounded bg-accent/5 p-2 text-[10px] text-muted border border-accent/20">
                Spatial filter: PostGIS ST_DWithin geography index
              </div>
            </div>
          </div>

          {/* Traffic Activity Chart */}
          <div className="rounded border border-line bg-panel p-4 shadow-sm">
            <h3 className="text-sm font-bold text-white mb-1">
              Hourly ADS-B Observation Volume Near {airport.ident}
            </h3>
            <p className="text-[11px] text-muted mb-4">
              Temporal distribution of recorded fixes within the selected {radiusKm} km radius.
            </p>

            {traffic.hourly_series.length > 0 ? (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={traffic.hourly_series}>
                    <CartesianGrid stroke="#1e2f4d" strokeDasharray="3 3" />
                    <XAxis dataKey="hour" stroke="#7e8da6" fontSize={10} tickLine={false} />
                    <YAxis stroke="#7e8da6" fontSize={10} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: "#0d1524", borderColor: "#1e2f4d", borderRadius: 4, fontSize: 11 }}
                    />
                    <Bar dataKey="count" fill="#38bdf8" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="p-8 text-center text-xs text-muted">
                No recorded flights within {radiusKm} km of this airport in the current dataset.
              </p>
            )}
          </div>

          {/* Nearby Aircraft Table */}
          <div className="rounded border border-line bg-panel p-4 shadow-sm">
            <h3 className="text-sm font-bold text-white mb-3">
              Identified Aircraft Fixes Near {airport.ident} (Within {radiusKm} km)
            </h3>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-subpanel text-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">ICAO24</th>
                    <th className="px-3 py-2 font-medium">Callsign</th>
                    <th className="px-3 py-2 font-medium">Airframe Type</th>
                    <th className="px-3 py-2 font-medium">Baro Altitude</th>
                    <th className="px-3 py-2 font-medium">Velocity</th>
                    <th className="px-3 py-2 font-medium">Distance from Airport</th>
                    <th className="px-3 py-2 font-medium">Last Observed (UTC)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60 font-mono">
                  {traffic.recent_aircraft.map((ac: any, idx: number) => (
                    <tr key={idx} className="hover:bg-subpanel/50">
                      <td className="px-3 py-2 font-semibold">
                        <Link to={`/aircraft/${ac.icao24}`} className="text-accent hover:underline">
                          {ac.icao24.toUpperCase()}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-slate-200">{orDash(ac.callsign)}</td>
                      <td className="px-3 py-2 text-muted">{orDash(ac.aircraft_type)}</td>
                      <td className="px-3 py-2">{fmtAlt(ac.baro_altitude_m)}</td>
                      <td className="px-3 py-2">{fmtSpeed(ac.velocity_ms)}</td>
                      <td className="px-3 py-2 text-accent font-semibold">{ac.distance_km} km</td>
                      <td className="whitespace-nowrap px-3 py-2 text-muted">{fmtTime(ac.observed_at)}</td>
                    </tr>
                  ))}
                  {traffic.recent_aircraft.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-4 text-center text-muted font-sans">
                        No aircraft observed within {radiusKm} km of {airport.ident}.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Aviation Coverage Honesty Notice */}
          <div className="rounded border border-line/60 bg-subpanel p-3 text-xs text-muted">
            <strong className="text-slate-300">ADS-B Coverage Notice:</strong> Local traffic counts reflect public OpenSky receiver coverage
            in this region. Incomplete receiver coverage must not be inferred as an absence of aircraft traffic.
          </div>
        </>
      )}
    </section>
  );
}
