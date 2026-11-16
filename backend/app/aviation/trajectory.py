"""Trajectory analytics over stored observations. Pure functions; no I/O, no verdicts.

Reported values come straight from the provider (ADS-B velocity, vertical rate). Derived values are computed
here from consecutive positions/altitudes. They are different quantities and are never mixed or relabelled:
a mismatch between them is what the detection rules (Phase 4) examine, not something this module judges.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.aviation.geo import haversine_m, initial_bearing_deg


@dataclass(frozen=True, slots=True)
class TrackPoint:
    t: datetime
    lat: float
    lon: float
    baro_altitude_m: float | None = None
    geo_altitude_m: float | None = None
    velocity_ms: float | None = None  # reported
    vertical_rate_ms: float | None = None  # reported
    heading_deg: float | None = None  # reported
    on_ground: bool | None = None


@dataclass(frozen=True, slots=True)
class Segment:
    start: datetime
    end: datetime
    dt_s: float
    distance_m: float  # straight-line (great-circle) between the two fixes
    derived_speed_ms: float | None  # distance / dt (ground displacement); None when dt <= 0
    reported_speed_ms: float | None  # mean of the endpoints' reported velocity, if available
    baro_delta_m: float | None
    geo_delta_m: float | None
    derived_vertical_rate_ms: float | None  # from barometric altitude change (geometric if baro absent)
    is_gap: bool  # dt exceeds the gap threshold: movement between the fixes was not observed
    derived_bearing_deg: float | None = None
    reported_heading_deg: float | None = None
    derived_acceleration_ms2: float | None = None
    reported_vertical_rate_ms: float | None = None
    vertical_rate_delta_ms: float | None = None


@dataclass(frozen=True, slots=True)
class TrajectorySummary:
    points: int
    segments: int
    start: datetime | None
    end: datetime | None
    duration_s: float
    observed_distance_m: float  # continuous segments only; gaps are excluded, not interpolated
    gap_count: int
    gap_total_s: float
    longest_gap_s: float
    median_interval_s: float | None
    max_derived_speed_ms: float | None
    max_reported_speed_ms: float | None
    min_baro_altitude_m: float | None
    max_baro_altitude_m: float | None
    duplicate_timestamps: int  # consecutive points with dt == 0
    max_acceleration_ms2: float | None = None
    avg_derived_speed_ms: float | None = None


def _mean(a: float | None, b: float | None) -> float | None:
    vals = [v for v in (a, b) if v is not None]
    return sum(vals) / len(vals) if vals else None


def _delta(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else b - a


def build_segments(points: Sequence[TrackPoint], gap_s: float = 120.0) -> list[Segment]:
    """Segments between consecutive points, which must be ordered by time ascending."""
    out: list[Segment] = []
    for a, b in zip(points, points[1:], strict=False):
        dt = (b.t - a.t).total_seconds()
        dist = haversine_m(a.lat, a.lon, b.lat, b.lon)
        d_baro, d_geo = (
            _delta(a.baro_altitude_m, b.baro_altitude_m),
            _delta(a.geo_altitude_m, b.geo_altitude_m),
        )
        d_alt = d_baro if d_baro is not None else d_geo
        derived_spd = dist / dt if dt > 0 else None
        rep_spd = _mean(a.velocity_ms, b.velocity_ms)
        derived_vrate = d_alt / dt if d_alt is not None and dt > 0 else None
        rep_vrate = _mean(a.vertical_rate_ms, b.vertical_rate_ms)
        vrate_delta = (
            derived_vrate - rep_vrate if derived_vrate is not None and rep_vrate is not None else None
        )
        bearing = initial_bearing_deg(a.lat, a.lon, b.lat, b.lon) if dist > 0.1 else None
        rep_heading = _mean(a.heading_deg, b.heading_deg)
        accel = (
            (b.velocity_ms - a.velocity_ms) / dt
            if dt > 0 and a.velocity_ms is not None and b.velocity_ms is not None
            else None
        )

        out.append(
            Segment(
                start=a.t,
                end=b.t,
                dt_s=dt,
                distance_m=dist,
                derived_speed_ms=derived_spd,
                reported_speed_ms=rep_spd,
                baro_delta_m=d_baro,
                geo_delta_m=d_geo,
                derived_vertical_rate_ms=derived_vrate,
                is_gap=dt > gap_s,
                derived_bearing_deg=bearing,
                reported_heading_deg=rep_heading,
                derived_acceleration_ms2=accel,
                reported_vertical_rate_ms=rep_vrate,
                vertical_rate_delta_ms=vrate_delta,
            )
        )
    return out


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def summarize(points: Sequence[TrackPoint], segments: Sequence[Segment]) -> TrajectorySummary:
    gaps = [s for s in segments if s.is_gap]
    continuous = [s for s in segments if not s.is_gap]
    derived = [s.derived_speed_ms for s in continuous if s.derived_speed_ms is not None]
    reported = [p.velocity_ms for p in points if p.velocity_ms is not None]
    baro = [p.baro_altitude_m for p in points if p.baro_altitude_m is not None]
    accels = [abs(s.derived_acceleration_ms2) for s in continuous if s.derived_acceleration_ms2 is not None]
    return TrajectorySummary(
        points=len(points),
        segments=len(segments),
        start=points[0].t if points else None,
        end=points[-1].t if points else None,
        duration_s=(points[-1].t - points[0].t).total_seconds() if points else 0.0,
        observed_distance_m=sum(s.distance_m for s in continuous),
        gap_count=len(gaps),
        gap_total_s=sum(s.dt_s for s in gaps),
        longest_gap_s=max((s.dt_s for s in gaps), default=0.0),
        median_interval_s=_median([s.dt_s for s in segments if s.dt_s > 0]),
        max_derived_speed_ms=max(derived, default=None),
        max_reported_speed_ms=max(reported, default=None),
        min_baro_altitude_m=min(baro, default=None),
        max_baro_altitude_m=max(baro, default=None),
        duplicate_timestamps=sum(1 for s in segments if s.dt_s == 0),
        max_acceleration_ms2=max(accels, default=None),
        avg_derived_speed_ms=sum(derived) / len(derived) if derived else None,
    )
