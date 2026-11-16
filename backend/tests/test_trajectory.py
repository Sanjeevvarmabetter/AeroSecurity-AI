"""Pure-function tests with hand-checkable geometry (synthetic points, not observations)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.aviation.aircraft_category import classify_aircraft_category
from app.aviation.geo import (
    EARTH_RADIUS_M,
    angular_difference_deg,
    haversine_m,
    initial_bearing_deg,
    turn_rate_deg_s,
)
from app.aviation.trajectory import TrackPoint, build_segments, summarize

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def pt(sec: float, lat: float, lon: float, **kw: float | None) -> TrackPoint:
    return TrackPoint(T0 + timedelta(seconds=sec), lat, lon, **kw)  # type: ignore[arg-type]


def test_haversine_known_distances() -> None:
    assert haversine_m(0, 0, 0, 0) == 0
    one_degree = 2 * 3.141592653589793 * EARTH_RADIUS_M / 360
    assert haversine_m(0, 0, 0, 1) == pytest.approx(one_degree, rel=1e-9)  # equator
    assert haversine_m(0, 0, 1, 0) == pytest.approx(one_degree, rel=1e-9)  # meridian
    # London Heathrow -> New York JFK ~ 5,540 km (published great-circle value 5,540 +/- 20 km)
    assert haversine_m(51.4700, -0.4543, 40.6413, -73.7781) / 1000 == pytest.approx(5540, abs=25)
    assert haversine_m(0, 179.5, 0, -179.5) == pytest.approx(one_degree, rel=1e-9)  # antimeridian
    assert haversine_m(10, 20, -30, 70) == pytest.approx(haversine_m(-30, 70, 10, 20))  # symmetric


def test_longitude_degree_shrinks_with_latitude() -> None:
    assert haversine_m(60, 0, 60, 1) == pytest.approx(haversine_m(0, 0, 0, 1) / 2, rel=2e-3)


def test_segment_derived_vs_reported_are_separate() -> None:
    p = [
        pt(0, 0, 0, velocity_ms=100.0, baro_altitude_m=1000.0),
        pt(10, 0, 0.01, velocity_ms=140.0, baro_altitude_m=1100.0),
    ]
    (s,) = build_segments(p)
    assert s.dt_s == 10 and s.distance_m == pytest.approx(1111.95, rel=1e-3)
    assert s.derived_speed_ms == pytest.approx(111.2, rel=1e-3)
    assert s.reported_speed_ms == 120.0  # mean of reported endpoints, untouched by the derived value
    assert s.derived_vertical_rate_ms == pytest.approx(10.0) and not s.is_gap


def test_missing_values_stay_none() -> None:
    (s,) = build_segments([pt(0, 0, 0), pt(5, 0, 0.001)])
    assert s.reported_speed_ms is None and s.baro_delta_m is None and s.derived_vertical_rate_ms is None


def test_vertical_rate_falls_back_to_geometric_altitude() -> None:
    (s,) = build_segments([pt(0, 0, 0, geo_altitude_m=0.0), pt(10, 0, 0.001, geo_altitude_m=-50.0)])
    assert s.baro_delta_m is None and s.derived_vertical_rate_ms == -5.0


def test_zero_dt_has_no_derived_speed() -> None:
    (s,) = build_segments([pt(0, 0, 0), pt(0, 0, 0.5)])
    assert s.derived_speed_ms is None and s.dt_s == 0


def test_gap_detection_and_summary_excludes_gaps_from_distance() -> None:
    p = [
        pt(0, 0, 0, baro_altitude_m=0.0),
        pt(10, 0, 0.01, baro_altitude_m=50.0),
        pt(1010, 0, 1.0, baro_altitude_m=9000.0),
        pt(1020, 0, 1.01, baro_altitude_m=9100.0),
    ]
    segs = build_segments(p, gap_s=120)
    assert [s.is_gap for s in segs] == [False, True, False]
    sm = summarize(p, segs)
    assert (sm.gap_count, sm.gap_total_s, sm.longest_gap_s) == (1, 1000.0, 1000.0)
    assert sm.observed_distance_m == pytest.approx(2 * 1111.95, rel=1e-3)  # the 1000 s jump is not counted
    assert (sm.min_baro_altitude_m, sm.max_baro_altitude_m) == (0.0, 9100.0)
    assert sm.median_interval_s == 10.0 and sm.duration_s == 1020 and sm.points == 4


def test_empty_and_single_point() -> None:
    assert summarize([], []).points == 0 and summarize([], []).start is None
    one = [pt(0, 1, 1)]
    sm = summarize(one, build_segments(one))
    assert sm.segments == 0 and sm.observed_distance_m == 0 and sm.median_interval_s is None


def test_initial_bearing_cardinal_directions() -> None:
    assert initial_bearing_deg(0, 0, 0, 0) == 0.0
    assert initial_bearing_deg(0, 0, 1, 0) == pytest.approx(0.0, abs=1e-5)  # due North
    assert initial_bearing_deg(0, 0, 0, 1) == pytest.approx(90.0, abs=1e-5)  # due East
    assert initial_bearing_deg(0, 0, -1, 0) == pytest.approx(180.0, abs=1e-5)  # due South
    assert initial_bearing_deg(0, 0, 0, -1) == pytest.approx(270.0, abs=1e-5)  # due West


def test_angular_difference_and_turn_rate() -> None:
    assert angular_difference_deg(0, 0) == 0.0
    assert angular_difference_deg(10, 350) == 20.0
    assert angular_difference_deg(350, 10) == 20.0
    assert angular_difference_deg(0, 180) == 180.0
    assert turn_rate_deg_s(10, 40, 10.0) == pytest.approx(3.0)
    assert turn_rate_deg_s(350, 10, 4.0) == pytest.approx(5.0)
    assert turn_rate_deg_s(10, 20, 0.0) is None


def test_derived_bearing_and_acceleration_in_segments() -> None:
    p = [
        pt(0, 0, 0, velocity_ms=100.0, vertical_rate_ms=5.0, baro_altitude_m=1000.0, heading_deg=90.0),
        pt(10, 0, 0.01, velocity_ms=120.0, vertical_rate_ms=7.0, baro_altitude_m=1050.0, heading_deg=90.0),
    ]
    (s,) = build_segments(p)
    assert s.derived_bearing_deg == pytest.approx(90.0, abs=0.1)
    assert s.reported_heading_deg == 90.0
    assert s.derived_acceleration_ms2 == pytest.approx(2.0)  # (120 - 100) / 10 s
    assert s.reported_vertical_rate_ms == 6.0  # mean of 5 and 7
    assert s.derived_vertical_rate_ms == pytest.approx(5.0)  # (1050 - 1000) / 10 s
    assert s.vertical_rate_delta_ms == pytest.approx(-1.0)  # derived (5) - reported (6)


def test_aircraft_category_classification() -> None:
    assert classify_aircraft_category("A320") == "JET"
    assert classify_aircraft_category("B738") == "JET"
    assert classify_aircraft_category("LJ60") == "JET"
    assert classify_aircraft_category("DH8D") == "TURBOPROP"
    assert classify_aircraft_category("AT72") == "TURBOPROP"
    assert classify_aircraft_category("C172") == "PISTON"
    assert classify_aircraft_category("PA28") == "PISTON"
    assert classify_aircraft_category("R44") == "HELICOPTER"
    assert classify_aircraft_category("EC35") == "HELICOPTER"
    assert classify_aircraft_category("MQ9") == "DRONE_UAV"
    assert classify_aircraft_category(None, "Boeing 777-300ER") == "JET"
    assert classify_aircraft_category(None, "Robinson R22 Beta") == "HELICOPTER"
    assert classify_aircraft_category("XYZ999") == "UNKNOWN"
