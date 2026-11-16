"""Threat-intelligence correlation. The AI is asked to keep four layers apart and the service ENFORCES it:
verified observations may cite only platform records, external facts only the supplied documents."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Principal
from app.intelligence import prompts
from app.intelligence.context import AIContext, build_anomaly_context, clean
from app.intelligence.schemas import ThreatCorrelation
from app.intelligence.service import ProviderFactory, _detection_echo, _run, effective_settings
from app.models import AIAnalysis
from app.threat_intel import service as intel

MAX_DOCS = 5


def build_context(
    session: Session, anomaly_id: str, max_chars: int
) -> tuple[AIContext, Any, list[dict[str, Any]]]:
    base, detail = build_anomaly_context(session, anomaly_id, max_chars)
    query = f"{detail.title} {detail.rule.name} {detail.detection_type.replace('_', ' ')} ADS-B"
    docs = intel.relevant_for(session, query, MAX_DOCS) or intel.relevant_for(
        session, "ADS-B security anomaly", MAX_DOCS
    )
    doc_rows = [
        clean(
            {
                "ref": f"D{i}",
                "title": d.title,
                "authors": d.authors,
                "published": str(d.publication_date or "unknown"),
                "source": d.source_name,
                "url": d.source_url,
                "excerpt": d.excerpt[:800],
                "reliability": d.reliability_notes,
            },
            800,
        )
        for i, d in enumerate(docs, start=1)
    ]
    data = {
        **base.data,
        "documents": doc_rows,
        "documents_note": "Documents are external research context, NOT evidence about this platform's data.",
    }
    text = json.dumps(data, separators=(",", ":"), default=str)
    if len(text) > max_chars * 2:  # documents add bounded extra context; refuse only if absurdly large
        raise ValueError("correlation context too large")
    allowed = frozenset(base.allowed_refs | {r["ref"] for r in doc_rows})
    return AIContext(data, allowed, text), detail, doc_rows


def make_validator(allowed: frozenset[str], doc_refs: set[str]) -> Any:
    platform = allowed - doc_refs

    def check(v: ThreatCorrelation) -> None:
        for f in v.verified_observations:
            if not f.refs or not set(f.refs) <= platform:
                raise ValueError(
                    "every verified_observation must cite at least one platform record (E*, RULE, AC, A*) "
                    "and no documents"
                )
        for f in v.external_facts:
            if not doc_refs:
                raise ValueError("no documents were supplied, so external_facts must be empty")
            if not f.refs or not set(f.refs) <= doc_refs:
                raise ValueError(
                    "every external_fact must cite at least one supplied document (D*) and nothing else"
                )
        # Hypotheses are the AI's own reasoning: ungrounded ones are removed and counted instead of
        # failing the whole analysis. The layers that carry factual weight above stay strict.
        grounded = [f for f in v.analytical_hypotheses if f.refs and set(f.refs) <= allowed]
        v.removed_ungrounded_hypotheses = len(v.analytical_hypotheses) - len(grounded)
        v.analytical_hypotheses = grounded
        unknown = sorted(v.refs() - allowed)
        if unknown:
            raise ValueError(f"unknown reference(s) {unknown}; cite only these ids: {sorted(allowed)}")

    return check


def correlate(
    session: Session,
    settings: Settings,
    factory: ProviderFactory,
    who: Principal,
    anomaly_id: str,
    provider: str | None,
    model: str | None,
) -> tuple[AIAnalysis, dict[str, Any]]:
    eff = effective_settings(session, settings)
    ctx, detail, docs = build_context(session, anomaly_id, settings.ai_max_context_chars)
    row = _run(
        session,
        settings,
        factory,
        eff,
        who,
        kind="threat_correlation",
        version=prompts.THREAT_CORRELATION_VERSION,
        system=prompts.THREAT_CORRELATION_SYSTEM,
        task="Assess consistency with documented categories of aviation data anomalies and security issues.",
        schema=ThreatCorrelation,
        ctx=ctx,
        anomaly_pk=detail.id,
        aircraft_pk=None,
        subject=detail.anomaly_id,
        entity="anomaly",
        provider=provider,
        model=model,
        validator=make_validator(ctx.allowed_refs, {d["ref"] for d in docs}),
        max_repairs=2,
    )
    out = dict(row.output or {})
    out["documents_supplied"] = [
        {k: d[k] for k in ("ref", "title", "authors", "published", "source", "url", "reliability")}
        for d in docs
    ]
    row.output = out
    session.commit()
    return row, _detection_echo(detail)
