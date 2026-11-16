"""DET-007 Unusual Trajectory: robust statistics against the aircraft's OWN stored history (no ML).

Two signals: (a) sustained turn rate far above both an absolute floor and the aircraft's own baseline, and
(b) repeated rotation over a small area (orbit/loiter). Holding patterns and training flights are legitimate
and produce the same shapes; findings are low severity and always list those alternatives.
"""

import statistics
from collections.abc import Sequence

from app.aviation.geo import haversine_m
from app.detection.config import Det007Config
from app.detection.rules.base import AircraftRule, group_runs, obs_evidence
from app.detection.scoring import clamp
from app.detection.types import AircraftInfo, DataQuality, EvidenceItem, Finding, Obs, Severity

ALTS = (
    "Holding pattern, go-around or approach procedure",
    "Training or survey/orbit flight",
    "Weather avoidance",
    "Noisy heading data",
    "Unusual behaviour that merits a human look",
)


def _wrap(delta: float) -> float:
    return (delta + 180.0) % 360.0 - 180.0


class UnusualTrajectory(AircraftRule):
    rule_id = "DET-007"
    name = "Unusual Trajectory"
    version = "1.0.0"
    description = (
        "Turn-rate and orbit patterns that are extreme relative to the aircraft's own recorded behaviour."
    )
    config_model = Det007Config
    cfg: Det007Config

    def _samples(self, obs: Sequence[Obs]) -> list[Obs]:
        c, out, last = self.cfg, [], -1e18
        for o in obs:
            if (
                o.has_position
                and o.heading_deg is not None
                and o.on_ground is not True
                and (o.velocity_ms or 0.0) >= c.min_speed_ms
                and o.ts - last >= c.sample_s
            ):
                out.append(o)
                last = o.ts
        return out

    @staticmethod
    def _unwrap(samples: Sequence[Obs]) -> list[float]:
        u, prev = [], None
        for o in samples:
            h = o.heading_deg or 0.0
            u.append(h if prev is None else u[-1] + _wrap(h - prev))
            prev = h
        return u

    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c = self.cfg
        positioned = [o for o in obs if o.has_position]
        if (
            len(positioned) < c.min_baseline_positions
            or positioned[-1].ts - positioned[0].ts < c.min_baseline_duration_s
        ):
            return []  # not enough history to define "normal" for this aircraft
        s = self._samples(obs)
        if len(s) < 10:
            return []
        u = self._unwrap(s)
        return [*self._turn_rate(aircraft, s, u), *self._orbits(aircraft, s, u)]

    def _turn_rate(self, ac: AircraftInfo, s: Sequence[Obs], u: Sequence[float]) -> list[Finding]:
        c = self.cfg
        rates: list[tuple[int, float]] = []  # (index, signed deg/s over the trailing window)
        j = 0
        for i in range(len(s)):
            while s[i].ts - s[j].ts > c.window_s:
                j += 1
            span = s[i].ts - s[j].ts
            contiguous = all(s[k + 1].ts - s[k].ts <= 3 * c.sample_s for k in range(j, i))
            if span >= 0.6 * c.window_s and contiguous:
                rates.append((i, (u[i] - u[j]) / span))
        if len(rates) < 20:
            return []
        mags = [abs(r) for _, r in rates]
        med = statistics.median(mags)
        mad = statistics.median(abs(m - med) for m in mags)
        sigma = max(
            1.4826 * mad, 0.5
        )  # floor: heading is quantised/noisy, avoids infinite z on perfectly straight flights
        hits = [
            (i, r, (abs(r) - med) / sigma)
            for i, r in rates
            if abs(r) > c.min_turn_rate_dps and (abs(r) - med) / sigma > c.robust_z_threshold
        ]
        out = []
        for run in group_runs(hits, lambda x: s[x[0]].ts, c.run_join_s):
            i, r, z = max(run, key=lambda x: abs(x[1]))
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="TRAJECTORY_ANOMALY",
                    severity=Severity.LOW,
                    confidence=round(clamp(0.3 + 0.02 * (z - c.robust_z_threshold), 0.3, 0.6), 3),
                    title=f"Sustained turn rate {abs(r):.1f} deg/s",
                    description=(
                        f"Average turn rate {abs(r):.1f} deg/s over {c.window_s:.0f} s, versus a baseline median of "
                        f"{med:.2f} deg/s for this aircraft (robust z={z:.1f})."
                    ),
                    event_start=s[run[0][0]].t,
                    event_end=s[run[-1][0]].t,
                    dedup_key=f"turn:{s[run[0][0]].id}",
                    data_quality=DataQuality.GOOD,
                    icao24=ac.icao24,
                    sources=tuple(sorted({s[i].source for i, _, _ in run})),
                    evidence=[
                        EvidenceItem("observation", obs_evidence(s[i]), s[i].id)
                        for i in (run[0][0], i, run[-1][0])
                    ]
                    + [
                        EvidenceItem(
                            "metric",
                            {
                                "peak_turn_rate_dps": round(r, 2),
                                "baseline_median_dps": round(med, 3),
                                "baseline_mad_dps": round(mad, 3),
                                "robust_z": round(z, 1),
                                "baseline_windows": len(rates),
                                "window_s": c.window_s,
                            },
                        )
                    ],
                    summary={"check": "turn_rate", "peak_dps": round(abs(r), 2), "robust_z": round(z, 1)},
                    alternatives=ALTS,
                )
            )
        return out

    def _orbits(self, ac: AircraftInfo, s: Sequence[Obs], u: Sequence[float]) -> list[Finding]:
        c, out, i = self.cfg, [], 0
        while i < len(s):
            found = None
            k = i + 1
            while k < len(s) and s[k].ts - s[i].ts <= c.orbit_window_s:
                if s[k].ts - s[k - 1].ts > 60.0:
                    break  # unobserved gap inside the window: do not stitch across it
                if abs(u[k] - u[i]) >= c.orbit_min_rotation_deg:
                    seg = s[i : k + 1]
                    clat = sum(o.lat or 0.0 for o in seg) / len(seg)
                    clon = sum(o.lon or 0.0 for o in seg) / len(seg)
                    radius = max(haversine_m(clat, clon, o.lat or 0.0, o.lon or 0.0) for o in seg)
                    if radius <= c.orbit_max_radius_m:
                        found = (k, radius, u[k] - u[i])
                        break
                k += 1
            if found:
                k, radius, rot = found
                seg = s[i : k + 1]
                out.append(
                    Finding(
                        rule_id=self.rule_id,
                        detection_type="TRAJECTORY_ANOMALY",
                        severity=Severity.LOW,
                        confidence=0.5,
                        title=f"Orbit/loiter pattern ({abs(rot):.0f} deg of rotation)",
                        description=(
                            f"Heading rotated {abs(rot):.0f} deg in {seg[-1].ts - seg[0].ts:.0f} s within "
                            f"{radius / 1000:.1f} km of one point."
                        ),
                        event_start=seg[0].t,
                        event_end=seg[-1].t,
                        dedup_key=f"orbit:{seg[0].id}",
                        icao24=ac.icao24,
                        sources=tuple(sorted({o.source for o in seg})),
                        evidence=[
                            EvidenceItem("observation", obs_evidence(o), o.id)
                            for o in (seg[0], seg[len(seg) // 2], seg[-1])
                        ]
                        + [
                            EvidenceItem(
                                "metric",
                                {
                                    "rotation_deg": round(rot, 1),
                                    "radius_m": round(radius, 1),
                                    "duration_s": round(seg[-1].ts - seg[0].ts, 1),
                                },
                            )
                        ],
                        summary={
                            "check": "orbit",
                            "rotation_deg": round(rot, 1),
                            "radius_m": round(radius, 1),
                        },
                        alternatives=ALTS,
                    )
                )
                i = k + 1
            else:
                i += 1
        return out
