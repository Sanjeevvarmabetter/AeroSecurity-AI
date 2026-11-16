from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from typing import ClassVar

from pydantic import BaseModel

from app.detection.types import AircraftInfo, AirportTraffic, Finding, Obs


class AircraftRule(ABC):
    """A rule evaluated per aircraft over its time-ordered observations. Pure: no I/O."""

    rule_id: ClassVar[str]
    name: ClassVar[str]
    version: ClassVar[str]
    description: ClassVar[str]
    config_model: ClassVar[type[BaseModel]]

    def __init__(self, config: BaseModel | None = None) -> None:
        self.cfg = config if config is not None else self.config_model()

    @abstractmethod
    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        """`obs` is sorted by time ascending."""


class AirportRule(ABC):
    rule_id: ClassVar[str]
    name: ClassVar[str]
    version: ClassVar[str]
    description: ClassVar[str]
    config_model: ClassVar[type[BaseModel]]

    def __init__(self, config: BaseModel | None = None) -> None:
        self.cfg = config if config is not None else self.config_model()

    @abstractmethod
    def detect(self, traffic: AirportTraffic) -> list[Finding]: ...


def group_runs[T](items: Iterable[T], time_of: Callable[[T], float], join_s: float) -> list[list[T]]:
    """Group time-ordered items into runs where consecutive items are at most `join_s` apart."""
    runs: list[list[T]] = []
    for it in items:
        if runs and time_of(it) - time_of(runs[-1][-1]) <= join_s:
            runs[-1].append(it)
        else:
            runs.append([it])
    return runs


def obs_evidence(o: Obs, **extra: object) -> dict[str, object]:
    """Compact, JSON-safe snapshot of an observation for evidence payloads."""
    return {
        "t": o.t.isoformat(),
        "lat": o.lat,
        "lon": o.lon,
        "baro_altitude_m": o.baro_altitude_m,
        "geo_altitude_m": o.geo_altitude_m,
        "velocity_ms": o.velocity_ms,
        "heading_deg": o.heading_deg,
        "vertical_rate_ms": o.vertical_rate_ms,
        "squawk": o.squawk,
        "on_ground": o.on_ground,
        "source": o.source,
        **extra,
    }


def latlon(o: Obs) -> tuple[float, float]:
    """Coordinates of an observation that is known to have a position."""
    if o.lat is None or o.lon is None:
        raise ValueError("observation has no position")
    return o.lat, o.lon
