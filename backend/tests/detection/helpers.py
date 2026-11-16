"""Builders for SYNTHETIC test observations. Nothing here is real aviation data."""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from app.detection.types import AircraftInfo, Obs

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
AC = AircraftInfo("abc123", "N1TEST", "B738")
M_PER_DEG_LAT = 111_194.9


def mk(i: int, sec: float, lat: float | None = 0.0, lon: float | None = 0.0, **kw: Any) -> Obs:
    kw.setdefault("source", "s1")
    return Obs(id=i, t=T0 + timedelta(seconds=sec), lat=lat, lon=lon, **kw)


def cruise(
    n: int,
    *,
    speed: float = 200.0,
    step: float = 1.0,
    start_id: int = 1,
    t0: float = 0.0,
    lat0: float = 0.0,
    lon0: float = 0.0,
    **kw: object,
) -> list[Obs]:
    """Level eastbound flight along the equator at `speed` m/s, one fix every `step` s."""
    out = []
    for k in range(n):
        lon = lon0 + (speed * step * k) / M_PER_DEG_LAT
        out.append(
            mk(
                start_id + k,
                t0 + step * k,
                lat0,
                lon,
                baro_altitude_m=10_000.0,
                geo_altitude_m=10_300.0,
                velocity_ms=speed,
                heading_deg=90.0,
                vertical_rate_ms=0.0,
                on_ground=False,
                **kw,
            )
        )
    return out


def circle(
    n: int,
    *,
    radius_m: float,
    speed: float,
    step: float = 1.0,
    start_id: int = 1,
    t0: float = 0.0,
    center: tuple[float, float] = (45.0, 10.0),
    clockwise: bool = True,
) -> list[Obs]:
    """Constant-speed circular track; heading increments consistently with the path."""
    out, omega = [], speed / radius_m  # rad/s
    for k in range(n):
        th = omega * step * k * (1 if clockwise else -1)
        lat = center[0] + (radius_m * math.sin(th)) / M_PER_DEG_LAT
        lon = center[1] + (radius_m * (1 - math.cos(th))) / (
            M_PER_DEG_LAT * math.cos(math.radians(center[0]))
        )
        hdg = (math.degrees(th) + (0 if clockwise else 0)) % 360.0
        out.append(
            mk(
                start_id + k,
                t0 + step * k,
                lat,
                lon,
                baro_altitude_m=3000.0,
                geo_altitude_m=3100.0,
                velocity_ms=speed,
                heading_deg=hdg if clockwise else (360 - hdg) % 360,
                on_ground=False,
            )
        )
    return out
