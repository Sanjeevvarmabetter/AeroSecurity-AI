import { trackToGeoJSON, thin, boundsOf } from "./geojson";
import { fmtAlt, fmtDuration, fmtSpeed, fmtTime, orDash } from "./format";
import type { Segment, TrackPoint } from "../types/aviation";

test("absent values render as a dash, never a number", () => {
  expect(fmtAlt(null)).toBe("—");
  expect(fmtSpeed(undefined)).toBe("—");
  expect(orDash(null)).toBe("—");
  expect(orDash("")).toBe("—");
  expect(orDash(0)).toBe("0");
});

test("unit conversions", () => {
  expect(fmtAlt(10000)).toBe("10,000 m (32,808 ft)");
  expect(fmtSpeed(100)).toContain("194 kt");
  expect(fmtDuration(4476)).toBe("1 h 14 min");
  expect(fmtDuration(5)).toBe("5.0 s");
  expect(fmtTime("2026-09-30T04:01:28.500Z")).toBe("2026-09-30 04:01:28 UTC");
});

const pt = (lon: number): TrackPoint => ({ t: "", lat: 0, lon, baro_altitude_m: null, geo_altitude_m: null, reported_velocity_ms: null });
const seg = (is_gap: boolean): Segment => ({ start: "", end: "", dt_s: 1, distance_m: 1, derived_speed_ms: 1, reported_speed_ms: null, baro_delta_m: null, geo_delta_m: null, derived_vertical_rate_ms: null, is_gap });

test("gaps become separate dashed connectors, not continuous track", () => {
  const fc = trackToGeoJSON([pt(0), pt(1), pt(2), pt(3), pt(4)], [seg(false), seg(true), seg(false), seg(false)]);
  const kinds = fc.features.map((f) => [(f.properties as { gap: boolean }).gap, (f.geometry as GeoJSON.LineString).coordinates.length]);
  expect(kinds).toEqual([[false, 2], [true, 2], [false, 3]]);
});

test("single point yields no line; bounds and thinning behave", () => {
  expect(trackToGeoJSON([pt(0)], []).features).toEqual([]);
  expect(boundsOf([])).toBeNull();
  expect(boundsOf([{ lat: 1, lon: 2 }, { lat: 3, lon: -4 }])).toEqual([[-4, 1], [2, 3]]);
  expect(thin([1, 2, 3], 10)).toEqual([1, 2, 3]);
  expect(thin(Array.from({ length: 1000 }, (_, i) => i), 100)).toHaveLength(100);
});
