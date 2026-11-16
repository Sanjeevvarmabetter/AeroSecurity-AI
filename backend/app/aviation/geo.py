"""Geodesy helpers. Spherical Earth model (mean radius); WGS84 error is at most about 0.5%."""

import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 lat/lon points given in degrees."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing (azimuth) from point 1 to point 2, in degrees [0, 360)."""
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    x = math.sin(dlmb) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlmb)
    deg = math.degrees(math.atan2(x, y))
    return (deg + 360.0) % 360.0


def angular_difference_deg(angle1: float, angle2: float) -> float:
    """Smallest positive angular difference between two compass headings in degrees [0, 180]."""
    diff = abs(angle1 - angle2) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


def turn_rate_deg_s(heading1: float, heading2: float, dt_s: float) -> float | None:
    """Turn rate in degrees per second between two headings over dt_s seconds."""
    if dt_s <= 0:
        return None
    return angular_difference_deg(heading1, heading2) / dt_s
