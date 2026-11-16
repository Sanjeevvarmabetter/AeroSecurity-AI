"""DET-006 Data Integrity Anomalies. Findings are about the DATA, flagged DEGRADED, and say nothing about intent."""

from collections.abc import Sequence

from app.detection.config import Det006Config
from app.detection.rules.base import AircraftRule, group_runs, obs_evidence
from app.detection.types import AircraftInfo, DataQuality, EvidenceItem, Finding, Obs, Severity


class DataIntegrity(AircraftRule):
    rule_id = "DET-006"
    name = "Data Integrity Anomalies"
    version = "1.0.0"
    description = (
        "Missing or invalid coordinates, invalid field values flagged at ingestion, inconsistent timestamps, "
        "and duplicate records across sources."
    )
    config_model = Det006Config
    cfg: Det006Config

    def detect(self, aircraft: AircraftInfo, obs: Sequence[Obs]) -> list[Finding]:
        c, out = self.cfg, []

        def make(
            kind: str, run: list[Obs], title: str, desc: str, sev: Severity, alts: tuple[str, ...]
        ) -> Finding:
            return Finding(
                rule_id=self.rule_id,
                detection_type="DATA_INTEGRITY",
                severity=sev,
                confidence=0.9,
                title=title,
                description=desc,
                event_start=run[0].t,
                event_end=run[-1].t,
                dedup_key=f"{kind}:{run[0].id}",
                data_quality=DataQuality.DEGRADED,
                icao24=aircraft.icao24,
                sources=tuple(sorted({o.source for o in run})),
                evidence=[
                    EvidenceItem("observation", obs_evidence(o, issues=list(o.issues)), o.id) for o in run[:5]
                ]
                + [EvidenceItem("metric", {"check": kind, "observations": len(run)})],
                summary={"check": kind, "observations": len(run)},
                alternatives=alts,
            )

        # Observations lacking a position (start of coverage, receiver loss, decoding gaps).
        for run in group_runs([o for o in obs if not o.has_position], lambda o: o.ts, c.run_join_s):
            out.append(
                make(
                    "missing_coordinates",
                    run,
                    f"{len(run)} observation(s) without a position",
                    "State vectors were recorded with no usable coordinates.",
                    Severity.LOW,
                    (
                        "Aircraft not yet/no longer transmitting position",
                        "Receiver decoding loss",
                        "Provider omitted the field",
                    ),
                )
            )

        # Field-level problems recorded when the data was ingested (excluding the missing-coordinates case above).
        kinds = sorted({i for o in obs for i in o.issues if i != "missing_coordinates"})
        for kind in kinds:
            for run in group_runs([o for o in obs if kind in o.issues], lambda o: o.ts, c.run_join_s):
                out.append(
                    make(
                        kind,
                        run,
                        f"Invalid data at ingestion: {kind}",
                        f"{len(run)} observation(s) carried a value rejected by ingestion validation ({kind}); "
                        "the original value is preserved in the stored observation.",
                        Severity.LOW,
                        ("Decoding error", "Provider formatting change"),
                    )
                )

        # last_contact earlier than the position time it should postdate; observation time in the future.
        bad_ts = [
            o
            for o in obs
            if o.last_contact is not None and o.ts - o.last_contact.timestamp() > c.last_contact_tolerance_s
        ]
        for run in group_runs(bad_ts, lambda o: o.ts, c.run_join_s):
            out.append(
                make(
                    "last_contact_before_position",
                    run,
                    "Last-contact time precedes position time",
                    f"{len(run)} observation(s) whose last-contact timestamp is earlier than the position "
                    "timestamp, which a provider should never produce.",
                    Severity.LOW,
                    ("Receiver clock skew", "Aggregation/merge ordering fault"),
                )
            )
        future = [
            o
            for o in obs
            if o.ingested_at is not None and o.ts - o.ingested_at.timestamp() > c.future_tolerance_s
        ]
        for run in group_runs(future, lambda o: o.ts, c.run_join_s):
            out.append(
                make(
                    "timestamp_in_future",
                    run,
                    "Observation timestamp in the future",
                    f"{len(run)} observation(s) are timestamped later than the moment they were ingested.",
                    Severity.MEDIUM,
                    ("Receiver clock error", "Deliberately falsified timestamp"),
                )
            )

        # The same fix (same time and place) delivered by more than one source: duplicated data.
        by_key: dict[tuple[float, float, float], list[Obs]] = {}
        for o in obs:
            if o.has_position:
                by_key.setdefault((round(o.ts, 3), round(o.lat or 0, 5), round(o.lon or 0, 5)), []).append(o)
        dups = [grp for grp in by_key.values() if len({o.source for o in grp}) > 1]
        for grun in group_runs(sorted(dups, key=lambda g: g[0].ts), lambda g: g[0].ts, c.run_join_s):
            flat = [o for g in grun for o in g]
            out.append(
                make(
                    "duplicate_record",
                    flat,
                    f"Duplicate records from multiple sources ({len(grun)})",
                    "Identical position fixes were delivered by more than one data source.",
                    Severity.LOW,
                    ("Overlapping feeds", "Re-ingestion under a different source name"),
                )
            )
        return out
