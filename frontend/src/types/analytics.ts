export interface OverviewAnalytics {
  total_aircraft: number;
  active_aircraft: number;
  total_observations: number;
  total_airports: number;
  total_anomalies: number;
  total_investigations: number;
  critical_events: number;
  emergency_squawks: number;
  newest_observation_at: string | null;
  latest_refresh_at: string | null;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  by_detection_type: Record<string, number>;
  top_aircraft_types: { type: string; count: number }[];
  recent_anomalies: {
    id: string;
    rule_id: string;
    title: string;
    severity: string;
    status: string;
    confidence: number;
    icao24: string | null;
    registration: string | null;
    event_start: string | null;
  }[];
  data_sources: {
    name: string;
    kind: string;
    enabled: boolean;
    last_success_at: string | null;
    last_error: string | null;
  }[];
}

export interface FleetAnalytics {
  altitude_distribution: { range: string; label: string; count: number }[];
  speed_distribution: { range: string; label: string; count: number }[];
  category_distribution: { category: string; count: number }[];
  top_manufacturers: { manufacturer: string; count: number }[];
  on_ground_count: number;
  airborne_count: number;
}

export interface AirportTraffic {
  ident: string;
  name: string;
  radius_km: number;
  total_observations: number;
  distinct_aircraft_count: number;
  hourly_series: { hour: string; count: number }[];
  recent_aircraft: {
    icao24: string;
    callsign: string | null;
    aircraft_type: string | null;
    baro_altitude_m: number | null;
    velocity_ms: number | null;
    observed_at: string;
    distance_km: number;
  }[];
}
