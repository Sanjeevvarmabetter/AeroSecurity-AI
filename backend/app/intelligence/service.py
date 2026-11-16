"""Runs AI analyses. Deterministic detections are inputs only; nothing here can modify them."""

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import redact
from app.core.security import Principal
from app.intelligence import prompts
from app.intelligence.base import LLMProvider
from app.intelligence.context import AIContext, build_aircraft_context, build_anomaly_context
from app.intelligence.errors import AIError, InvalidModelOutput, NotConfigured
from app.intelligence.ollama import OllamaProvider
from app.intelligence.openrouter import OpenRouterProvider
from app.intelligence.schemas import AircraftInvestigation, AnomalyExplanation
from app.models import AIAnalysis, Aircraft, AISettings, AuditLog
from app.schemas.intelligence import AnalysisOut

log = logging.getLogger(__name__)

ProviderFactory = Callable[[str, str | None], LLMProvider]  # (provider name, model override) -> provider

# Wording that presents a hypothesis as established fact: flagged (never blocked) for the analyst.
# Negated or hedged phrasing ("cannot be confirmed as spoofing") is deliberately not flagged.
_ASSERT = (
    r"(?:confirm(?:s|ed|ing)?|prov(?:es?|en|ed|ing)|definitely|certainly|clearly|conclusively|undoubtedly)"
)
_TOPIC = r"(?:spoof\w*|attack\w*|hijack\w*|malicious|sabotage\w*|terror\w*|cyber\w*)"
_CERTAINTY = re.compile(
    rf"\b{_ASSERT}\b[^.;]{{0,60}}\b{_TOPIC}\b|\b(?:is|was|are|were)\s+(?:a\s+|an\s+)?(?:deliberate|confirmed)\b[^.;]{{0,30}}\b{_TOPIC}\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:not|cannot|can't|can not|no|nor|neither|without|unable|unconfirmed|never|fails? to|does not|do not|did not)\b[^.;]{0,30}$",  # noqa: E501
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class EffectiveAI:
    provider: str
    ollama_model: str
    openrouter_model: str
    source: str  # "environment" | "database"


def effective_settings(session: Session, settings: Settings) -> EffectiveAI:
    row = session.get(AISettings, 1)
    return EffectiveAI(
        provider=(row.provider if row and row.provider else settings.ai_provider),
        ollama_model=(row.ollama_model if row and row.ollama_model else settings.ollama_model),
        openrouter_model=(
            row.openrouter_model if row and row.openrouter_model else settings.openrouter_model
        ),
        source="database"
        if row and (row.provider or row.ollama_model or row.openrouter_model)
        else "environment",
    )


def make_provider_factory(settings: Settings, eff: EffectiveAI) -> ProviderFactory:
    def factory(provider: str, model: str | None) -> LLMProvider:
        common: dict[str, Any] = {
            "timeout_s": settings.ai_timeout_s,
            "max_tokens": settings.ai_max_output_tokens,
            "temperature": settings.ai_temperature,
        }
        if provider == "ollama":
            return OllamaProvider(model or eff.ollama_model, base_url=settings.ollama_base_url, **common)
        if provider == "openrouter":
            return OpenRouterProvider(
                model or eff.openrouter_model,
                api_key=settings.openrouter_api_key.get_secret_value(),
                base_url=settings.openrouter_base_url,
                max_retries=settings.ai_max_retries,
                **common,
            )
        raise NotConfigured(f"unknown AI provider '{provider}'")

    return factory


def certainty_warnings(output: dict[str, Any]) -> list[str]:
    text = " ".join(_strings(output))
    hits = {
        m.group(0)[:80]
        for m in _CERTAINTY.finditer(text)
        if not _NEGATION.search(text[max(0, m.start() - 40) : m.start()])
    }
    return [f'Wording presents a hypothesis as fact: "{h}"' for h in sorted(hits)]


def _strings(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def _ref_validator(allowed: frozenset[str]) -> Callable[[Any], None]:
    def check(value: Any) -> None:
        unknown = sorted(value.refs() - allowed)
        if unknown:
            raise ValueError(
                f"unknown evidence reference(s) {unknown}; cite only these ids: {sorted(allowed)}"
            )

    return check


def _record(
    session: Session,
    *,
    kind: str,
    who: Principal,
    anomaly_id: int | None,
    aircraft_id: int | None,
    provider: str,
    model: str,
    version: str,
    ctx: AIContext,
    status: str,
    output: dict[str, Any] | None,
    warnings: list[str],
    error: str | None,
    latency_ms: int | None,
    p_tok: int | None,
    c_tok: int | None,
    subject: str,
    entity: str,
) -> AIAnalysis:
    row = AIAnalysis(
        kind=kind,
        anomaly_id=anomaly_id,
        aircraft_id=aircraft_id,
        requested_by=who.actor,
        provider=provider,
        model=model,
        prompt_version=version,
        status=status,
        output=output,
        warnings=warnings,
        error=error,
        input_chars=ctx.chars,
        input_sha256=hashlib.sha256(ctx.text.encode()).hexdigest(),
        prompt_tokens=p_tok,
        completion_tokens=c_tok,
        latency_ms=latency_ms,
    )
    session.add(row)
    session.flush()
    # The audit entry records usage and selection, never the prompt or the generated text.
    session.add(
        AuditLog(
            actor=who.actor,
            action="ai.analysis" if status == "OK" else "ai.failed",
            entity_type=entity,
            entity_id=subject,
            details={
                "analysis_id": row.id,
                "kind": kind,
                "provider": provider,
                "model": model,
                "prompt_version": version,
                "status": status,
                "input_chars": ctx.chars,
                "latency_ms": latency_ms,
            },
        )
    )
    session.commit()
    return row


class AIRequestFailed(Exception):
    def __init__(self, error: AIError, analysis_id: int) -> None:
        super().__init__(str(error))
        self.error, self.analysis_id = error, analysis_id


def _run(
    session: Session,
    settings: Settings,
    factory: ProviderFactory,
    eff: EffectiveAI,
    who: Principal,
    *,
    kind: str,
    version: str,
    system: str,
    task: str,
    schema: type[BaseModel],
    ctx: AIContext,
    anomaly_pk: int | None,
    aircraft_pk: int | None,
    subject: str,
    entity: str,
    provider: str | None,
    model: str | None,
    validator: Callable[[Any], None] | None = None,
    max_repairs: int = 1,
) -> AIAnalysis:
    name = provider or eff.provider
    prov = factory(name, model)
    base: dict[str, Any] = dict(
        kind=kind,
        who=who,
        anomaly_id=anomaly_pk,
        aircraft_id=aircraft_pk,
        provider=name,
        model=prov.model or "",
        version=version,
        ctx=ctx,
        subject=subject,
        entity=entity,
    )
    try:
        res = prov.generate_structured(
            prompts.user_prompt(task, ctx.text),
            schema,
            system,
            validate=validator or _ref_validator(ctx.allowed_refs),
            max_repairs=max_repairs,
        )
    except AIError as exc:
        status = "INVALID_OUTPUT" if isinstance(exc, InvalidModelOutput) else "PROVIDER_ERROR"
        row = _record(
            session,
            status=status,
            output=None,
            warnings=[],
            error=redact(str(exc))[:500],
            latency_ms=None,
            p_tok=None,
            c_tok=None,
            **base,
        )
        raise AIRequestFailed(exc, row.id) from exc
    out = res.value.model_dump(mode="json")
    notes = [f"output needed {res.attempts} attempts to validate"] if res.attempts > 1 else []
    removed = out.get("removed_ungrounded_hypotheses")
    if removed:
        notes.append(f"{removed} AI hypothesis(es) were removed because they cited no valid evidence")
    return _record(
        session,
        status="OK",
        output=out,
        warnings=[*certainty_warnings(out), *notes],
        error=None,
        latency_ms=res.generation.latency_ms,
        p_tok=res.generation.prompt_tokens,
        c_tok=res.generation.completion_tokens,
        **{**base, "model": res.generation.model or base["model"]},
    )


def explain_anomaly(
    session: Session,
    settings: Settings,
    factory: ProviderFactory,
    who: Principal,
    anomaly_id: str,
    provider: str | None,
    model: str | None,
) -> tuple[AIAnalysis, dict[str, Any]]:
    eff = effective_settings(session, settings)
    ctx, detail = build_anomaly_context(session, anomaly_id, settings.ai_max_context_chars)
    row = _run(
        session,
        settings,
        factory,
        eff,
        who,
        kind="anomaly_explanation",
        version=prompts.ANOMALY_EXPLANATION_VERSION,
        system=prompts.ANOMALY_EXPLANATION_SYSTEM,
        task="Explain this detection for the analyst.",
        schema=AnomalyExplanation,
        ctx=ctx,
        anomaly_pk=detail.id,
        aircraft_pk=None,
        subject=detail.anomaly_id,
        entity="anomaly",
        provider=provider,
        model=model,
    )
    det = {
        "anomaly_id": detail.anomaly_id,
        "severity": detail.severity,
        "status": detail.status,
        "confidence": detail.confidence,
        "rule": f"{detail.rule.id} v{detail.rule.version}",
    }
    return row, det


def _detection_echo(d: Any) -> dict[str, Any]:
    return {
        "anomaly_id": d.anomaly_id,
        "severity": d.severity,
        "status": d.status,
        "confidence": d.confidence,
        "rule": f"{d.rule.id} v{d.rule.version}",
    }


def current_detection(session: Session, anomaly_id: str) -> dict[str, Any]:
    from app.services.anomalies import anomaly_detail

    return _detection_echo(anomaly_detail(session, anomaly_id))


def investigate_aircraft(
    session: Session,
    settings: Settings,
    factory: ProviderFactory,
    who: Principal,
    icao24: str,
    provider: str | None,
    model: str | None,
) -> AIAnalysis:
    eff = effective_settings(session, settings)
    ctx, pk = build_aircraft_context(session, icao24, settings.ai_max_context_chars)
    return _run(
        session,
        settings,
        factory,
        eff,
        who,
        kind="aircraft_investigation",
        version=prompts.AIRCRAFT_INVESTIGATION_VERSION,
        system=prompts.AIRCRAFT_INVESTIGATION_SYSTEM,
        task="Produce an investigation summary for this aircraft.",
        schema=AircraftInvestigation,
        ctx=ctx,
        anomaly_pk=None,
        aircraft_pk=pk,
        subject=icao24.lower(),
        entity="aircraft",
        provider=provider,
        model=model,
    )


def to_out(row: AIAnalysis, subject: str, deterministic: dict[str, Any] | None = None) -> AnalysisOut:
    return AnalysisOut(
        analysis_id=row.id,
        kind=row.kind,
        subject=subject,
        provider=row.provider,
        model=row.model,
        prompt_version=row.prompt_version,
        status=row.status,
        output=row.output,
        warnings=list(row.warnings or []),
        error=row.error,
        requested_by=row.requested_by,
        created_at=row.created_at,
        latency_ms=row.latency_ms,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        deterministic=deterministic,
    )


def list_analyses(
    session: Session, *, anomaly_pk: int | None, icao24: str | None, limit: int
) -> list[AIAnalysis]:
    q = select(AIAnalysis).order_by(AIAnalysis.created_at.desc(), AIAnalysis.id.desc()).limit(limit)
    if anomaly_pk is not None:
        q = q.where(AIAnalysis.anomaly_id == anomaly_pk)
    if icao24:
        q = q.where(
            AIAnalysis.aircraft_id
            == select(Aircraft.id).where(Aircraft.icao24 == icao24.lower()).scalar_subquery()
        )
    return list(session.scalars(q))
