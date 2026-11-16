from collections.abc import Sequence
from typing import Any

from app.detection.config import Det002Config, Det003Config
from app.detection.rules.det002 import ImplausibleVelocity
from app.detection.rules.det003 import AltitudeAnomaly
from app.detection.types import AircraftInfo, DataQuality, Finding, Obs, Severity
from tests.detection.helpers import AC, cruise, mk

D2, D3 = ImplausibleVelocity, AltitudeAnomaly


def d2(obs: Sequence[Obs], ac: AircraftInfo = AC, **cfg: Any) -> list[Finding]:
    return D2(Det002Config(**cfg)).detect(ac, obs)


def d3(obs: Sequence[Obs], **cfg: Any) -> list[Finding]:
    return D3(Det003Config(**cfg)).detect(AC, obs)


# ---- DET-002 ------------------------------------------------------------------------------------
def test_normal_speed_clean() -> None:
    assert d2(cruise(100, speed=240.0)) == []


def test_type_specific_limit_is_applied() -> None:
    obs = cruise(10, speed=150.0)
    assert d2(obs, AircraftInfo("abc123", None, "B738")) == []  # fine for an airliner
    (f,) = d2(obs, AircraftInfo("abc123", None, "PA46"))  # impossible for a PA-46
    assert f.summary["limit_source"] == "type_override:PA46" and f.summary["limit_ms"] == 120.0
    assert f.severity is Severity.LOW  # 150/120 = 1.25, below the 1.3 MEDIUM tier


def test_severity_tiers_and_unknown_type_is_partial() -> None:
    unknown = AircraftInfo("abc123", None, None)
    for speed, sev in ((400.0, Severity.LOW), (500.0, Severity.MEDIUM), (800.0, Severity.HIGH)):
        (f,) = d2(cruise(5, speed=speed), unknown)
        assert f.severity is sev, speed
        assert f.data_quality is DataQuality.PARTIAL  # default limit used because the type is unknown


def test_isolated_velocity_glitch_yields_speed_and_acceleration_findings() -> None:
    obs = cruise(10, speed=230.0)
    obs[5] = mk(obs[5].id, 5.0, 0.0, obs[5].lon, velocity_ms=440.0)
    kinds = sorted(f.title.split()[0] for f in d2(obs))
    assert kinds == ["Implausible", "Reported"]


def test_timestamp_jitter_does_not_create_false_acceleration() -> None:
    a, b = mk(1, 0.0, velocity_ms=230.0), mk(2, 0.2, velocity_ms=250.0)  # 20 m/s in 0.2 s
    assert d2([a, b]) == []


# ---- DET-003 ------------------------------------------------------------------------------------
def test_level_flight_and_normal_climb_clean() -> None:
    climb = [
        mk(
            i,
            float(i),
            0.0,
            0.0,
            baro_altitude_m=1000.0 + 10 * i,
            geo_altitude_m=1100.0 + 10 * i,
            vertical_rate_ms=10.0,
            on_ground=False,
        )
        for i in range(60)
    ]
    assert d3(cruise(100)) == [] and d3(climb) == []


def test_impossible_altitude_change() -> None:
    obs = cruise(4)
    obs[2] = mk(
        obs[2].id, 2.0, 0.0, obs[2].lon, baro_altitude_m=13_000.0, geo_altitude_m=10_300.0, on_ground=False
    )
    kinds = {f.summary["check"] for f in d3(obs)}
    assert "impossible_change" in kinds


def test_reported_vertical_rate_unsupported_by_altitude_series() -> None:
    """Mirrors the documented real case: reported -108 m/s while altitude supports ~17 m/s."""
    a = mk(1, 0.0, baro_altitude_m=5000.0, geo_altitude_m=5100.0, vertical_rate_ms=-108.0, on_ground=False)
    b = mk(2, 10.0, baro_altitude_m=4832.0, geo_altitude_m=4932.0, vertical_rate_ms=-108.0, on_ground=False)
    (f,) = d3([a, b])
    assert f.summary["check"] == "vertical_rate_mismatch" and f.data_quality is DataQuality.PARTIAL
    assert f.confidence <= 0.75  # the broadcast vertical-rate field is known to be noisy
    # Same reported rate WITH a matching altitude change is consistent:
    c = mk(3, 10.0, baro_altitude_m=3920.0, geo_altitude_m=4020.0, vertical_rate_ms=-108.0, on_ground=False)
    assert d3([a, c]) == [] or all(x.summary["check"] != "vertical_rate_mismatch" for x in d3([a, c]))


def test_baro_geo_divergence_tiers() -> None:
    def case(diff: float) -> list:  # type: ignore[type-arg]
        return d3(
            [
                mk(
                    i,
                    float(i),
                    0.0,
                    0.0,
                    baro_altitude_m=8000.0,
                    geo_altitude_m=8000.0 + diff,
                    on_ground=False,
                )
                for i in range(6)
            ]
        )

    assert case(1000.0) == []  # normal pressure/geoid effects
    assert case(2000.0)[0].severity is Severity.MEDIUM
    assert case(-3800.0)[0].severity is Severity.HIGH


def test_on_ground_contradiction_and_normal_ground_obs() -> None:
    ok = [
        mk(1, 0.0, baro_altitude_m=None, geo_altitude_m=None, on_ground=True)
    ]  # baro absent on ground: normal
    assert d3(ok) == []
    (f,) = d3([mk(1, 0.0, baro_altitude_m=9000.0, on_ground=True)])
    assert f.summary["check"] == "on_ground_contradiction"


def test_missing_altitude_requires_a_sustained_run() -> None:
    def no_alt(n: int) -> list[Obs]:
        return [mk(i, float(i), 0.0, 0.0, on_ground=False) for i in range(n)]

    assert d3(no_alt(5)) == []
    (f,) = d3(no_alt(12))
    assert f.severity is Severity.LOW and f.data_quality is DataQuality.DEGRADED
