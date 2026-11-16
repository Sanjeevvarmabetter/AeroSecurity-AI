from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from app.detection.config import Det004Config, Det005Config, Det006Config
from app.detection.rules.det004 import DuplicateIdentity
from app.detection.rules.det005 import EmergencySquawk
from app.detection.rules.det006 import DataIntegrity
from app.detection.types import DataQuality, Finding, Obs, Severity
from tests.detection.helpers import AC, T0, cruise, mk

# ---- DET-004 ------------------------------------------------------------------------------------


def d4(obs: Sequence[Obs]) -> list[Finding]:
    return DuplicateIdentity(Det004Config()).detect(AC, obs)


def test_two_sources_agreeing_is_not_a_conflict() -> None:
    a = cruise(20, source="s1")
    b = cruise(20, source="s2", start_id=100)  # same track, same times
    assert d4(sorted(a + b, key=lambda o: o.ts)) == []


def test_cross_source_conflict_detected_without_claiming_spoofing() -> None:
    a = cruise(10, source="opensky")
    b = [mk(100 + i, float(i), 3.0, 1.0, source="adsbx") for i in range(10)]  # ~330 km away, same instants
    (f,) = d4(sorted(a + b, key=lambda o: o.ts))
    assert f.detection_type == "IDENTITY_CONFLICT" and f.severity is Severity.MEDIUM
    assert f.data_quality is DataQuality.PARTIAL and set(f.sources) == {"opensky", "adsbx"}
    assert "not proof of spoofing" in f.description
    assert any("clock skew" in a for a in f.alternatives) and any("spoofing" in a for a in f.alternatives)


def test_far_apart_in_time_is_not_a_conflict() -> None:
    a = [mk(1, 0.0, 0.0, 0.0, source="s1")]
    b = [mk(2, 600.0, 0.0, 1.0, source="s2")]  # 10 min later, 111 km away: reachable
    assert d4(a + b) == []


def test_interleaved_streams_flagged_but_single_glitch_is_not() -> None:
    obs = []
    for i in range(12):  # alternate between two places 111 km apart, 1 s apart
        obs.append(mk(i, float(i), 0.0 if i % 2 == 0 else 1.0, 0.0))
    (f,) = d4(obs)
    assert f.summary["check"] == "interleaved" and f.summary["jumps"] >= 3
    glitch = cruise(10)
    glitch[5] = mk(glitch[5].id, 5.0, 1.0, glitch[5].lon)  # one bad point only
    assert d4(glitch) == []  # DET-001's job; DET-004 needs alternation


# ---- DET-005 ------------------------------------------------------------------------------------


def d5(obs: Sequence[Obs], **cfg: Any) -> list[Finding]:
    return EmergencySquawk(Det005Config(**cfg)).detect(AC, obs)


def squawks(code: str, n: int, start: float = 0.0, start_id: int = 1, pos: bool = True) -> list[Obs]:
    return [
        mk(
            start_id + i,
            start + i,
            10.0 + i * 0.001 if pos else None,
            20.0 if pos else None,
            squawk=code,
            callsign="TST1",
            baro_altitude_m=3000.0,
        )
        for i in range(n)
    ]


def test_each_code_has_its_own_severity() -> None:
    for code, sev in (("7500", Severity.CRITICAL), ("7700", Severity.HIGH), ("7600", Severity.MEDIUM)):
        (f,) = d5(squawks(code, 5))
        assert f.severity is sev and f.detection_type == "EMERGENCY_SQUAWK" and code in f.title


def test_event_record_contents() -> None:
    (f,) = d5(squawks("7700", 40))
    ctx = f.evidence[-1].payload
    assert ctx["observations"] == 40 and ctx["callsign"] == "TST1"
    assert ctx["last_known_position"]["lat"] == 10.039 and f.sources == ("s1",)
    assert len([e for e in f.evidence if e.kind == "observation"]) <= 13  # capped history
    assert f.event_start == T0 and f.event_end == T0 + timedelta(seconds=39)
    assert any("training" in a.lower() for a in f.alternatives)


def test_last_known_position_falls_back_to_last_positioned_observation() -> None:
    obs = squawks("7700", 5) + [mk(50, 5.0, None, None, squawk="7700")]
    (f,) = d5(obs)
    assert f.evidence[-1].payload["last_known_position"]["lat"] == 10.004


def test_single_observation_is_marked_transient_with_low_confidence() -> None:
    (f,) = d5(squawks("7700", 1))
    assert f.summary["transient"] is True and f.confidence <= 0.3 and "single observation" in f.title
    assert d5(squawks("7700", 6))[0].confidence > f.confidence


def test_separate_episodes_and_ordinary_codes() -> None:
    obs = (
        squawks("7700", 3)
        + squawks("7700", 3, start=1000.0, start_id=100)
        + squawks("1200", 50, start_id=200)
    )
    assert len(d5(obs)) == 2
    assert d5(squawks("1200", 50)) == []


def test_episode_dedup_key_is_stable_when_the_episode_grows() -> None:
    short, longer = d5(squawks("7700", 5))[0], d5(squawks("7700", 9))[0]
    assert short.dedup_key == longer.dedup_key and longer.event_end > short.event_end


# ---- DET-006 ------------------------------------------------------------------------------------


def d6(obs: Sequence[Obs]) -> list[Finding]:
    return DataIntegrity(Det006Config()).detect(AC, obs)


def test_clean_data_has_no_integrity_findings() -> None:
    assert d6(cruise(50)) == []


def test_missing_coordinates_runs_are_grouped() -> None:
    obs = cruise(5) + [mk(10 + i, 5.0 + i, None, None) for i in range(3)] + cruise(5, start_id=20, t0=500.0)
    (f,) = d6(obs)
    assert (
        f.summary == {"check": "missing_coordinates", "observations": 3}
        and f.data_quality is DataQuality.DEGRADED
    )


def test_ingestion_issues_surface_with_run_grouping() -> None:
    obs = [mk(i, float(i), 0.0, 0.0, issues=("invalid_velocity_ms",)) for i in range(4)]
    (f,) = d6(obs)
    assert "invalid_velocity_ms" in f.title and f.summary["observations"] == 4


def test_last_contact_before_position_and_future_timestamp() -> None:
    bad = mk(1, 10.0, last_contact=T0 + timedelta(seconds=5))  # contact 5 s BEFORE the position it covers
    fine = mk(2, 20.0, last_contact=T0 + timedelta(seconds=20))
    assert [f.summary["check"] for f in d6([bad, fine])] == ["last_contact_before_position"]
    fut = mk(3, 100.0, ingested_at=T0)  # observation stamped 100 s after it was ingested
    assert d6([fut])[0].summary["check"] == "timestamp_in_future"
    assert d6([mk(4, 100.0, ingested_at=T0 + timedelta(seconds=200))]) == []


def test_duplicate_records_across_sources() -> None:
    a, b = mk(1, 5.0, 1.0, 2.0, source="s1"), mk(2, 5.0, 1.0, 2.0, source="s2")
    (f,) = d6([a, b])
    assert f.summary["check"] == "duplicate_record"
    assert d6([a, mk(3, 5.0, 1.0, 2.0, source="s1")]) == []  # same source is not cross-source duplication
