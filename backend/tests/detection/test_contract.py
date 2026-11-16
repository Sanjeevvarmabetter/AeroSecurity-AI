"""Invariants that EVERY finding from EVERY rule must satisfy (the detection output contract)."""

import json
import re
from datetime import timedelta

import pytest

from app.detection.rules import AIRCRAFT_RULES, AIRPORT_RULES, ALL_RULES
from app.detection.types import SEVERITY_ORDER, AirportTraffic, Finding, Obs
from tests.detection.helpers import AC, T0, circle, cruise, mk


def scenarios() -> list[Obs]:
    teleport = cruise(5) + [mk(100, 9.0, 0.0, 1.0, velocity_ms=200.0, source="opensky")]
    glitch = cruise(10, start_id=200, t0=1000.0)
    glitch[5] = mk(
        glitch[5].id,
        1005.0,
        0.0,
        glitch[5].lon,
        velocity_ms=900.0,
        baro_altitude_m=14_000.0,
        geo_altitude_m=9_000.0,
        vertical_rate_ms=-120.0,
        on_ground=False,
    )
    emergency = [mk(300 + i, 2000.0 + i, 10.0, 20.0, squawk="7700") for i in range(5)]
    dirty = [mk(400 + i, 3000.0 + i, None, None, issues=("invalid_squawk",)) for i in range(3)]
    other_source = [mk(500 + i, 1000.0 + i, 3.0, 1.0, source="adsbx") for i in range(5)]
    orbit = cruise(500, start_id=1000, t0=4000.0) + circle(
        700, radius_m=3000.0, speed=80.0, start_id=2000, t0=4500.0
    )
    return sorted(teleport + glitch + emergency + dirty + other_source + orbit, key=lambda o: o.ts)


def all_findings() -> list[Finding]:
    obs = scenarios()
    out = [f for cls in AIRCRAFT_RULES.values() for f in cls().detect(AC, obs)]
    spike = AirportTraffic(
        "TSTA", "Testville", {T0 + timedelta(hours=i): n for i, n in enumerate([4, 5, 3, 4, 5, 4] * 8 + [40])}
    )
    out += [f for cls in AIRPORT_RULES.values() for f in cls().detect(spike)]
    return out


FINDINGS = all_findings()


def test_every_rule_is_exercised_by_the_fixture() -> None:
    assert {f.rule_id for f in FINDINGS} == set(ALL_RULES)


@pytest.mark.parametrize("f", FINDINGS, ids=lambda f: f"{f.rule_id}:{f.dedup_key}")
def test_finding_satisfies_the_output_contract(f: Finding) -> None:
    assert re.fullmatch(r"DET-00[1-8]", f.rule_id) and f.detection_type and f.title and f.description
    assert f.severity in SEVERITY_ORDER and 0.0 <= f.confidence <= 1.0
    assert f.event_start <= f.event_end and f.dedup_key
    assert (f.icao24 is None) != (f.airport_ident is None)  # exactly one subject
    assert f.evidence, "a detection without evidence is not allowed"
    assert f.alternatives, "benign explanations must always be listed"
    json.dumps([e.payload for e in f.evidence] + [f.summary])  # evidence must be JSON-serialisable
    assert all(e.kind in {"observation", "metric", "context"} for e in f.evidence)
    text = f"{f.title} {f.description}".lower()
    for banned in ("is spoofing", "was spoofed", "attack", "malicious", "hijack", "terror", "crash"):
        assert banned not in text, f"finding asserts intent/cause: {banned!r}"


def test_rules_are_deterministic_and_do_not_mutate_input() -> None:
    obs = scenarios()
    snapshot = list(obs)
    first = [
        (f.rule_id, f.dedup_key, f.severity, f.confidence)
        for cls in AIRCRAFT_RULES.values()
        for f in cls().detect(AC, obs)
    ]
    second = [
        (f.rule_id, f.dedup_key, f.severity, f.confidence)
        for cls in AIRCRAFT_RULES.values()
        for f in cls().detect(AC, obs)
    ]
    assert first == second and obs == snapshot


def test_registry_is_complete_and_versioned() -> None:
    assert sorted(ALL_RULES) == [f"DET-00{i}" for i in range(1, 9)]
    for rid, cls in ALL_RULES.items():
        assert cls.rule_id == rid and cls.name and cls.description
        assert re.fullmatch(r"\d+\.\d+\.\d+", cls.version)
        with pytest.raises(Exception):  # noqa: B017,PT011  (extra="forbid": typos in config must fail loudly)
            cls.config_model.model_validate({"definitely_not_a_setting": 1})
