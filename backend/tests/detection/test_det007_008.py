from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from app.detection.config import Det007Config, Det008Config
from app.detection.rules.det007 import UnusualTrajectory
from app.detection.rules.det008 import AbnormalAirportTraffic
from app.detection.types import AirportTraffic, Finding, Obs, Severity
from tests.detection.helpers import AC, T0, circle, cruise, mk

# ---- DET-007 ------------------------------------------------------------------------------------


def d7(obs: Sequence[Obs], **cfg: Any) -> list[Finding]:
    return UnusualTrajectory(Det007Config(**cfg)).detect(AC, obs)


def hard_turn(n: int, start_id: int, t0: float, rate_dps: float, lon0: float) -> list:  # type: ignore[type-arg]
    return [
        mk(
            start_id + i,
            t0 + i,
            0.0,
            lon0 + i * 0.001,
            velocity_ms=200.0,
            heading_deg=(90.0 + rate_dps * i) % 360.0,
            on_ground=False,
            baro_altitude_m=9000.0,
        )
        for i in range(n)
    ]


def test_insufficient_history_yields_nothing() -> None:
    assert d7(hard_turn(100, 1, 0.0, 12.0, 0.0)) == []  # 100 positions, far below the baseline minimum


def test_straight_flight_is_normal() -> None:
    assert d7(cruise(1500)) == []


def test_sustained_extreme_turn_relative_to_own_baseline_is_flagged() -> None:
    obs = (
        cruise(1000)
        + hard_turn(90, 2000, 1000.0, 12.0, 1.0)
        + cruise(500, start_id=3000, t0=1090.0, lon0=2.0)
    )
    fs = [f for f in d7(obs) if f.summary["check"] == "turn_rate"]
    assert len(fs) == 1
    f = fs[0]
    assert f.severity is Severity.LOW and f.confidence <= 0.6 and f.summary["peak_dps"] >= 6
    m = f.evidence[-1].payload
    assert m["baseline_median_dps"] < 0.5 and m["robust_z"] > 8
    assert any("Holding pattern" in a for a in f.alternatives)


def test_orbit_over_small_area_is_flagged_but_large_circle_is_not() -> None:
    padding = cruise(500)
    tight = circle(700, radius_m=3000.0, speed=80.0, start_id=1000, t0=500.0)  # >2 loops, 3 km radius
    fs = [f for f in d7(padding + tight) if f.summary["check"] == "orbit"]
    assert fs and fs[0].summary["rotation_deg"] >= 540
    wide = circle(700, radius_m=30_000.0, speed=200.0, start_id=1000, t0=500.0)
    assert [f for f in d7(padding + wide) if f.summary["check"] == "orbit"] == []


def test_orbit_does_not_stitch_across_an_observation_gap() -> None:
    half = circle(120, radius_m=3000.0, speed=80.0, start_id=1000, t0=500.0)
    later = circle(120, radius_m=3000.0, speed=80.0, start_id=2000, t0=500.0 + 120 + 300)
    assert [f for f in d7(cruise(500) + half + later) if f.summary["check"] == "orbit"] == []


# ---- DET-008 ------------------------------------------------------------------------------------


def traffic(counts: list[int]) -> AirportTraffic:
    return AirportTraffic(
        "TSTA", "Testville Intl", {T0 + timedelta(hours=i): n for i, n in enumerate(counts)}
    )


def d8(counts: list[int], **cfg: Any) -> list[Finding]:
    return AbnormalAirportTraffic(Det008Config(**cfg)).detect(traffic(counts))


def test_spike_against_own_baseline_is_flagged_with_disclaimers() -> None:
    base = [4, 5, 3, 4, 5, 4] * 8
    (f,) = d8(base + [40] + base[:6])
    assert (
        f.airport_ident == "TSTA" and f.icao24 is None and f.severity is Severity.LOW and f.confidence <= 0.5
    )
    assert "does not indicate a security incident" in f.description
    assert f.summary["peak_aircraft"] == 40 and f.summary["baseline_median"] == 4


def test_consecutive_spike_hours_are_one_event() -> None:
    base = [4, 5, 3, 4, 5, 4] * 8
    (f,) = d8(base + [30, 35] + base[:6])
    assert f.summary["hours"] == 2


def test_short_baseline_small_spikes_and_drops_are_ignored() -> None:
    assert d8([4, 5, 40]) == []  # too little history
    base = [0, 1, 0, 0, 1, 0] * 8
    assert d8(base + [3]) == []  # tiny absolute number
    assert d8([20, 21, 19, 22] * 12 + [0]) == []  # a drop looks the same as a receiver outage: not reported
