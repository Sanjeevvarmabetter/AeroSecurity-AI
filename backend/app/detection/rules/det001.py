"""DET-001 Impossible Position Transition."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.aviation.geo import haversine_m
from app.detection.config import Det001Config
from app.detection.rules.base import AircraftRule, group_runs, latlon, obs_evidence
from app.detection.scoring import clamp, confidence_from_ratio
from app.detection.types import (
    SEVERITY_ORDER,
    AircraftInfo,
    DataQuality,
    EvidenceItem,
    Finding,
    Obs,
    Severity,
)

NON_ADSB_SOURCES = {1, 2, 3}  # OpenSky position_source: ASTERIX, MLAT, FLARM


@dataclass(frozen=True, slots=True)
class Transition:
    a: Obs
    b: Obs
    distance_m: float
    dt_s: float
    required_speed_lb_ms: float  # smallest speed consistent with the displacement, after tolerances
    severity: Severity
    confidence: float
    penalties: tuple[str, ...]
    limit_ms: float
    reported_max_ms: float | None


class ImpossiblePositionTransition(AircraftRule):
    rule_id = "DET-001"
    name = "Impossible Position Transition"
    version = "1.0.0"
    description = (
        "Consecutive positions whose displacement cannot be covered in the elapsed time at any plausible "
        "aircraft speed, after allowing for position and timestamp uncertainty."
    )
    config_model = Det001Config
    cfg: Det001Config

    def _evaluate(self, a: Obs, b: Obs) -> Transition | None:
        c = self.cfg
        d = haversine_m(*latlon(a), *latlon(b))
        dt = b.ts - a.ts
        # Conservative lower bound: smallest distance / largest elapsed time consistent with the tolerances.
        # (Real data shows ~1 s timestamp jitter, which would otherwise create false 1,000+ m/s speeds.)
        v_lb = max(0.0, d - 2 * c.position_uncertainty_m) / (max(dt, 0.0) + c.timestamp_uncertainty_s)
        reported = [v for v in (a.velocity_ms, b.velocity_ms) if v is not None]
        rmax = max(reported) if reported else None

        if v_lb > c.hard_speed_ceiling_ms:
            sev, limit = Severity.HIGH, c.hard_speed_ceiling_ms
        elif v_lb > c.civil_speed_ceiling_ms and (rmax is None or v_lb > c.reported_speed_factor * rmax):
            sev, limit = Severity.MEDIUM, c.civil_speed_ceiling_ms
        else:
            return None

        penalties: list[str] = []
        conf = confidence_from_ratio(v_lb / limit)
        if {a.position_source, b.position_source} & NON_ADSB_SOURCES:
            penalties.append("non_adsb_position_source")
            conf -= 0.15
        if dt > c.gap_s:
            penalties.append("observation_gap")
            conf -= 0.10
        if rmax is None:
            penalties.append("no_reported_velocity")
            conf -= 0.05
        return Transition(
            a, b, d, dt, v_lb, sev, round(clamp(conf, 0.2, 0.95), 3), tuple(penalties), limit, rmax
        )

    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        pos = [o for o in obs if o.has_position]
        found = [t for a, b in zip(pos, pos[1:], strict=False) if (t := self._evaluate(a, b))]
        findings: list[Finding] = []
        for run in group_runs(found, lambda t: t.a.ts, self.cfg.episode_join_s):
            sev = max((t.severity for t in run), key=SEVERITY_ORDER.__getitem__)
            conf = max(t.confidence for t in run)
            worst = max(run, key=lambda t: t.required_speed_lb_ms)
            penalties = sorted({p for t in run for p in t.penalties})
            ev: list[EvidenceItem] = []
            for t in run[: self.cfg.max_evidence_transitions]:
                ev.append(EvidenceItem("observation", obs_evidence(t.a, role="from"), t.a.id))
                ev.append(EvidenceItem("observation", obs_evidence(t.b, role="to"), t.b.id))
                ev.append(
                    EvidenceItem(
                        "metric",
                        {
                            "distance_m": round(t.distance_m, 1),
                            "dt_s": round(t.dt_s, 3),
                            "naive_speed_ms": round(t.distance_m / t.dt_s, 1) if t.dt_s > 0 else None,
                            "required_speed_lower_bound_ms": round(t.required_speed_lb_ms, 1),
                            "threshold_ms": t.limit_ms,
                            "reported_speed_max_ms": t.reported_max_ms,
                            "tolerances": {
                                "timestamp_s": self.cfg.timestamp_uncertainty_s,
                                "position_m_per_fix": self.cfg.position_uncertainty_m,
                            },
                        },
                    )
                )
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="POSITION_ANOMALY",
                    severity=sev,
                    confidence=conf,
                    title=f"Impossible position transition ({len(run)} jump{'s' if len(run) > 1 else ''})",
                    description=(
                        f"Position changed by {worst.distance_m / 1000:.1f} km in {worst.dt_s:.1f} s, requiring at "
                        f"least {worst.required_speed_lb_ms:.0f} m/s even after tolerances, above the "
                        f"{worst.limit_ms:.0f} m/s limit. This is a data pattern, not a determination of cause."
                    ),
                    event_start=run[0].a.t,
                    event_end=run[-1].b.t,
                    dedup_key=f"{run[0].a.id}:{run[0].b.id}",
                    data_quality=DataQuality.PARTIAL if penalties else DataQuality.GOOD,
                    icao24=aircraft.icao24,
                    evidence=ev,
                    sources=tuple(sorted({t.a.source for t in run} | {t.b.source for t in run})),
                    summary={
                        "jumps": len(run),
                        "max_required_speed_lb_ms": round(worst.required_speed_lb_ms, 1),
                        "penalties": penalties,
                        "evidence_truncated": len(run) > self.cfg.max_evidence_transitions,
                    },
                    alternatives=(
                        "Receiver or aggregator timestamp error",
                        "Single corrupted/decoded-in-error position message",
                        "Multilateration artefact",
                        "Two transponders sharing one ICAO24 address",
                        "Deliberate position falsification (ADS-B spoofing)",
                    ),
                )
            )
        return findings


__all__ = ["ImpossiblePositionTransition", "Transition"]
