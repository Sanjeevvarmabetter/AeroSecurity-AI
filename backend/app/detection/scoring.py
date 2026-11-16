"""Confidence helpers. Confidence expresses how sure we are the *data pattern* is genuine and as described
(not an artefact of tolerances). It never expresses the probability of malicious activity."""

import math


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def confidence_from_ratio(
    ratio: float, *, base: float = 0.5, per_doubling: float = 0.15, lo: float = 0.2, hi: float = 0.95
) -> float:
    """base at ratio==1 (just over threshold), rising by `per_doubling` per doubling of the margin."""
    if ratio <= 0:
        return lo
    return round(clamp(base + per_doubling * math.log2(ratio), lo, hi), 3)
