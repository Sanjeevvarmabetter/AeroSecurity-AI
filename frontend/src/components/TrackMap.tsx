import type { GeoJSONSource, Map } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type { Trajectory } from "../types/aviation";
import { boundsOf, trackToGeoJSON } from "../utils/geojson";
import { MapView } from "./MapView";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export interface Highlight {
  lat: number;
  lon: number;
}

const NO_HIGHLIGHTS: Highlight[] = [];

export function TrackMap({
  trajectory,
  className,
  highlights = NO_HIGHLIGHTS,
}: {
  trajectory: Trajectory | undefined;
  className?: string;
  highlights?: Highlight[];
}) {
  const mapRef = useRef<Map | null>(null);
  const [ready, setReady] = useState(false); // the track may arrive before the map has loaded

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !trajectory) return;
    (map.getSource("track") as GeoJSONSource | undefined)?.setData(
      trackToGeoJSON(trajectory.points, trajectory.segments),
    );
    const pts = trajectory.points;
    (map.getSource("ends") as GeoJSONSource | undefined)?.setData(
      pts.length
        ? {
            type: "FeatureCollection",
            features: [
              { type: "Feature", properties: { end: "first" }, geometry: { type: "Point", coordinates: [pts[0].lon, pts[0].lat] } },
              { type: "Feature", properties: { end: "last" }, geometry: { type: "Point", coordinates: [pts[pts.length - 1].lon, pts[pts.length - 1].lat] } },
            ],
          }
        : EMPTY,
    );
    const b = boundsOf(pts);
    if (b) map.fitBounds(b, { padding: 50, duration: 0, maxZoom: 10 });
  }, [trajectory, ready]);

  // Evidence markers update independently so they never reset the user's view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("highlights") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: highlights.map((h) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [h.lon, h.lat] } })),
    });
  }, [highlights, ready]);

  return (
    <MapView
      className={className}
      probeLayer="track-line"
      onReady={(map) => {
        mapRef.current = map;
        map.addSource("track", { type: "geojson", data: EMPTY });
        map.addSource("ends", { type: "geojson", data: EMPTY });
        map.addSource("highlights", { type: "geojson", data: EMPTY });
        map.addLayer({ id: "track-line", type: "line", source: "track", filter: ["==", ["get", "gap"], false],
          paint: { "line-color": "#4c8dff", "line-width": 2.5 } });
        map.addLayer({ id: "track-gap", type: "line", source: "track", filter: ["==", ["get", "gap"], true],
          paint: { "line-color": "#eab308", "line-width": 1.5, "line-dasharray": [2, 3] } });
        map.addLayer({ id: "highlights", type: "circle", source: "highlights",
          paint: { "circle-radius": 7, "circle-color": "#f43f5e", "circle-opacity": 0.35, "circle-stroke-width": 2, "circle-stroke-color": "#f43f5e" } });
        map.addLayer({ id: "ends", type: "circle", source: "ends",
          paint: { "circle-radius": 5, "circle-stroke-width": 1.5, "circle-stroke-color": "#0b1220",
            "circle-color": ["match", ["get", "end"], "first", "#22c55e", "#f97316"] } });
        setReady(true);
        return () => {
          mapRef.current = null;
          setReady(false);
        };
      }}
    >
      <div className="pointer-events-none absolute bottom-6 left-2 rounded bg-ink/80 px-2 py-1 text-[11px] text-muted">
        <span className="text-ok">●</span> first fix <span className="text-sev-high">●</span> last fix{" "}
        <span className="text-sev-medium">- - -</span> unobserved gap {highlights.length > 0 && <><span className="text-[#f43f5e]">◎</span> evidence</>}
      </div>
    </MapView>
  );
}
