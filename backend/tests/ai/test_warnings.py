import pytest

from app.intelligence.service import certainty_warnings


@pytest.mark.parametrize(
    "text",
    [
        "This confirms a deliberate spoofing attack.",
        "The data proves the aircraft was hijacked.",
        "It is definitely a malicious transponder.",
        "The pattern clearly shows sabotage by an outside party.",
        "This was a confirmed cyber attack.",
    ],
)
def test_assertive_claims_are_flagged(text: str) -> None:
    assert certainty_warnings({"what_happened": text}), text


@pytest.mark.parametrize(
    "text",
    [
        "Spoofing cannot be confirmed or excluded from this data alone.",
        "There is no evidence that confirms an attack.",
        "A decoding error is possible; this does not prove malicious activity.",
        "The squawk was observed 212 times over 413 seconds.",
        "Further analysis is unable to confirm a cyber cause.",
    ],
)
def test_hedged_or_neutral_statements_are_not_flagged(text: str) -> None:
    assert certainty_warnings({"limitations": [text]}) == [], text


def test_nested_output_is_scanned() -> None:
    out = {"a": {"b": ["fine", "this definitely proves spoofing"]}, "c": [{"d": "ok"}]}
    assert len(certainty_warnings(out)) == 1
