"""DET-008 Abnormal Airport Traffic. Traffic-volume statistics only; never an incident claim.

Counts depend on receiver coverage, so only *increases* against the airport's own hourly baseline are reported.
A drop cannot be told apart from a receiver outage and is deliberately not flagged.
"""

import statistics
from datetime import timedelta

from app.detection.config import Det008Config
from app.detection.rules.base import AirportRule, group_runs
from app.detection.scoring import clamp
from app.detection.types import AirportTraffic, DataQuality, EvidenceItem, Finding, Severity


class AbnormalAirportTraffic(AirportRule):
    rule_id = "DET-008"
    name = "Abnormal Airport Traffic"
    version = "1.0.0"
    description = (
        "Hourly distinct-aircraft counts near an airport far above that airport's own observed baseline."
    )
    config_model = Det008Config
    cfg: Det008Config

    def detect(self, traffic: AirportTraffic) -> list[Finding]:
        c = self.cfg
        if len(traffic.hourly) < c.min_baseline_hours:
            return []
        counts = list(traffic.hourly.values())
        med = statistics.median(counts)
        mad = statistics.median(abs(x - med) for x in counts)
        sigma = max(1.4826 * mad, 1.0)
        hits = [
            (h, n, (n - med) / sigma)
            for h, n in sorted(traffic.hourly.items())
            if n >= c.min_count
            and n >= c.min_ratio_to_median * max(med, 1.0)
            and (n - med) / sigma > c.robust_z_threshold
        ]
        out = []
        for run in group_runs(hits, lambda x: x[0].timestamp(), 3600.0):
            h, n, z = max(run, key=lambda x: x[2])
            out.append(
                Finding(
                    rule_id=self.rule_id,
                    detection_type="AIRPORT_TRAFFIC",
                    severity=Severity.LOW,
                    confidence=round(clamp(0.25 + 0.02 * (z - c.robust_z_threshold), 0.25, 0.5), 3),
                    title=f"Traffic near {traffic.ident} {n} aircraft/h vs baseline {med:.0f}",
                    description=(
                        f"{n} distinct aircraft observed within {c.radius_m / 1000:.0f} km of {traffic.name} in one hour, "
                        f"versus a baseline median of {med:.0f} (robust z={z:.1f}). Traffic volume alone does not "
                        "indicate a security incident."
                    ),
                    event_start=run[0][0],
                    event_end=run[-1][0] + timedelta(hours=1),
                    dedup_key=f"{traffic.ident}:{run[0][0].isoformat()}",
                    data_quality=DataQuality.PARTIAL,
                    airport_ident=traffic.ident,
                    evidence=[
                        EvidenceItem(
                            "metric", {"hour": hh.isoformat(), "aircraft": nn, "robust_z": round(zz, 1)}
                        )
                        for hh, nn, zz in run
                    ]
                    + [
                        EvidenceItem(
                            "context",
                            {
                                "baseline_median": med,
                                "baseline_mad": mad,
                                "baseline_hours": len(counts),
                                "radius_m": c.radius_m,
                            },
                        )
                    ],
                    summary={
                        "peak_aircraft": n,
                        "baseline_median": med,
                        "robust_z": round(z, 1),
                        "hours": len(run),
                    },
                    alternatives=(
                        "Scheduled bank/peak or seasonal event",
                        "Receiver coverage change near the airport",
                        "Diversions from weather elsewhere",
                        "Special event or exercise",
                        "Small baseline sample",
                    ),
                )
            )
        return out
