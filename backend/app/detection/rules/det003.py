"""DET-003 Altitude Anomaly. Barometric and geometric altitude are different quantities and are compared
only against explicit tolerances; neither is treated as ground truth."""

from collections.abc import Sequence

from app.detection.config import Det003Config
from app.detection.rules.base import AircraftRule, group_runs, obs_evidence
from app.detection.scoring import clamp, confidence_from_ratio
from app.detection.types import AircraftInfo, DataQuality, EvidenceItem, Finding, Obs, Severity


class AltitudeAnomaly(AircraftRule):
    rule_id = "DET-003"
    name = "Altitude Anomaly"
    version = "1.0.0"
    description = (
        "Altitude changes no aircraft can perform, reported vertical rates unsupported by the altitude "
        "series, barometric/geometric divergence, and contradictory or missing altitude data."
    )
    config_model = Det003Config
    cfg: Det003Config

    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        return [
            *self._impossible_change(aircraft, obs),
            *self._vrate_mismatch(aircraft, obs),
            *self._divergence(aircraft, obs),
            *self._on_ground_contradiction(aircraft, obs),
            *self._missing_altitude(aircraft, obs),
        ]

    # -- a) altitude change faster than any aircraft can climb/descend ---------------------------------
    def _impossible_change(self, ac: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c, hits = self.cfg, []
        for a, b in zip(obs, obs[1:], strict=False):
            if a.baro_altitude_m is None or b.baro_altitude_m is None:
                continue
            dh = abs(b.baro_altitude_m - a.baro_altitude_m)
            rate_lb = max(0.0, dh - 2 * c.altitude_resolution_m) / (
                max(b.ts - a.ts, 0.0) + c.timestamp_uncertainty_s
            )
            if rate_lb > c.max_vertical_rate_ms:
                hits.append((a, b, rate_lb))
        out = []
        for run in group_runs(hits, lambda x: x[0].ts, c.run_join_s):
            a, b, r = max(run, key=lambda x: x[2])
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="ALTITUDE_ANOMALY",
                    severity=Severity.HIGH,
                    confidence=confidence_from_ratio(r / c.max_vertical_rate_ms),
                    title=f"Implausible altitude change ({r:.0f} m/s)",
                    description=(
                        f"Barometric altitude changed {a.baro_altitude_m:.0f} -> {b.baro_altitude_m:.0f} m in "
                        f"{b.ts - a.ts:.1f} s: at least {r:.0f} m/s, above the {c.max_vertical_rate_ms:.0f} m/s limit."
                    ),
                    event_start=run[0][0].t,
                    event_end=run[-1][1].t,
                    dedup_key=f"jump:{run[0][0].id}",
                    icao24=ac.icao24,
                    sources=(a.source,),
                    evidence=[
                        EvidenceItem("observation", obs_evidence(a, role="from"), a.id),
                        EvidenceItem("observation", obs_evidence(b, role="to"), b.id),
                        EvidenceItem(
                            "metric",
                            {"derived_vertical_rate_lb_ms": round(r, 1), "limit_ms": c.max_vertical_rate_ms},
                        ),
                    ],
                    summary={"check": "impossible_change", "events": len(run)},
                    alternatives=(
                        "Altimeter/pressure-setting change",
                        "A genuine extreme flight condition (e.g. loss of control, steep dive or climb) that the limit does not model",
                        "Decoding error in the altitude field",
                        "Mixed reports from two sources",
                    ),
                )
            )
        return out

    # -- b) reported vertical rate unsupported by the altitude series ---------------------------------
    def _vrate_mismatch(self, ac: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c, hits = self.cfg, []
        for a, b in zip(obs, obs[1:], strict=False):
            dt = b.ts - a.ts
            if not (c.vrate_window_min_s <= dt <= c.vrate_window_max_s):
                continue
            if (
                a.baro_altitude_m is None
                or b.baro_altitude_m is None
                or a.vertical_rate_ms is None
                or b.vertical_rate_ms is None
            ):
                continue
            reported = max(abs(a.vertical_rate_ms), abs(b.vertical_rate_ms))
            # Largest rate the altitude series could support, with every tolerance in the aircraft's favour.
            supported = (abs(b.baro_altitude_m - a.baro_altitude_m) + 2 * c.altitude_resolution_m) / max(
                dt - c.timestamp_uncertainty_s, 1.0
            )
            if reported > c.inconsistent_reported_vrate_ms and reported > 2 * supported:
                hits.append((a, b, reported, supported))
        out = []
        for run in group_runs(hits, lambda x: x[0].ts, c.run_join_s):
            a, b, rep, sup = max(run, key=lambda x: x[2] / max(x[3], 1e-6))
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="ALTITUDE_ANOMALY",
                    severity=Severity.MEDIUM,
                    confidence=confidence_from_ratio(rep / max(2 * sup, 1e-6), base=0.45, hi=0.75),
                    title=f"Reported vertical rate {rep:.0f} m/s unsupported by altitude series",
                    description=(
                        f"Reported vertical rate up to {rep:.1f} m/s, but barometric altitude over {b.ts - a.ts:.0f} s "
                        f"supports at most {sup:.1f} m/s."
                    ),
                    event_start=run[0][0].t,
                    event_end=run[-1][1].t,
                    dedup_key=f"vrate:{run[0][0].id}",
                    icao24=ac.icao24,
                    sources=(a.source,),
                    data_quality=DataQuality.PARTIAL,
                    evidence=[
                        EvidenceItem("observation", obs_evidence(a, role="from"), a.id),
                        EvidenceItem("observation", obs_evidence(b, role="to"), b.id),
                        EvidenceItem(
                            "metric",
                            {"reported_vrate_ms": round(rep, 1), "altitude_supported_ms": round(sup, 1)},
                        ),
                    ],
                    summary={"check": "vertical_rate_mismatch", "windows": len(run)},
                    alternatives=(
                        "A genuine extreme maneuver (the altitude series may be undersampled during it)",
                        "The broadcast vertical-rate field is known to be noisy or sourced from a different "
                        "sensor (barometric vs inertial)",
                        "Decoding error",
                        "Timestamp misalignment",
                    ),
                )
            )
        return out

    # -- c) barometric vs geometric divergence --------------------------------------------------------
    def _divergence(self, ac: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c = self.cfg
        hits = [
            o
            for o in obs
            if o.baro_altitude_m is not None
            and o.geo_altitude_m is not None
            and abs(o.geo_altitude_m - o.baro_altitude_m) > c.baro_geo_divergence_m
        ]
        out = []
        for run in group_runs(hits, lambda o: o.ts, c.run_join_s):
            worst = max(run, key=lambda o: abs((o.geo_altitude_m or 0) - (o.baro_altitude_m or 0)))
            div = (worst.geo_altitude_m or 0) - (worst.baro_altitude_m or 0)
            high = abs(div) > c.baro_geo_divergence_high_m
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="ALTITUDE_ANOMALY",
                    severity=Severity.HIGH if high else Severity.MEDIUM,
                    confidence=clamp(
                        confidence_from_ratio(abs(div) / c.baro_geo_divergence_m, base=0.4, hi=0.8)
                        + (0.1 if len(run) >= 5 else 0),
                        0.2,
                        0.8,
                    ),
                    title=f"Barometric/geometric altitude divergence {div:+.0f} m",
                    description=(
                        f"{len(run)} observation(s) where geometric and barometric altitude differ by more than "
                        f"{c.baro_geo_divergence_m:.0f} m (worst {div:+.0f} m). Pressure variation and geoid "
                        "height normally explain up to roughly 1 km."
                    ),
                    event_start=run[0].t,
                    event_end=run[-1].t,
                    dedup_key=f"diverge:{run[0].id}",
                    icao24=ac.icao24,
                    sources=tuple(sorted({o.source for o in run})),
                    evidence=[
                        EvidenceItem(
                            "observation",
                            obs_evidence(
                                o,
                                geo_minus_baro_m=round((o.geo_altitude_m or 0) - (o.baro_altitude_m or 0), 1),
                            ),
                            o.id,
                        )
                        for o in (run[:3] + ([worst] if worst not in run[:3] else []))
                    ]
                    + [
                        EvidenceItem(
                            "metric", {"observations": len(run), "worst_divergence_m": round(div, 1)}
                        )
                    ],
                    summary={
                        "check": "baro_geo_divergence",
                        "observations": len(run),
                        "worst_m": round(div, 1),
                    },
                    alternatives=(
                        "Unusual atmospheric pressure vs the standard 1013.25 hPa",
                        "Altimeter or GNSS fault/glitch",
                        "Decoding error",
                        "Deliberate falsification of one altitude field",
                    ),
                )
            )
        return out

    # -- d) contradictions ---------------------------------------------------------------------------
    def _on_ground_contradiction(self, ac: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c = self.cfg
        hits = [
            o
            for o in obs
            if o.on_ground
            and o.baro_altitude_m is not None
            and o.baro_altitude_m > c.on_ground_max_altitude_m
        ]
        return [
            Finding(
                rule_id=self.rule_id,
                detection_type="ALTITUDE_ANOMALY",
                severity=Severity.MEDIUM,
                confidence=0.7,
                title="On-ground flag contradicts altitude",
                description=(
                    f"{len(run)} observation(s) flagged on-ground while barometric altitude exceeds "
                    f"{c.on_ground_max_altitude_m:.0f} m."
                ),
                event_start=run[0].t,
                event_end=run[-1].t,
                dedup_key=f"ground:{run[0].id}",
                icao24=ac.icao24,
                sources=tuple(sorted({o.source for o in run})),
                data_quality=DataQuality.PARTIAL,
                evidence=[EvidenceItem("observation", obs_evidence(o), o.id) for o in run[:5]],
                summary={"check": "on_ground_contradiction", "observations": len(run)},
                alternatives=("Decoding error in the surface/airborne flag", "Stale flag"),
            )
            for run in group_runs(hits, lambda o: o.ts, c.run_join_s)
        ]

    def _missing_altitude(self, ac: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c = self.cfg
        hits = [
            o
            for o in obs
            if o.has_position
            and o.on_ground is False
            and o.baro_altitude_m is None
            and o.geo_altitude_m is None
        ]
        return [
            Finding(
                rule_id=self.rule_id,
                detection_type="ALTITUDE_ANOMALY",
                severity=Severity.LOW,
                confidence=0.8,
                title="Airborne positions without any altitude",
                description=f"{len(run)} consecutive airborne observations carry a position but no altitude value.",
                event_start=run[0].t,
                event_end=run[-1].t,
                dedup_key=f"noalt:{run[0].id}",
                icao24=ac.icao24,
                sources=tuple(sorted({o.source for o in run})),
                data_quality=DataQuality.DEGRADED,
                evidence=[EvidenceItem("observation", obs_evidence(o), o.id) for o in run[:5]],
                summary={"check": "missing_altitude", "observations": len(run)},
                alternatives=("Receiver did not decode the altitude message", "Provider omits the field"),
            )
            for run in group_runs(hits, lambda o: o.ts, c.run_join_s)
            if len(run) >= c.missing_altitude_min_run
        ]
