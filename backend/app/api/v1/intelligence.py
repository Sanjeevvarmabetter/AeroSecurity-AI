import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import Principal, Role, ai_limiter, require_role
from app.intelligence import service
from app.intelligence.errors import AIError
from app.models import AISettings, AuditLog
from app.schemas.intelligence import (
    AircraftInvestigationRequest,
    AISettingsOut,
    AISettingsUpdate,
    AnalysisOut,
    AnomalyExplanationRequest,
    ProviderStatus,
)
from app.services.anomalies import parse_public_id
from app.services.aviation import NotFoundError

log = logging.getLogger(__name__)
viewer = Depends(require_role(Role.VIEWER))
analyst = require_role(Role.ANALYST)
admin = require_role(Role.ADMIN)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])
settings_router = APIRouter(prefix="/settings", tags=["settings"])

Db = Annotated[Session, Depends(get_session)]
Cfg = Annotated[Settings, Depends(get_settings)]


def get_provider_factory(db: Db, cfg: Cfg) -> service.ProviderFactory:
    """Dependency so tests can substitute a fake provider; production builds the configured one."""
    return service.make_provider_factory(cfg, service.effective_settings(db, cfg))


Factory = Annotated[service.ProviderFactory, Depends(get_provider_factory)]


def _limit(who: Principal, cfg: Settings) -> None:
    wait = ai_limiter.check(who.key_id, cfg.ai_rate_limit_per_minute)
    if wait is not None:
        raise HTTPException(
            429, f"AI request limit reached; retry in {wait}s", headers={"Retry-After": str(wait)}
        )


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except service.AIRequestFailed as e:
        raise HTTPException(
            e.error.status_code, f"{e.error} (recorded as AI analysis #{e.analysis_id})"
        ) from e
    except AIError as e:
        raise HTTPException(e.status_code, str(e)) from e


@router.post("/anomaly-explanation", response_model=AnalysisOut)
def anomaly_explanation(
    body: AnomalyExplanationRequest,
    db: Db,
    cfg: Cfg,
    factory: Factory,
    who: Annotated[Principal, Depends(analyst)],
) -> AnalysisOut:
    _limit(who, cfg)

    def go() -> AnalysisOut:
        row, det = service.explain_anomaly(db, cfg, factory, who, body.anomaly_id, body.provider, body.model)
        return service.to_out(row, body.anomaly_id, det)

    return _run(go)


@router.post("/aircraft-investigation", response_model=AnalysisOut)
def aircraft_investigation(
    body: AircraftInvestigationRequest,
    db: Db,
    cfg: Cfg,
    factory: Factory,
    who: Annotated[Principal, Depends(analyst)],
) -> AnalysisOut:
    _limit(who, cfg)

    def go() -> AnalysisOut:
        row = service.investigate_aircraft(db, cfg, factory, who, body.icao24, body.provider, body.model)
        return service.to_out(row, body.icao24.lower())

    return _run(go)


@router.get("/analyses", response_model=list[AnalysisOut], dependencies=[viewer])
def analyses(
    db: Db,
    anomaly_id: Annotated[str | None, Query(pattern=r"^ANM-\d{1,9}$")] = None,
    icao24: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{6}$")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[AnalysisOut]:
    def go() -> list[AnalysisOut]:
        pk = parse_public_id(anomaly_id) if anomaly_id else None
        rows = service.list_analyses(db, anomaly_pk=pk, icao24=icao24, limit=limit)
        # Always show the detection as it is NOW next to stored AI text, so stale AI output is never mistaken
        # for the current verdict.
        det = service.current_detection(db, anomaly_id) if anomaly_id else None
        return [service.to_out(r, anomaly_id or icao24 or "", det) for r in rows]

    return _run(go)


# -- settings ----------------------------------------------------------------------------------------
@settings_router.get("/ai", response_model=AISettingsOut, dependencies=[viewer])
def get_ai_settings(db: Db, cfg: Cfg, factory: Factory, check: bool = False) -> AISettingsOut:
    eff = service.effective_settings(db, cfg)
    statuses: list[ProviderStatus] = []
    for name, model, configured, url in (
        ("ollama", eff.ollama_model, bool(eff.ollama_model), cfg.ollama_base_url),
        (
            "openrouter",
            eff.openrouter_model,
            bool(cfg.openrouter_api_key.get_secret_value() and eff.openrouter_model),
            None,
        ),
    ):
        healthy: bool | None = None
        detail: str | None = None
        models: list[str] | None = None
        if check:
            try:
                p = factory(name, None)
                h = p.health_check()
                healthy, detail = h.ok, h.detail
                models = [m.id for m in p.list_models()][:400] if h.ok or name == "openrouter" else []
            except AIError as e:
                healthy, detail = False, str(e)
        statuses.append(
            ProviderStatus(
                name=name,
                configured=configured,
                current_model=model or None,
                healthy=healthy,
                detail=detail,
                models=models,
                base_url=url,
            )
        )
    return AISettingsOut(
        provider=eff.provider,
        source=eff.source,
        providers=statuses,
        limits={
            "timeout_s": cfg.ai_timeout_s,
            "max_output_tokens": cfg.ai_max_output_tokens,
            "max_context_chars": cfg.ai_max_context_chars,
            "requests_per_minute": cfg.ai_rate_limit_per_minute,
        },
    )


@settings_router.put("/ai", response_model=AISettingsOut)
def put_ai_settings(
    body: AISettingsUpdate, db: Db, cfg: Cfg, factory: Factory, who: Annotated[Principal, Depends(admin)]
) -> AISettingsOut:
    before = service.effective_settings(db, cfg)
    row = db.get(AISettings, 1) or AISettings(id=1)
    db.add(row)
    for field in ("provider", "ollama_model", "openrouter_model"):
        v = getattr(body, field)
        if v is not None:
            setattr(row, field, v)
    row.updated_by = who.actor
    after = service.effective_settings(db, cfg)  # flushes via autoflush
    db.add(
        AuditLog(
            actor=who.actor,
            action="ai.settings_changed",
            entity_type="ai_settings",
            entity_id="1",
            details={
                "before": {
                    "provider": before.provider,
                    "ollama_model": before.ollama_model,
                    "openrouter_model": before.openrouter_model,
                },
                "after": {
                    "provider": after.provider,
                    "ollama_model": after.ollama_model,
                    "openrouter_model": after.openrouter_model,
                },
            },
        )
    )
    db.commit()
    return get_ai_settings(db, cfg, factory, check=False)
