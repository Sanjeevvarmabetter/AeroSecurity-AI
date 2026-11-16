export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface LatLon {
  lat: number;
  lon: number;
}
export interface AircraftSummary {
  icao24: string;
  registration: string | null;
  aircraft_type: string | null;
  category?: string;
  manufacturer: string | null;
  model: string | null;
  operator: string | null;
  origin_country: string | null;
  first_seen: string | null;
  last_seen: string | null;
  last_callsign: string | null;
  last_position: LatLon | null;
  last_position_at: string | null;
}
export interface SquawkUse {
  squawk: string;
  first_seen: string;
  last_seen: string;
  observations: number;
}
export interface AircraftDetail extends AircraftSummary {
  observation_count: number;
  positioned_count: number;
  callsigns: string[];
  squawks: SquawkUse[];
  observation_sources: string[];
  metadata_source: string | null;
}
export interface Observation {
  id: number;
  observed_at: string;
  last_contact_at: string | null;
  callsign: string | null;
  lat: number | null;
  lon: number | null;
  baro_altitude_m: number | null;
  geo_altitude_m: number | null;
  on_ground: boolean | null;
  velocity_ms: number | null;
  heading_deg: number | null;
  vertical_rate_ms: number | null;
  squawk: string | null;
  position_source: number | null;
  source: string;
  validation_issues: string[];
}
export interface LiveAircraft {
  icao24: string;
  callsign: string | null;
  registration: string | null;
  aircraft_type?: string | null;
  category?: string;
  squawk?: string | null;
  lat: number;
  lon: number;
  heading_deg: number | null;
  velocity_ms: number | null;
  baro_altitude_m: number | null;
  vertical_rate_ms: number | null;
  on_ground: boolean | null;
  observed_at: string;
  age_s: number;
  source: string;
}
export interface LiveResponse {
  as_of: string;
  max_age_s: number;
  count: number;
  truncated: boolean;
  latest_observation_at: string | null;
  stale: boolean;
  aircraft: LiveAircraft[];
}
export interface TrackPoint {
  t: string;
  lat: number;
  lon: number;
  baro_altitude_m: number | null;
  geo_altitude_m: number | null;
  reported_velocity_ms: number | null;
}
export interface Segment {
  start: string;
  end: string;
  dt_s: number;
  distance_m: number;
  derived_speed_ms: number | null;
  reported_speed_ms: number | null;
  baro_delta_m: number | null;
  geo_delta_m: number | null;
  derived_vertical_rate_ms: number | null;
  is_gap: boolean;
  derived_bearing_deg?: number | null;
  reported_heading_deg?: number | null;
  derived_acceleration_ms2?: number | null;
  reported_vertical_rate_ms?: number | null;
  vertical_rate_delta_ms?: number | null;
}
export interface TrajectorySummary {
  points: number;
  segments: number;
  start: string | null;
  end: string | null;
  duration_s: number;
  observed_distance_m: number;
  gap_count: number;
  gap_total_s: number;
  longest_gap_s: number;
  median_interval_s: number | null;
  max_derived_speed_ms: number | null;
  max_reported_speed_ms: number | null;
  min_baro_altitude_m: number | null;
  max_baro_altitude_m: number | null;
  duplicate_timestamps: number;
  max_acceleration_ms2?: number | null;
  avg_derived_speed_ms?: number | null;
}
export interface Trajectory {
  icao24: string;
  gap_threshold_s: number;
  summary: TrajectorySummary;
  points: TrackPoint[];
  segments: Segment[];
  notes: string[];
}
export interface Airport {
  ident: string;
  iata_code: string | null;
  name: string;
  airport_type: string | null;
  iso_country: string | null;
  elevation_ft: number | null;
  lat: number;
  lon: number;
}
export interface DataSource {
  name: string;
  kind: string;
  enabled: boolean;
  terms_url: string | null;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error: string | null;
}
