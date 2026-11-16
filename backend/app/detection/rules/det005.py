"""DET-005 Emergency Squawk Monitoring (7500 / 7600 / 7700)."""

from collections.abc import Sequence

from app.detection.config import Det005Config
from app.detection.rules.base import AircraftRule, obs_evidence
from app.detection.scoring import clamp
from app.detection.types import AircraftInfo, DataQuality, EvidenceItem, Finding, Obs, Severity

CODES = {
    "7500": ("Unlawful interference", Severity.CRITICAL),
    "7600": ("Radio communication failure", Severity.MEDIUM),
    "7700": ("General emergency", Severity.HIGH),
}


class EmergencySquawk(AircraftRule):
    rule_id = "DET-005"
    name = "Emergency Squawk Monitoring"
    version = "1.0.0"
    description = (
        "Transponder code 7500, 7600 or 7700 observed, as an event with position, source and history."
    )
    config_model = Det005Config
    cfg: Det005Config

    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c, out = self.cfg, []
        for code, (meaning, severity) in CODES.items():
            hits = [o for o in obs if o.squawk == code]
            episodes: list[list[Obs]] = []
            for o in hits:
                # An episode continues while the code is re-observed within episode_gap_s.
                if episodes and o.ts - episodes[-1][-1].ts <= c.episode_gap_s:
                    episodes[-1].append(o)
                else:
                    episodes.append([o])
            for ep in episodes:
                n, first, last = len(ep), ep[0], ep[-1]
                last_pos = next((o for o in reversed(ep) if o.has_position), None)
                duration = last.ts - first.ts
                # Fewer than min_observations may be a code passing through 7700 while being dialled.
                transient = n < c.min_observations
                conf = clamp(
                    0.3 if transient else 0.55 + 0.1 * min(n, 5) / 5 + (0.15 if duration >= 30 else 0.0),
                    0.2,
                    0.95,
                )
                step = max(1, n // c.max_evidence_observations)
                sample = ep[::step][: c.max_evidence_observations]
                if last not in sample:
                    sample.append(last)
                out.append(
                    Finding(
                        rule_id=self.rule_id,
                        detection_type="EMERGENCY_SQUAWK",
                        severity=severity,
                        confidence=round(conf, 3),
                        title=f"Squawk {code} ({meaning})" + (" - single observation" if transient else ""),
                        description=(
                            f"Transponder code {code} ({meaning}) observed {n} time(s) over {duration:.0f} s. "
                            "A squawk code is what the crew (or equipment) selected; it does not establish the cause."
                        ),
                        event_start=first.t,
                        event_end=last.t,
                        dedup_key=f"{code}:{first.id}",
                        icao24=aircraft.icao24,
                        data_quality=DataQuality.GOOD if last_pos else DataQuality.PARTIAL,
                        sources=tuple(sorted({o.source for o in ep})),
                        evidence=[EvidenceItem("observation", obs_evidence(o), o.id) for o in sample]
                        + [
                            EvidenceItem(
                                "context",
                                {
                                    "squawk": code,
                                    "meaning": meaning,
                                    "observations": n,
                                    "duration_s": round(duration, 1),
                                    "first_seen": first.t.isoformat(),
                                    "last_seen": last.t.isoformat(),
                                    "callsign": next((o.callsign for o in ep if o.callsign), None),
                                    "last_known_position": (
                                        {
                                            "lat": last_pos.lat,
                                            "lon": last_pos.lon,
                                            "at": last_pos.t.isoformat(),
                                            "baro_altitude_m": last_pos.baro_altitude_m,
                                        }
                                        if last_pos
                                        else None
                                    ),
                                },
                            )
                        ],
                        summary={
                            "squawk": code,
                            "meaning": meaning,
                            "observations": n,
                            "duration_s": round(duration, 1),
                            "transient": transient,
                            "last_known_position": (
                                {"lat": last_pos.lat, "lon": last_pos.lon} if last_pos else None
                            ),
                        },
                        alternatives=(
                            "Genuine in-flight emergency",
                            "Crew training or test",
                            "Mis-selected code corrected shortly after",
                            "Transient value while the code was being dialled",
                            "Decoding error or spoofed transponder reply",
                        ),
                    )
                )
        return out
