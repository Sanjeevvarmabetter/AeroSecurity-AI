"""Intelligence report assembly. Every section carries an explicit PROVENANCE: platform-derived facts are kept
apart from AI-generated content, which is always labelled unverified. The same structure renders to Markdown and PDF."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core.security import Principal
from app.models import AIAnalysis, Aircraft, AuditLog, DataSource, IntelligenceReport
from app.services import anomalies as an
from app.services import aviation as av
from app.services.aviation import NotFoundError

VERIFIED = "VERIFIED_PLATFORM_DATA"
AI = "AI_GENERATED_UNVERIFIED"
NOTICE = (
    "UNREVIEWED REPORT. Sections marked VERIFIED PLATFORM DATA are generated deterministically from stored records. "
    "Sections marked AI-GENERATED are model output, were not verified by a human, and are NOT security findings. "
    "Detections are data patterns, not determinations of cause or intent."
)


class ReportError(Exception):
    status_code = 409


def _iso(d: datetime | None) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S UTC") if d else "not available"


def _v(x: Any) -> str:
    return "not available" if x is None or x == "" else str(x)


def _sec(sid: str, title: str, prov: str, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {"id": sid, "title": title, "provenance": prov, "blocks": [b for b in blocks if b]}


def _p(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "text": text}


def _bul(items: list[str]) -> dict[str, Any]:
    return {"type": "bullets", "items": items} if items else {}


def _tbl(columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {"type": "table", "columns": columns, "rows": rows} if rows else {}


def _latest_ok(
    session: Session, kind: str, *, anomaly_pk: int | None, aircraft_pk: int | None
) -> AIAnalysis | None:
    q = select(AIAnalysis).where(AIAnalysis.kind == kind, AIAnalysis.status == "OK")
    q = (
        q.where(AIAnalysis.anomaly_id == anomaly_pk)
        if anomaly_pk is not None
        else q.where(AIAnalysis.aircraft_id == aircraft_pk)
    )
    return session.scalar(q.order_by(AIAnalysis.created_at.desc(), AIAnalysis.id.desc()).limit(1))


def _ai_blocks(a: AIAnalysis) -> list[dict[str, Any]]:
    o = a.output or {}
    head = _p(
        f"AI analysis #{a.id} ({a.kind.replace('_', ' ')}) by {a.provider}/{a.model}, prompt {a.prompt_version}, "
        f"requested by {a.requested_by}. Unverified."
    )
    blocks: list[dict[str, Any]] = [head]
    for key, label in (
        ("what_happened", "What happened"),
        ("rule_triggered", "Rule triggered"),
        ("why_it_may_matter", "Why it may matter"),
        ("activity_summary", "Activity summary"),
        ("ai_interpretation", "Interpretation"),
    ):
        if isinstance(o.get(key), str):
            blocks.append(_p(f"{label}: {o[key]}"))
    for key, label in (
        ("verified_observations", "Observations cited from platform records"),
        ("external_facts", "Statements from supplied documents"),
        ("analytical_hypotheses", "Hypotheses (AI reasoning)"),
        ("unusual_observations", "Unusual observations"),
    ):
        items = o.get(key)
        if isinstance(items, list) and items:
            blocks.append(_p(label + ":"))
            blocks.append(
                _bul(
                    [
                        f"{i.get('text', '')} [{', '.join(i.get('refs', []))}]"
                        for i in items
                        if isinstance(i, dict)
                    ]
                )
            )
    if a.warnings:
        blocks.append(_p("Warnings raised by the platform: " + "; ".join(a.warnings)))
    return blocks


def build(
    session: Session, who: Principal, subject_type: str, subject: str, include_ai: bool
) -> IntelligenceReport:
    now = datetime.now(UTC)
    sections: list[dict[str, Any]] = []
    anomalies_out: list[Any] = []
    anomaly_pk: int | None = None
    detail: Any = None

    if subject_type == "anomaly":
        detail = an.anomaly_detail(session, subject)
        anomaly_pk, icao = detail.id, detail.icao24
        anomalies_out = [detail]
    else:
        icao = subject.lower()
    ac = av.aircraft_detail(session, icao) if icao else None
    aircraft_pk = session.scalar(select(Aircraft.id).where(Aircraft.icao24 == icao)) if icao else None
    if subject_type == "aircraft":
        page = an.list_anomalies(
            session,
            severity=None,
            status=None,
            detection_type=None,
            rule_id=None,
            icao24=icao,
            airport=None,
            min_confidence=None,
            start=None,
            end=None,
            sort="event_start",
            order="asc",
            limit=50,
            offset=0,
        )
        anomalies_out = [x for x in page.items if x.icao24 == icao]
    traj = av.trajectory(session, icao, None, None, 120.0) if icao and ac and ac.positioned_count else None

    ais: list[AIAnalysis] = []
    if include_ai:
        if subject_type == "anomaly":
            kinds = ("anomaly_explanation", "threat_correlation")
            ais = [a for k in kinds if (a := _latest_ok(session, k, anomaly_pk=anomaly_pk, aircraft_pk=None))]
        else:
            ais = [
                a
                for a in [
                    _latest_ok(session, "aircraft_investigation", anomaly_pk=None, aircraft_pk=aircraft_pk)
                ]
                if a
            ]
        if not ais:
            raise ReportError(
                "no AI analysis exists for this subject yet; request one first, or generate the report without AI"
            )

    # 1. Executive summary: deterministic only
    if detail:
        summ = (
            f"{detail.anomaly_id}: {detail.title}. Severity {detail.severity} and confidence {detail.confidence:.2f} "
            f"were assigned by rule {detail.rule.id} v{detail.rule.version} (confidence is in the data pattern, not the "
            f"probability of malicious activity). Event window {_iso(detail.event_start)} to {_iso(detail.event_end)}; "
            f"status {detail.status}; {len(detail.evidence)} evidence items."
        )
        title = f"Intelligence report: {detail.anomaly_id}, {detail.title}"
    else:
        n_hi = sum(1 for a in anomalies_out if a.severity in ("HIGH", "CRITICAL"))
        summ = (
            f"Aircraft {icao}: {ac.observation_count if ac else 0} stored observations between "
            f"{_iso(ac.first_seen) if ac else 'n/a'} and {_iso(ac.last_seen) if ac else 'n/a'}; "
            f"{len(anomalies_out)} detection(s), {n_hi} of them HIGH or CRITICAL."
        )
        title = f"Intelligence report: aircraft {icao}"
    sections.append(_sec("executive_summary", "Executive summary", VERIFIED, _p(summ)))

    # 2. Aircraft information
    if ac:
        sections.append(
            _sec(
                "aircraft",
                "Aircraft information",
                VERIFIED,
                _tbl(
                    ["Field", "Value"],
                    [
                        ["ICAO24", ac.icao24],
                        ["Registration", _v(ac.registration)],
                        ["Type", _v(ac.aircraft_type)],
                        ["Manufacturer / model", _v(" ".join(x for x in (ac.manufacturer, ac.model) if x))],
                        ["Operator", _v(ac.operator)],
                        ["Origin country (as reported)", _v(ac.origin_country)],
                        ["Callsigns seen", _v(", ".join(ac.callsigns))],
                        ["Observations", f"{ac.observation_count} ({ac.positioned_count} with position)"],
                        ["Observation sources", _v(", ".join(ac.observation_sources))],
                        ["Metadata source", _v(ac.metadata_source)],
                    ],
                ),
                _p(
                    "Fields shown as 'not available' were not provided by any registered source and are not inferred."
                ),
            )
        )

    # 3. Timeline
    events: list[tuple[datetime, str]] = []
    if ac and ac.first_seen:
        events.append((ac.first_seen, "First observation of this aircraft"))
    for a in anomalies_out:
        events.append((a.event_start, f"{a.anomaly_id} begins: {a.title} ({a.severity})"))
        if a.event_end != a.event_start:
            events.append((a.event_end, f"{a.anomaly_id} ends"))
    if traj:
        for sg in [s for s in traj.segments if s.is_gap][:5]:
            events.append((sg.start, f"Observation gap of {round(sg.dt_s)} s begins (position not observed)"))
    if ac and ac.last_seen:
        events.append((ac.last_seen, "Last observation of this aircraft"))
    sections.append(
        _sec(
            "timeline",
            "Observation timeline",
            VERIFIED,
            _tbl(["Time", "Event"], [[_iso(t), e] for t, e in sorted(events, key=lambda x: x[0])][:40]),
        )
    )

    # 4. Detected anomalies
    sections.append(
        _sec(
            "anomalies",
            "Detected anomalies",
            VERIFIED,
            _tbl(
                ["ID", "Rule", "Severity", "Confidence", "Status", "Data quality", "Title"],
                [
                    [
                        a.anomaly_id,
                        a.rule_id,
                        a.severity,
                        f"{a.confidence:.2f}",
                        a.status,
                        a.data_quality,
                        a.title,
                    ]
                    for a in anomalies_out[:25]
                ],
            )
            or _p("No detections are recorded for this subject."),
        )
    )

    # 5. Evidence
    if detail:
        rows = []
        for e in detail.evidence[:20]:
            p = e.payload
            if e.kind == "observation":
                rows.append(
                    [
                        f"E{e.ordinal}",
                        _v(p.get("t")),
                        f"{p.get('lat')}, {p.get('lon')}",
                        _v(p.get("baro_altitude_m")),
                        _v(p.get("velocity_ms")),
                        _v(p.get("squawk")),
                    ]
                )
        sections.append(
            _sec(
                "evidence",
                "Evidence",
                VERIFIED,
                _tbl(["Ref", "Time", "Position", "Baro alt (m)", "Speed (m/s)", "Squawk"], rows),
                _bul(
                    [
                        f"{k.replace('_', ' ')}: {v}"
                        for k, v in detail.summary.items()
                        if not isinstance(v, dict | list)
                    ]
                ),
            )
        )

    # 6. AI analysis
    if ais:
        blocks = [b for a in ais for b in _ai_blocks(a)]
        sections.append(_sec("ai_analysis", "AI analysis (unverified)", AI, *blocks))

    # 7. Alternative explanations
    alts: list[str] = list(detail.alternatives) if detail else []
    sections.append(
        _sec(
            "alternatives",
            "Alternative explanations",
            VERIFIED,
            _p("From the detection rule's definition; none has been ruled out:") if alts else {},
            _bul(alts),
        )
    )
    ai_alts = [
        x
        for a in ais
        for x in (a.output or {}).get("alternative_explanations", [])
        or (a.output or {}).get("possible_explanations", [])
    ]
    if ai_alts:
        sections.append(
            _sec(
                "alternatives_ai",
                "Alternative explanations suggested by AI",
                AI,
                _bul([str(x) for x in ai_alts]),
            )
        )

    # 8. Security relevance
    rel = [
        _p(
            "Platform statement: severity and confidence are produced by deterministic rules. A detection indicates a data "
            "pattern worth review; it does not establish malicious activity, cause or intent."
        )
    ]
    why = [
        str((a.output or {}).get("why_it_may_matter"))
        for a in ais
        if (a.output or {}).get("why_it_may_matter")
    ]
    sections.append(_sec("relevance", "Security relevance", VERIFIED, *rel))
    if why or any((a.output or {}).get("security_implications") for a in ais):
        imp = why + [str(x) for a in ais for x in (a.output or {}).get("security_implications", [])]
        sections.append(_sec("relevance_ai", "Security relevance (AI view)", AI, _bul(imp)))

    # 9. Recommendations
    if detail and detail.investigation:
        sections.append(
            _sec(
                "investigation",
                "Investigation record",
                VERIFIED,
                _p(
                    f"Investigation opened {_iso(detail.investigation.opened_at)} by {detail.investigation.opened_by}; status {detail.status}; "
                    f"{len(detail.notes)} analyst note(s)."
                ),
            )
        )
    recs = [
        str(x)
        for a in ais
        for x in ((a.output or {}).get("next_steps") or (a.output or {}).get("recommendations") or [])
    ]
    if recs:
        sections.append(
            _sec("recommendations", "Investigation recommendations (AI-suggested)", AI, _bul(recs))
        )

    # 10. Limitations
    lim = [
        "Observations come from volunteer receivers; coverage, timestamps (up to ~1 s jitter) and gaps affect every statistic.",
        "Detection thresholds are configurable and have not been validated against labelled attack data; no accuracy claim is made.",
    ]
    if traj and traj.summary.gap_count:
        lim.append(
            f"{traj.summary.gap_count} observation gap(s) totalling {round(traj.summary.gap_total_s)} s; movement inside gaps is unobserved."
        )
    if ac and len(ac.observation_sources) <= 1:
        lim.append(
            "Only one observation source is present, so cross-source consistency could not be assessed."
        )
    if detail and detail.data_quality != "GOOD":
        lim.append(f"This detection's data quality is {detail.data_quality}.")
    lim += [
        str(x)
        for a in ais
        for x in (a.output or {}).get("limitations", []) or (a.output or {}).get("gaps_and_limitations", [])
    ]
    sections.append(_sec("limitations", "Data limitations", VERIFIED, _bul(lim)))

    # 11. Sources
    srcs = (
        session.scalars(
            select(DataSource).where(
                DataSource.name.in_(
                    ac.observation_sources + ([ac.metadata_source] if ac and ac.metadata_source else [])
                )
            )
        ).all()
        if ac
        else []
    )
    refs = [f"Data source: {s.name} ({s.kind}); terms: {s.terms_url or 'n/a'}" for s in srcs]
    for a in ais:
        for d in (a.output or {}).get("documents_supplied", []):
            refs.append(
                f"Document {d['ref']}: {d['title']} ({d['authors'] or 'authors n/a'}, {d['published']}) {d['url']}. Reliability: {d['reliability']}"
            )
        refs.append(f"AI: {a.provider}/{a.model}, prompt {a.prompt_version}, analysis #{a.id}")
    if detail:
        refs.append(f"Detection rule: {detail.rule.id} v{detail.rule.version} ({detail.rule.name})")
    refs.append(f"Generated by AeroSecurity AI v{__version__} for {who.actor} on {_iso(now)}")
    sections.append(_sec("sources", "Source references", VERIFIED, _bul(refs)))

    structured = {
        "title": title,
        "generated_at": now.isoformat(),
        "subject": {"type": subject_type, "id": subject},
        "status": "UNREVIEWED",
        "includes_ai": bool(ais),
        "notice": NOTICE,
        "sections": sections,
    }
    from app.reports.markdown import render

    row = IntelligenceReport(
        title=title[:300],
        subject_type=subject_type,
        subject=subject,
        created_by=who.actor,
        includes_ai=bool(ais),
        ai_analysis_ids=[a.id for a in ais],
        structured=structured,
        markdown=render(structured),
    )
    session.add(row)
    session.flush()
    session.add(
        AuditLog(
            actor=who.actor,
            action="report.generated",
            entity_type="report",
            entity_id=str(row.id),
            details={
                "subject_type": subject_type,
                "subject": subject,
                "includes_ai": bool(ais),
                "ai_analysis_ids": row.ai_analysis_ids,
            },
        )
    )
    session.commit()
    return row


def get(session: Session, report_id: int) -> IntelligenceReport:
    r = session.get(IntelligenceReport, report_id)
    if r is None:
        raise NotFoundError(f"report {report_id} not found")
    return r
