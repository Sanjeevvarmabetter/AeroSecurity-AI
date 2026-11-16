"""DET-004 Duplicate ICAO24 Identity. Reports an identity *conflict*; never concludes spoofing."""

import math
from collections.abc import Sequence

from app.aviation.geo import haversine_m
from app.detection.config import Det004Config
from app.detection.rules.base import AircraftRule, group_runs, latlon, obs_evidence
from app.detection.scoring import clamp, confidence_from_ratio
from app.detection.types import AircraftInfo, DataQuality, EvidenceItem, Finding, Obs, Severity

ALTERNATIVES = (
    "Receiver/aggregator clock skew between sources",
    "Position uncertainty larger than configured tolerance",
    "Data merged from different time bases",
    "Two aircraft or ground vehicles sharing one ICAO24 (misconfiguration, address reuse)",
    "Relay or multipath of one transmission",
    "Deliberate identity spoofing",
)


class DuplicateIdentity(AircraftRule):
    rule_id = "DET-004"
    name = "Duplicate ICAO24 Identity"
    version = "1.0.0"
    description = (
        "The same ICAO24 reported in mutually impossible locations at (nearly) the same time, either by "
        "different data sources or as alternating positions within a single source."
    )
    config_model = Det004Config
    cfg: Det004Config

    def _unreachable_m(self, dt: float) -> float:
        """Distance that cannot be covered in dt even with every tolerance in the aircraft's favour."""
        c = self.cfg
        return (
            c.plausible_speed_ms * (max(dt, 0.0) + c.timestamp_uncertainty_s) + 2 * c.position_uncertainty_m
        )

    @staticmethod
    def _reversals(pos: Sequence[Obs], chain: Sequence[int]) -> int:
        """Count consecutive impossible hops whose displacement vectors point in opposing directions."""

        def vec(i: int) -> tuple[float, float]:
            (la, lo), (lb, lb2) = latlon(pos[i]), latlon(pos[i + 1])
            return lb - la, (lb2 - lo) * math.cos(math.radians((la + lb) / 2))

        n = 0
        for i, j in zip(chain, chain[1:], strict=False):
            (x1, y1), (x2, y2) = vec(i), vec(j)
            if x1 * x2 + y1 * y2 < 0:
                n += 1
        return n

    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        return [*self._cross_source(aircraft, obs), *self._interleaved(aircraft, obs)]

    def _cross_source(self, ac: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        pos = [o for o in obs if o.has_position]
        conflicts: list[tuple[Obs, Obs, float, float]] = []
        for i, a in enumerate(pos):
            for b in pos[i + 1 :]:
                dt = b.ts - a.ts
                if dt > self.cfg.overlap_s:
                    break
                if a.source == b.source:
                    continue
                d = haversine_m(*latlon(a), *latlon(b))
                if d > self._unreachable_m(dt):
                    conflicts.append((a, b, d, dt))
        out = []
        for run in group_runs(conflicts, lambda x: x[0].ts, 60.0):
            a, b, d, dt = max(run, key=lambda x: x[2])
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="IDENTITY_CONFLICT",
                    severity=Severity.MEDIUM,
                    confidence=clamp(
                        confidence_from_ratio(d / self._unreachable_m(dt), base=0.45)
                        + (0.1 if len(run) >= 3 else 0),
                        0.2,
                        0.85,
                    ),
                    title=f"Same ICAO24 in two places: {a.source} vs {b.source}",
                    description=(
                        f"{a.source} and {b.source} report ICAO24 {ac.icao24} {d / 1000:.1f} km apart within "
                        f"{dt:.1f} s ({len(run)} conflicting pair(s)). This is an identity conflict, not proof of spoofing."
                    ),
                    event_start=run[0][0].t,
                    event_end=run[-1][1].t,
                    dedup_key=f"xsrc:{run[0][0].id}:{run[0][1].id}",
                    icao24=ac.icao24,
                    data_quality=DataQuality.PARTIAL,
                    sources=tuple(sorted({a.source, b.source})),
                    evidence=[
                        EvidenceItem("observation", obs_evidence(a, role="first_source"), a.id),
                        EvidenceItem("observation", obs_evidence(b, role="second_source"), b.id),
                        EvidenceItem(
                            "metric",
                            {
                                "distance_m": round(d, 1),
                                "dt_s": round(dt, 2),
                                "unreachable_beyond_m": round(self._unreachable_m(dt), 1),
                            },
                        ),
                    ],
                    summary={"check": "cross_source", "pairs": len(run), "max_distance_m": round(d, 1)},
                    alternatives=ALTERNATIVES,
                )
            )
        return out

    def _interleaved(self, ac: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        """Within ONE source: A -> B -> A ... in a short window, i.e. two tracks multiplexed into one stream.
        (Conflicts between different sources are reported by _cross_source, never twice.)"""
        out: list[Finding] = []
        for source in sorted({o.source for o in obs}):
            out.extend(
                self._interleaved_stream(ac, [o for o in obs if o.source == source and o.has_position])
            )
        return out

    def _interleaved_stream(self, ac: AircraftInfo, pos: Sequence[Obs]) -> list[Finding]:
        c = self.cfg
        jumps: list[int] = []  # index i where pos[i] -> pos[i+1] is an impossible hop
        for i in range(len(pos) - 1):
            a, b = pos[i], pos[i + 1]
            if haversine_m(*latlon(a), *latlon(b)) > self._unreachable_m(b.ts - a.ts):
                jumps.append(i)
        out, k = [], 0
        while k < len(jumps):
            j = k
            while j + 1 < len(jumps) and pos[jumps[j + 1]].ts - pos[jumps[k]].ts <= c.window_s:
                j += 1
            chain = jumps[k : j + 1]
            if len(chain) >= c.min_alternations:
                first, last = pos[chain[0]], pos[chain[-1] + 1]
                # Alternation signature: successive impossible hops reverse direction (A->B->A->B...).
                returns = self._reversals(pos, chain) >= c.min_alternations - 1
                if returns:
                    out.append(
                        Finding(
                            rule_id=self.rule_id,
                            detection_type="IDENTITY_CONFLICT",
                            severity=Severity.MEDIUM,
                            confidence=clamp(0.5 + 0.05 * (len(chain) - c.min_alternations), 0.5, 0.8),
                            title=f"Alternating positions for one ICAO24 ({len(chain)} jumps in {last.ts - first.ts:.0f} s)",
                            description=(
                                "The position stream alternates between locations that cannot both belong to one "
                                "aircraft. Consistent with two transmitters/streams sharing an address, or a "
                                "data-merge fault; not proof of spoofing."
                            ),
                            event_start=first.t,
                            event_end=last.t,
                            dedup_key=f"interleave:{pos[chain[0]].id}",
                            icao24=ac.icao24,
                            data_quality=DataQuality.PARTIAL,
                            sources=tuple(sorted({o.source for o in (first, last)})),
                            evidence=[
                                EvidenceItem("observation", obs_evidence(pos[i]), pos[i].id)
                                for i in chain[:6]
                            ]
                            + [
                                EvidenceItem(
                                    "metric", {"jumps": len(chain), "window_s": round(last.ts - first.ts, 1)}
                                )
                            ],
                            summary={"check": "interleaved", "jumps": len(chain)},
                            alternatives=ALTERNATIVES,
                        )
                    )
                k = j + 1
            else:
                k += 1
        return out
