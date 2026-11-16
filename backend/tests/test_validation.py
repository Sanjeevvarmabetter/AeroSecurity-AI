"""Synthetic records (test data, not real observations)."""

from datetime import UTC, datetime

from app.ingestion.schema import NormalizedObservation, Rejection
from app.ingestion.validation import normalize

T = 1_790_739_541.0


def rec(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "icao24": "A1B2C3",
        "observed_at": T,
        "lat": "26.4",
        "lon": "51.3",
        "velocity_ms": "226.4",
        "heading_deg": "289.5",
        "squawk": "0527",
        "callsign": "FDB1073 ",
        "on_ground": "False",
    }
    return {**base, **kw}


def ok(r: object) -> NormalizedObservation:
    assert isinstance(r, NormalizedObservation), r
    return r


def test_valid_record_normalised() -> None:
    o = ok(normalize(rec()))
    assert o.icao24 == "a1b2c3" and o.callsign == "FDB1073" and o.squawk == "0527"
    assert o.observed_at == datetime.fromtimestamp(T, UTC) and o.on_ground is False
    assert "issues" not in o.raw


def test_bad_identity_or_time_is_rejected() -> None:
    assert normalize(rec(icao24="xyz"), 7) == Rejection("invalid_icao24", 7)
    assert normalize(rec(icao24=None)) == Rejection("invalid_icao24", None)
    assert normalize(rec(observed_at=None)) == Rejection("missing_timestamp", None)
    assert normalize(rec(observed_at="abc")) == Rejection("invalid_timestamp", None)
    assert normalize(rec(observed_at=5.0)) == Rejection("invalid_timestamp", None)


def test_absent_fields_stay_none_and_missing_coordinates_flagged() -> None:
    o = ok(normalize(rec(lat="", lon="", velocity_ms=None, squawk="", callsign="")))
    assert o.lat is None and o.velocity_ms is None and o.squawk is None and o.callsign is None
    assert o.raw["issues"] == ["missing_coordinates"]


def test_out_of_range_coordinates_nulled_and_original_kept() -> None:
    o = ok(normalize(rec(lat="91.5")))
    assert o.lat is None and o.lon is None  # a half position is not a position
    assert "invalid_coordinates" in o.raw["issues"] and o.raw["rejected_values"]["lat"] == 91.5


def test_impossible_numbers_nulled_but_implausible_preserved_for_detection() -> None:
    o = ok(normalize(rec(velocity_ms="-5", heading_deg="400")))
    assert o.velocity_ms is None and o.heading_deg is None
    assert o.raw["rejected_values"] == {"velocity_ms": -5.0, "heading_deg": 400.0}
    fast = ok(normalize(rec(velocity_ms="900")))  # implausible for most aircraft, but DET-002's call
    assert fast.velocity_ms == 900.0
    assert ok(normalize(rec(velocity_ms="nan"))).velocity_ms is None


def test_squawk_must_be_four_octal_digits() -> None:
    for bad in ("7800", "123", "abcd", "12345"):
        o = ok(normalize(rec(squawk=bad)))
        assert o.squawk is None and "invalid_squawk" in o.raw["issues"]
    assert ok(normalize(rec(squawk="7700"))).squawk == "7700"


def test_untrusted_strings_are_truncated() -> None:
    o = ok(normalize(rec(callsign="A" * 500, origin_country="B" * 500)))
    assert len(o.callsign or "") == 16 and len(o.origin_country or "") == 64
