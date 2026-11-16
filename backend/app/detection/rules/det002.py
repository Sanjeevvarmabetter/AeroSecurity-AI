"""DET-002 Physically Implausible Velocity."""

from collections.abc import Sequence

from app.detection.config import Det002Config
from app.detection.rules.base import AircraftRule, group_runs, obs_evidence
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


class ImplausibleVelocity(AircraftRule):
    rule_id = "DET-002"
    name = "Physically Implausible Velocity"
    version = "1.0.0"
    description = (
        "Reported ground speed above a configurable, aircraft-type-aware ceiling, or an acceleration "
        "between consecutive reports that no aircraft can produce."
    )
    config_model = Det002Config
    cfg: Det002Config

    def limit_for(self, aircraft: AircraftInfo) -> tuple[float, str]:
        t = (aircraft.aircraft_type or "").upper()
        if t in self.cfg.type_limits_ms:
            return self.cfg.type_limits_ms[t], f"type_override:{t}"
        return self.cfg.default_max_speed_ms, "default"

    @staticmethod
    def _severity(ratio: float) -> Severity:
        return Severity.HIGH if ratio > 2.0 else Severity.MEDIUM if ratio > 1.3 else Severity.LOW

    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        limit, limit_src = self.limit_for(aircraft)
        c = self.cfg
        out: list[Finding] = []
        quality = (
            DataQuality.GOOD if aircraft.aircraft_type else DataQuality.PARTIAL
        )  # type unknown => default limit

        over = [o for o in obs if o.velocity_ms is not None and o.velocity_ms > limit]
        for run in group_runs(over, lambda o: o.ts, c.run_join_s):
            peak = max(run, key=lambda o: o.velocity_ms or 0.0)
            ratio = (peak.velocity_ms or 0.0) / limit
            conf = confidence_from_ratio(ratio) + (0.1 if len(run) >= 3 else 0.0)
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="VELOCITY_ANOMALY",
                    severity=self._severity(ratio),
                    confidence=round(clamp(conf, 0.2, 0.95), 3),
                    title=f"Reported speed {peak.velocity_ms:.0f} m/s exceeds {limit:.0f} m/s limit",
                    description=(
                        f"{len(run)} observation(s) report ground speed above the {limit:.0f} m/s ceiling "
                        f"({limit_src}); peak {peak.velocity_ms:.1f} m/s."
                    ),
                    event_start=run[0].t,
                    event_end=run[-1].t,
                    dedup_key=f"speed:{run[0].id}",
                    data_quality=quality,
                    icao24=aircraft.icao24,
                    sources=tuple(sorted({o.source for o in run})),
                    evidence=[
                        EvidenceItem("observation", obs_evidence(o), o.id)
                        for o in (run[:3] + ([peak] if peak not in run[:3] else []))
                    ]
                    + [
                        EvidenceItem(
                            "metric",
                            {
                                "limit_ms": limit,
                                "limit_source": limit_src,
                                "peak_ms": peak.velocity_ms,
                                "observations_over_limit": len(run),
                            },
                        )
                    ],
                    summary={
                        "limit_ms": limit,
                        "limit_source": limit_src,
                        "peak_ms": peak.velocity_ms,
                        "observations": len(run),
                    },
                    alternatives=(
                        "Strong tailwind/jet stream on a type with no configured limit",
                        "A genuine extreme flight condition (e.g. loss of control, steep dive or climb) that the limit does not model",
                        "Decoding error in the velocity field",
                        "Wrong aircraft-type limit (type table is incomplete)",
                    ),
                )
            )

        accel: list[tuple[Obs, Obs, float]] = []
        for a, b in zip(obs, obs[1:], strict=False):
            if a.velocity_ms is None or b.velocity_ms is None:
                continue
            dt = b.ts - a.ts
            if dt > c.accel_max_dt_s:
                continue
            a_lb = abs(b.velocity_ms - a.velocity_ms) / (max(dt, 0.0) + c.timestamp_uncertainty_s)
            if a_lb > c.max_acceleration_ms2:
                accel.append((a, b, a_lb))
        for arun in group_runs(accel, lambda x: x[0].ts, c.run_join_s):
            a, b, a_lb = max(arun, key=lambda x: x[2])
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="VELOCITY_ANOMALY",
                    severity=Severity.MEDIUM,
                    confidence=confidence_from_ratio(a_lb / c.max_acceleration_ms2),
                    title=f"Implausible acceleration ({a_lb:.0f} m/s²)",
                    description=(
                        f"Reported speed changed {a.velocity_ms:.0f} -> {b.velocity_ms:.0f} m/s in "
                        f"{b.ts - a.ts:.1f} s (at least {a_lb:.0f} m/s² after timestamp tolerance)."
                    ),
                    event_start=arun[0][0].t,
                    event_end=arun[-1][1].t,
                    dedup_key=f"accel:{arun[0][0].id}",
                    data_quality=quality,
                    icao24=aircraft.icao24,
                    sources=(a.source,),
                    evidence=[
                        EvidenceItem("observation", obs_evidence(a, role="from"), a.id),
                        EvidenceItem("observation", obs_evidence(b, role="to"), b.id),
                        EvidenceItem(
                            "metric",
                            {"acceleration_lb_ms2": round(a_lb, 1), "limit_ms2": c.max_acceleration_ms2},
                        ),
                    ],
                    summary={"acceleration_lb_ms2": round(a_lb, 1), "events": len(arun)},
                    alternatives=(
                        "Decoding error in the velocity field",
                        "Receiver timestamp error",
                        "Mixed reports from two sources",
                    ),
                )
            )
        out.sort(key=lambda f: SEVERITY_ORDER[f.severity], reverse=True)
        return out
