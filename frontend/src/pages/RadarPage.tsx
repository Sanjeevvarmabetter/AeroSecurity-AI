import type { GeoJSONSource, Map, MapMouseEvent } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { MapView } from "../components/MapView";
import { ErrorNote, NeedsToken } from "../components/QueryNotice";
import { useLive, useTrajectory } from "../hooks/useAviation";
import type { LiveAircraft } from "../types/aviation";
import { fmtAlt, fmtSpeed, fmtTime, fmtVRate, orDash } from "../utils/format";
import { boundsOf, trackToGeoJSON } from "../utils/geojson";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
const AGES = [
  { label: "5 min", s: 300 },
  { label: "15 min", s: 900 },
  { label: "1 hour", s: 3600 },
  { label: "6 hours", s: 21600 },
  { label: "24 hours", s: 86400 },
];

const EMERGENCY_SQUAWKS: Record<string, string> = {
  "7500": "7500 - Unlawful Interference (Hijack)",
  "7600": "7600 - Radio Communication Failure",
  "7700": "7700 - General Aviation Emergency",
};

function planeImage(color = "#38bdf8"): ImageData {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d")!;
  g.fillStyle = color;
  g.strokeStyle = "#070c14";
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(16, 3);
  g.lineTo(26, 28);
  g.lineTo(16, 22);
  g.lineTo(6, 28);
  g.closePath();
  g.fill();
  g.stroke();
  return g.getImageData(0, 0, 32, 32);
}

function emergencyPlaneImage(): ImageData {
  return planeImage("#ef4444");
}

const toFeatures = (list: LiveAircraft[]): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: list.map((a) => {
    const isEmerg = Boolean(a.squawk && EMERGENCY_SQUAWKS[a.squawk]);
    return {
      type: "Feature",
      properties: {
        icao24: a.icao24,
        heading: a.heading_deg ?? 0,
        hasHeading: a.heading_deg != null,
        ground: a.on_ground === true,
        squawk: a.squawk ?? "",
        isEmergency: isEmerg,
        category: a.category || "UNKNOWN",
      },
      geometry: { type: "Point", coordinates: [a.lon, a.lat] },
    };
  }),
});

export function RadarPage() {
  const [at, setAt] = useState(""); // "" = now
  const [maxAge, setMaxAge] = useState(900);
  const [inView, setInView] = useState(false);
  const [bbox, setBbox] = useState<[number, number, number, number] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [ready, setReady] = useState(false);
  const mapRef = useRef<Map | null>(null);
  const fitted = useRef(false);

  const params = useMemo(
    () => ({
      at: at ? `${at}:00Z` : undefined,
      max_age_s: maxAge,
      ...(inView && bbox ? { lamin: bbox[0], lomin: bbox[1], lamax: bbox[2], lomax: bbox[3] } : {}),
    }),
    [at, maxAge, inView, bbox],
  );
  const live = useLive(params, at ? false : 15_000);
  const list = live.data?.aircraft ?? [];
  const shown = useMemo(() => {
    const s = search.trim().toLowerCase();
    return s
      ? list.filter(
          (a) =>
            a.icao24.includes(s) ||
            (a.callsign ?? "").toLowerCase().includes(s) ||
            (a.registration ?? "").toLowerCase().includes(s) ||
            (a.squawk ?? "").includes(s)
        )
      : list;
  }, [list, search]);
  const sel = shown.find((a) => a.icao24 === selected) ?? null;
  const track = useTrajectory(selected ?? undefined, at ? { end: `${at}:00Z` } : {});

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("aircraft") as GeoJSONSource).setData(toFeatures(shown));
    if (!fitted.current && shown.length) {
      const b = boundsOf(shown);
      if (b) map.fitBounds(b, { padding: 60, duration: 0, maxZoom: 8 });
      fitted.current = true;
    }
  }, [shown, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("track") as GeoJSONSource).setData(
      selected && track.data ? trackToGeoJSON(track.data.points, track.data.segments) : EMPTY,
    );
    map.setFilter("selected", ["==", ["get", "icao24"], selected ?? ""]);
  }, [track.data, selected, ready]);

  const jumpToLatest = () => {
    const t = live.data?.latest_observation_at;
    if (t) {
      setAt(t.slice(0, 16));
      fitted.current = false;
    }
  };

  const selIsEmergency = Boolean(sel?.squawk && EMERGENCY_SQUAWKS[sel.squawk]);

  return (
    <section className="space-y-4">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <span>Live Surveillance Flight Radar</span>
            <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
          </h1>
          <p className="text-xs text-muted">
            High-precision ADS-B tactical air situation display with emergency beacon tracking
          </p>
        </div>
      </div>

      <NeedsToken />

      {/* Control Toolbar */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-panel p-3 text-xs">
        <label>
          <div className="text-muted text-[11px] mb-1">Observation Time (UTC)</div>
          <input
            type="datetime-local"
            value={at}
            onChange={(e) => {
              setAt(e.target.value);
              fitted.current = false;
            }}
            className="rounded border border-line bg-ink px-2.5 py-1 text-slate-200"
          />
        </label>
        <button
          className="rounded border border-line bg-card px-3 py-1 font-semibold text-slate-300 hover:border-slate-500 transition-colors"
          onClick={() => {
            setAt("");
            fitted.current = false;
          }}
        >
          Live Snapshot
        </button>
        <label>
          <div className="text-muted text-[11px] mb-1">Freshness Window</div>
          <select
            value={maxAge}
            onChange={(e) => setMaxAge(Number(e.target.value))}
            className="rounded border border-line bg-ink px-2.5 py-1 text-slate-200"
          >
            {AGES.map((a) => (
              <option key={a.s} value={a.s}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer pb-1">
          <input
            type="checkbox"
            checked={inView}
            onChange={(e) => setInView(e.target.checked)}
            className="rounded border-line bg-ink"
          />
          <span className="text-slate-300 text-xs">Only aircraft in viewport</span>
        </label>
        <input
          aria-label="Filter aircraft"
          placeholder="Filter: ICAO24 / Callsign / Squawk..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="ml-auto w-64 rounded border border-line bg-ink px-3 py-1 text-xs text-slate-200 placeholder-muted/60 focus:border-accent focus:outline-none"
        />
      </div>

      <ErrorNote error={live.error} />

      {live.data && (
        <div className="flex items-center justify-between text-xs text-muted px-1">
          <span>
            Tracking <strong className="text-slate-200 font-mono">{shown.length.toLocaleString()}</strong> aircraft
            as of <span className="font-mono text-slate-300">{fmtTime(live.data.as_of)}</span> (positions &le;{" "}
            {AGES.find((a) => a.s === maxAge)?.label ?? `${maxAge}s`} old)
          </span>
          {live.data.truncated && (
            <span className="text-amber-400 font-medium">Result truncated — zoom into regional sector</span>
          )}
        </div>
      )}

      {live.data?.stale && (
        <div
          role="status"
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 text-xs text-amber-200 space-y-1"
        >
          <strong className="text-amber-400">Notice: Historical or Stale Flight Data.</strong> No observations fall within
          the immediate {AGES.find((a) => a.s === maxAge)?.label} window.
          {live.data.latest_observation_at && (
            <div>
              Newest stored observation in database:{" "}
              <span className="font-mono text-slate-200">{fmtTime(live.data.latest_observation_at)}</span>.{" "}
              <button className="underline text-accent hover:text-sky-300 font-semibold ml-1" onClick={jumpToLatest}>
                Synchronize View to That Moment &rarr;
              </button>
            </div>
          )}
        </div>
      )}

      {/* Main Map & Detail Split View */}
      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <MapView
          className="h-[600px] rounded-lg border border-line shadow-xl overflow-hidden"
          probeLayer="aircraft"
          onReady={(map) => {
            mapRef.current = map;
            map.addImage("plane", planeImage("#38bdf8"));
            map.addImage("plane-emergency", emergencyPlaneImage());
            map.addSource("aircraft", { type: "geojson", data: EMPTY });
            map.addSource("track", { type: "geojson", data: EMPTY });

            // Trajectory track lines
            map.addLayer({
              id: "track-line",
              type: "line",
              source: "track",
              filter: ["==", ["get", "gap"], false],
              paint: { "line-color": "#38bdf8", "line-width": 2, "line-opacity": 0.8 },
            });
            map.addLayer({
              id: "track-gap",
              type: "line",
              source: "track",
              filter: ["==", ["get", "gap"], true],
              paint: { "line-color": "#f59e0b", "line-width": 1.5, "line-dasharray": [2, 3] },
            });

            // Emergency squawk pulsing ring
            map.addLayer({
              id: "emergency-ring",
              type: "circle",
              source: "aircraft",
              filter: ["==", ["get", "isEmergency"], true],
              paint: {
                "circle-radius": 18,
                "circle-color": "#ef4444",
                "circle-opacity": 0.35,
                "circle-stroke-color": "#f87171",
                "circle-stroke-width": 2,
              },
            });

            // Selected aircraft ring
            map.addLayer({
              id: "selected",
              type: "circle",
              source: "aircraft",
              filter: ["==", ["get", "icao24"], ""],
              paint: {
                "circle-radius": 16,
                "circle-color": "#38bdf8",
                "circle-opacity": 0.25,
                "circle-stroke-color": "#38bdf8",
                "circle-stroke-width": 1.5,
              },
            });

            // Normal aircraft markers
            map.addLayer({
              id: "aircraft",
              type: "symbol",
              source: "aircraft",
              layout: {
                "icon-image": [
                  "case",
                  ["==", ["get", "isEmergency"], true],
                  "plane-emergency",
                  "plane",
                ],
                "icon-size": 0.65,
                "icon-rotate": ["get", "heading"],
                "icon-rotation-alignment": "map",
                "icon-allow-overlap": true,
                "icon-ignore-placement": true,
              },
            });

            const pick = (e: MapMouseEvent) => {
              const f = map.queryRenderedFeatures(e.point, { layers: ["aircraft"] })[0];
              setSelected(f ? String(f.properties?.icao24) : null);
            };
            const setBox = () => {
              const b = map.getBounds();
              setBbox([b.getSouth(), b.getWest(), b.getNorth(), b.getEast()]);
            };
            map.on("click", pick);
            map.on("mouseenter", "aircraft", () => (map.getCanvas().style.cursor = "pointer"));
            map.on("mouseleave", "aircraft", () => (map.getCanvas().style.cursor = ""));
            map.on("moveend", setBox);
            setBox();
            setReady(true);
            return () => {
              mapRef.current = null;
              setReady(false);
            };
          }}
        />

        {/* Sidebar Inspector */}
        <aside className="rounded-lg border border-line bg-panel p-4 text-xs shadow-lg flex flex-col">
          {sel ? (
            <div className="space-y-4">
              <div className="border-b border-line pb-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-lg font-bold text-accent">
                    {sel.icao24.toUpperCase()}
                  </span>
                  {sel.category && (
                    <span className="rounded bg-sky-500/10 border border-sky-500/30 px-2 py-0.5 text-[10px] font-mono text-sky-400">
                      {sel.category}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between text-muted text-[11px]">
                  <span>Callsign: <strong className="text-slate-200 font-mono">{orDash(sel.callsign)}</strong></span>
                  <span>Reg: <span className="font-mono text-slate-300">{orDash(sel.registration)}</span></span>
                </div>
              </div>

              {/* Emergency Beacon Alert if Squawking 7500/7600/7700 */}
              {selIsEmergency && (
                <div className="rounded border border-red-500/40 bg-red-500/10 p-2.5 text-xs text-red-300 font-medium space-y-1">
                  <div className="flex items-center gap-1.5 font-bold text-red-400">
                    <span>🚨</span>
                    <span>EMERGENCY SQUAWK DETECTED</span>
                  </div>
                  <div className="font-mono text-[11px] text-red-200">
                    {EMERGENCY_SQUAWKS[sel.squawk!]}
                  </div>
                </div>
              )}

              {/* Telemetry Grid */}
              <div className="space-y-2 rounded border border-line/60 bg-ink/50 p-3">
                {([
                  ["Squawk Code", sel.squawk ? `${sel.squawk} (SSR)` : "—"],
                  ["Baro Altitude", fmtAlt(sel.baro_altitude_m)],
                  ["Reported Speed", fmtSpeed(sel.velocity_ms)],
                  ["Heading", sel.heading_deg == null ? "—" : `${sel.heading_deg.toFixed(1)}°`],
                  ["Reported Vert Rate", fmtVRate(sel.vertical_rate_ms)],
                  ["On-Ground State", sel.on_ground == null ? "—" : sel.on_ground ? "True (Taxing / Parked)" : "False (Airborne)"],
                  ["Geodetic Position", `${sel.lat.toFixed(4)}°, ${sel.lon.toFixed(4)}°`],
                  ["Observation Age", `${sel.age_s.toFixed(0)} seconds ago`],
                  ["Telemetry Source", sel.source],
                ] as const).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between border-b border-line/30 pb-1 last:border-0 last:pb-0">
                    <span className="text-[11px] uppercase tracking-wide text-muted">{k}</span>
                    <span className="font-mono text-xs text-slate-200">{v}</span>
                  </div>
                ))}
              </div>

              {/* Deep Analysis Action Links */}
              <div className="pt-2 space-y-2">
                <Link
                  to={`/aircraft/${sel.icao24}`}
                  className="flex items-center justify-center gap-1.5 w-full rounded border border-accent/40 bg-accent/10 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20 transition-colors"
                >
                  Aircraft Intelligence Profile &rarr;
                </Link>
                <Link
                  to={`/trajectories?icao24=${sel.icao24}`}
                  className="flex items-center justify-center gap-1.5 w-full rounded border border-line bg-card py-1.5 text-xs text-slate-300 hover:border-slate-500 transition-colors"
                >
                  Kinematic Trajectory Analytics &rarr;
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-muted space-y-2">
              <span className="text-3xl opacity-40">🎯</span>
              <p className="text-xs">
                Select an aircraft marker on the radar screen to inspect its ADS-B telemetry, heading vector, and flight trajectory.
              </p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
