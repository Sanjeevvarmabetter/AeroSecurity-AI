from collections.abc import Sequence
from typing import Any

import pytest

from app.detection.config import Det001Config
from app.detection.rules.det001 import ImpossiblePositionTransition
from app.detection.types import DataQuality, Finding, Obs, Severity
from tests.detection.helpers import AC, M_PER_DEG_LAT, cruise, mk

RULE = ImpossiblePositionTransition


def detect(obs: Sequence[Obs], **cfg: Any) -> list[Finding]:
    return RULE(Det001Config(**cfg)).detect(AC, obs)


def test_normal_flight_has_no_findings() -> None:
    assert detect(cruise(300, speed=250.0)) == []


def test_teleport_is_high_severity_with_full_evidence() -> None:
    obs = cruise(5) + [mk(100, 9.0, 0.0, 1.0, velocity_ms=200.0)]  # ~111 km in ~5 s
    (f,) = detect(obs)
    assert f.severity is Severity.HIGH and f.detection_type == "POSITION_ANOMALY"
    assert 0.5 < f.confidence <= 0.95 and f.icao24 == "abc123"
    roles = [e.payload.get("role") for e in f.evidence if e.kind == "observation"]
    assert roles == ["from", "to"] and f.evidence[-1].kind == "metric"
    m = f.evidence[-1].payload
    assert m["required_speed_lower_bound_ms"] > 1000 and m["tolerances"]["timestamp_s"] == 1.0
    assert f.alternatives and "Deliberate position falsification" in f.alternatives[-1]


def test_single_outlier_out_and_back_is_one_episode() -> None:
    obs = cruise(10)
    obs[5] = mk(obs[5].id, 5.0, 1.0, 5.0, velocity_ms=200.0)  # one bad point ~111 km north
    (f,) = detect(obs)
    assert f.summary["jumps"] == 2  # out and back, grouped


def test_real_world_timestamp_jitter_is_not_flagged() -> None:
    """From real data: 230 m between fixes stamped 0.195 s apart (aircraft at ~232 m/s)."""
    a = mk(1, 0.0, 25.6682522, 53.1718070, velocity_ms=232.2)
    b = mk(2, 0.195, 25.6687643, 53.1695578, velocity_ms=232.2)
    assert detect([a, b]) == []
    # The naive speed would have been >1,100 m/s; the tolerance-adjusted bound is far lower.


def test_fast_but_consistent_with_reported_speed_is_not_flagged() -> None:
    # 400 m/s displacement, aircraft reports 350 m/s: above civil ceiling but not 2x reported.
    a = mk(1, 0.0, 0.0, 0.0, velocity_ms=350.0)
    b = mk(2, 10.0, 0.0, 4000.0 / M_PER_DEG_LAT, velocity_ms=350.0)
    assert detect([a, b]) == []


def test_fast_displacement_without_reported_velocity_is_medium_and_partial() -> None:
    a, b = mk(1, 0.0), mk(2, 10.0, 0.0, 5000.0 / M_PER_DEG_LAT)  # ~500 m/s
    (f,) = detect([a, b])
    assert f.severity is Severity.MEDIUM and f.data_quality is DataQuality.PARTIAL
    assert "no_reported_velocity" in f.summary["penalties"]


def test_long_gap_with_plausible_average_speed_is_fine() -> None:
    a, b = mk(1, 0.0, 0.0, 0.0, velocity_ms=230.0), mk(2, 4476.0, 0.0, 9.0, velocity_ms=230.0)  # ~1,000 km
    assert detect([a, b]) == []


def test_non_adsb_source_lowers_confidence() -> None:
    adsb = detect(
        [
            mk(1, 0.0, position_source=0, velocity_ms=200.0),
            mk(2, 5.0, 0.0, 1.0, position_source=0, velocity_ms=200.0),
        ]
    )[0]
    mlat = detect(
        [
            mk(1, 0.0, position_source=2, velocity_ms=200.0),
            mk(2, 5.0, 0.0, 1.0, position_source=2, velocity_ms=200.0),
        ]
    )[0]
    assert mlat.confidence < adsb.confidence and "non_adsb_position_source" in mlat.summary["penalties"]


def test_observations_without_position_are_skipped() -> None:
    obs = [mk(1, 0.0), mk(2, 1.0, None, None), mk(3, 2.0, 0.0, 0.001)]
    assert detect(obs) == []


def test_deterministic_and_config_overridable() -> None:
    obs = cruise(5) + [mk(100, 9.0, 0.0, 0.2, velocity_ms=200.0)]  # ~22 km in 4 s => ~4,400 m/s
    assert detect(obs) == detect(obs) or [f.dedup_key for f in detect(obs)] == [
        f.dedup_key for f in detect(obs)
    ]
    assert detect(obs, hard_speed_ceiling_ms=1e9, civil_speed_ceiling_ms=1e9) == []


def test_config_rejects_unknown_keys() -> None:
    with pytest.raises(Exception):  # noqa: B017,PT011
        Det001Config(nonsense=1)  # type: ignore[call-arg]
