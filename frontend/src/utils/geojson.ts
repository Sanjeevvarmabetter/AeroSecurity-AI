import type { Segment, TrackPoint } from "../types/aviation";

type Feature = GeoJSON.Feature<GeoJSON.LineString, { gap: boolean }>;

/** Split a track into continuous lines and dashed gap connectors. Gaps are drawn as such, never as flight. */
export function trackToGeoJSON(points: TrackPoint[], segments: Segment[]): GeoJSON.FeatureCollection {
  const features: Feature[] = [];
  let run: [number, number][] = points.length ? [[points[0].lon, points[0].lat]] : [];
  segments.forEach((s, i) => {
    const a = points[i];
    const b = points[i + 1];
    if (!a || !b) return;
    if (s.is_gap) {
      if (run.length > 1) features.push(line(run, false));
      features.push(line([[a.lon, a.lat], [b.lon, b.lat]], true));
      run = [[b.lon, b.lat]];
    } else {
      run.push([b.lon, b.lat]);
    }
  });
  if (run.length > 1) features.push(line(run, false));
  return { type: "FeatureCollection", features };
}

const line = (coordinates: [number, number][], gap: boolean): Feature => ({
  type: "Feature",
  properties: { gap },
  geometry: { type: "LineString", coordinates },
});

export function boundsOf(points: { lat: number; lon: number }[]): [[number, number], [number, number]] | null {
  if (!points.length) return null;
  let [w, s, e, n] = [180, 90, -180, -90];
  for (const p of points) {
    w = Math.min(w, p.lon);
    e = Math.max(e, p.lon);
    s = Math.min(s, p.lat);
    n = Math.max(n, p.lat);
  }
  return [[w, s], [e, n]];
}

/** Evenly thin a series for charting only; the underlying data is untouched. */
export function thin<T>(rows: T[], max: number): T[] {
  if (rows.length <= max) return rows;
  const step = rows.length / max;
  return Array.from({ length: max }, (_, i) => rows[Math.floor(i * step)]);
}
