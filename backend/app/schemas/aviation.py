from datetime import datetime

from pydantic import BaseModel


class LatLon(BaseModel):
    lat: float
    lon: float


class AircraftSummary(BaseModel):
    icao24: str
    registration: str | None
    aircraft_type: str | None
    category: str = "UNKNOWN"
    manufacturer: str | None
    model: str | None
    operator: str | None
    origin_country: str | None
    first_seen: datetime | None
    last_seen: datetime | None
    last_callsign: str | None
    last_position: LatLon | None
    last_position_at: datetime | None


class SquawkUse(BaseModel):
    squawk: str
    first_seen: datetime
    last_seen: datetime
    observations: int


class AircraftDetail(AircraftSummary):
    observation_count: int
    positioned_count: int
    callsigns: list[str]
    squawks: list[SquawkUse]
    observation_sources: list[str]  # data_sources that supplied observations
    metadata_source: str | None  # data_source that supplied registration/type/model, if any


class ObservationOut(BaseModel):
    id: int
    observed_at: datetime
    last_contact_at: datetime | None
    callsign: str | None
    lat: float | None
    lon: float | None
    baro_altitude_m: float | None
    geo_altitude_m: float | None
    on_ground: bool | None
    velocity_ms: float | None  # reported by the aircraft/provider
    heading_deg: float | None
    vertical_rate_ms: float | None  # reported
    squawk: str | None
    position_source: int | None
    source: str
    validation_issues: list[str]


class LiveAircraft(BaseModel):
    icao24: str
    callsign: str | None
    registration: str | None
    aircraft_type: str | None = None
    category: str = "UNKNOWN"
    squawk: str | None = None
    lat: float
    lon: float
    heading_deg: float | None
    velocity_ms: float | None
    baro_altitude_m: float | None
    vertical_rate_ms: float | None
    on_ground: bool | None
    observed_at: datetime
    age_s: float
    source: str


class LiveResponse(BaseModel):
    as_of: datetime
    max_age_s: int
    count: int
    truncated: bool
    latest_observation_at: datetime | None  # newest stored observation at or before as_of
    stale: bool  # True when no stored data falls inside the freshness window ending at as_of
    aircraft: list[LiveAircraft]


class TrackPointOut(BaseModel):
    t: datetime
    lat: float
    lon: float
    baro_altitude_m: float | None
    geo_altitude_m: float | None
    reported_velocity_ms: float | None


class SegmentOut(BaseModel):
    start: datetime
    end: datetime
    dt_s: float
    distance_m: float
    derived_speed_ms: float | None  # ground displacement / dt
    reported_speed_ms: float | None  # provider-reported, shown separately on purpose
    baro_delta_m: float | None
    geo_delta_m: float | None
    derived_vertical_rate_ms: float | None
    is_gap: bool
    derived_bearing_deg: float | None = None
    reported_heading_deg: float | None = None
    derived_acceleration_ms2: float | None = None
    reported_vertical_rate_ms: float | None = None
    vertical_rate_delta_ms: float | None = None


class TrajectorySummaryOut(BaseModel):
    points: int
    segments: int
    start: datetime | None
    end: datetime | None
    duration_s: float
    observed_distance_m: float
    gap_count: int
    gap_total_s: float
    longest_gap_s: float
    median_interval_s: float | None
    max_derived_speed_ms: float | None
    max_reported_speed_ms: float | None
    min_baro_altitude_m: float | None
    max_baro_altitude_m: float | None
    duplicate_timestamps: int
    max_acceleration_ms2: float | None = None
    avg_derived_speed_ms: float | None = None


class TrajectoryResponse(BaseModel):
    icao24: str
    start: datetime | None
    end: datetime | None
    gap_threshold_s: float
    summary: TrajectorySummaryOut
    points: list[TrackPointOut]
    segments: list[SegmentOut]
    notes: list[str]


class AirportOut(BaseModel):
    ident: str
    iata_code: str | None
    name: str
    airport_type: str | None
    iso_country: str | None
    elevation_ft: int | None
    lat: float
    lon: float


class AirportTrafficOut(BaseModel):
    ident: str
    name: str
    radius_km: float
    total_observations: int
    distinct_aircraft_count: int
    hourly_series: list[dict[str, object]]
    recent_aircraft: list[dict[str, object]]
