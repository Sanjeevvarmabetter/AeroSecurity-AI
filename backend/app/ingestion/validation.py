"""Normalisation and validation of untrusted provider records.

Policy: ingestion enforces *format and physical-possibility* only. Values that are merely implausible
(e.g. 900 m/s) are stored unchanged so the detection engine can see them. Values that are impossible as a
number (NaN, negative speed, lat > 90) are stored as NULL, flagged in raw["issues"], and the original text
is preserved in raw["rejected_values"].
"""

import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.ingestion.schema import NormalizedObservation, Rejection

_HEX6 = re.compile(r"^[0-9a-f]{6}$")
_SQUAWK = re.compile(r"^[0-7]{4}$")
_EPOCH_MIN = datetime(1990, 1, 1, tzinfo=UTC).timestamp()
_MAX_SPEED_MS = 10_000.0  # beyond any physical aircraft; below this is left to DET-002
_MAX_ALT_M = 100_000.0
_MAX_VRATE_MS = 1_000.0


def _present(v: Any) -> bool:
    return v is not None and not (isinstance(v, str) and v.strip().lower() in ("", "nan", "none", "null"))


def _to_float(v: Any) -> float | None:
    """Float or None if absent. Raises ValueError if present but not a finite number."""
    if not _present(v):
        return None
    f = float(v)
    if not math.isfinite(f):
        raise ValueError("non-finite")
    return f


def _to_dt(v: Any) -> datetime | None:
    f = _to_float(v)
    if f is None:
        return None
    if not (_EPOCH_MIN <= f <= datetime.now(UTC).timestamp() + 86_400):
        raise ValueError("timestamp out of range")
    return datetime.fromtimestamp(f, UTC)


def _to_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if not _present(v):
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "t"):
        return True
    if s in ("false", "0", "f"):
        return False
    raise ValueError("not a boolean")


def normalize(rec: Mapping[str, Any], row: int | None = None) -> NormalizedObservation | Rejection:
    """Convert a canonical-keyed record (see ObservationProvider implementations) into an observation."""
    icao = str(rec.get("icao24") or "").strip().lower()
    if not _HEX6.match(icao):
        return Rejection("invalid_icao24", row)

    issues: list[str] = []
    rejected: dict[str, Any] = {}

    def num(key: str, lo: float, hi: float) -> float | None:
        v = rec.get(key)
        try:
            f = _to_float(v)
        except (ValueError, TypeError):
            issues.append(f"invalid_{key}")
            rejected[key] = str(v)[:32]
            return None
        if f is not None and not (lo <= f <= hi):
            issues.append(f"invalid_{key}")
            rejected[key] = f
            return None
        return f

    try:
        observed_at = _to_dt(rec.get("observed_at")) or _to_dt(rec.get("last_contact"))
    except (ValueError, TypeError):
        return Rejection("invalid_timestamp", row)
    if observed_at is None:
        return Rejection("missing_timestamp", row)
    try:
        last_contact = _to_dt(rec.get("last_contact"))
    except (ValueError, TypeError):
        last_contact = None
        issues.append("invalid_last_contact")

    lat, lon = num("lat", -90.0, 90.0), num("lon", -180.0, 180.0)
    if lat is None or lon is None:
        if lat is None and lon is None and "invalid_lat" not in issues and "invalid_lon" not in issues:
            issues.append("missing_coordinates")
        else:
            issues.append("invalid_coordinates")
        lat = lon = None

    try:
        on_ground = _to_bool(rec.get("on_ground"))
    except ValueError:
        on_ground = None
        issues.append("invalid_on_ground")

    squawk = None
    if _present(rec.get("squawk")):
        sq = str(rec["squawk"]).strip()
        if _SQUAWK.match(sq):
            squawk = sq
        else:
            issues.append("invalid_squawk")
            rejected["squawk"] = sq[:8]

    callsign = str(rec["callsign"]).strip()[:16] if _present(rec.get("callsign")) else None
    country = str(rec["origin_country"]).strip()[:64] if _present(rec.get("origin_country")) else None
    ps = rec.get("position_source")
    position_source = int(ps) if isinstance(ps, int | float) and not isinstance(ps, bool) else None

    baro = num("baro_altitude_m", -1_000.0, _MAX_ALT_M)
    geo = num("geo_altitude_m", -1_000.0, _MAX_ALT_M)
    velocity = num("velocity_ms", 0.0, _MAX_SPEED_MS)
    heading = num("heading_deg", 0.0, 360.0)
    vrate = num("vertical_rate_ms", -_MAX_VRATE_MS, _MAX_VRATE_MS)

    raw: dict[str, Any] = dict(rec.get("extra") or {})
    if issues:
        raw["issues"] = issues
    if rejected:
        raw["rejected_values"] = rejected

    return NormalizedObservation(
        icao24=icao,
        observed_at=observed_at,
        last_contact_at=last_contact,
        callsign=callsign or None,
        lat=lat,
        lon=lon,
        baro_altitude_m=baro,
        geo_altitude_m=geo,
        on_ground=on_ground,
        velocity_ms=velocity,
        heading_deg=heading,
        vertical_rate_ms=vrate,
        squawk=squawk,
        position_source=position_source,
        origin_country=country,
        raw=raw,
    )
