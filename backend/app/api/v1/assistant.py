import re
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import select

from app.api.v1.intelligence import Cfg, Db, Factory, _limit
from app.core.security import Principal, Role, require_role
from app.intelligence import chat as chat_svc
from app.intelligence import correlation, service
from app.intelligence.errors import AIError
from app.models import Conversation, IntelligenceReport, ThreatIntelligence
from app.reports import builder, pdf
from app.reports import markdown as md
from app.schemas.common import Page
from app.schemas.intelligence import (
    AnalysisOut,
    ArxivImport,
    ChatMessageOut,
    ChatOut,
    ChatRequest,
    CitationOut,
    ConversationDetail,
    ConversationOut,
    IntelCreate,
    IntelOut,
    ReportMeta,
    ReportOut,
    ReportRequest,
    ThreatCorrelationRequest,
    ToolCallOut,
)
from app.services.aviation import NotFoundError
from app.threat_intel import arxiv
from app.threat_intel import service as intel

viewer = Depends(require_role(Role.VIEWER))
analyst = Depends(require_role(Role.ANALYST))
router = APIRouter(prefix="/intelligence", tags=["intelligence"])
intel_router = APIRouter(prefix="/threat-intel", tags=["threat-intel"])
Who = Annotated[Principal, Depends(require_role(Role.ANALYST))]
WhoViewer = Annotated[Principal, Depends(require_role(Role.VIEWER))]


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except service.AIRequestFailed as e:
        raise HTTPException(
            e.error.status_code, f"{e.error} (recorded as AI analysis #{e.analysis_id})"
        ) from e
    except (AIError, chat_svc.ConversationError, builder.ReportError, intel.IntelError) as e:
        raise HTTPException(e.status_code, str(e)) from e
    except arxiv.ArxivError as e:
        raise HTTPException(502, str(e)) from e


def classify(ref: str) -> tuple[str, str | None]:
    if re.fullmatch(r"ANM-\d+", ref):
        return "anomaly", f"/anomalies/{ref}"
    for prefix, kind in (("AC:", "aircraft"), ("TRAJ:", "trajectory"), ("OBS:", "observations")):
        if ref.startswith(prefix) and re.fullmatch(r"[0-9a-f]{6}", ref[len(prefix) :]):
            return kind, f"/aircraft/{ref[len(prefix) :]}"
    if re.fullmatch(r"DOC:\d+", ref):
        return "document", f"/threat-intel?doc={ref[4:]}"
    if ref.startswith("AP:"):
        return "airport", None
    return "other", None


def _cit(items: list[dict[str, str]] | None) -> list[CitationOut]:
    out = []
    for c in items or []:
        kind, link = classify(c["ref"])
        out.append(CitationOut(ref=c["ref"], note=c.get("note", ""), kind=kind, link=link))
    return out


# -- chat --------------------
@router.post("/chat", response_model=ChatOut)
def chat(body: ChatRequest, db: Db, cfg: Cfg, factory: Factory, who: Who) -> ChatOut:
    _limit(who, cfg)

    def go() -> ChatOut:
        r = chat_svc.chat(
            db,
            cfg,
            factory,
            who,
            conversation_id=body.conversation_id,
            message=body.message,
            provider=body.provider,
            model=body.model,
        )
        return ChatOut(
            conversation_id=r.conversation_id,
            answer=r.answer,
            citations=_cit(r.citations),
            tool_calls=[
                ToolCallOut(tool=t.tool, arguments=t.arguments, ok=t.ok, error=t.error, records=t.records)
                for t in r.tool_calls
            ],
            warnings=r.warnings,
            provider=r.provider,
            model=r.model,
        )

    return _run(go)


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(
    db: Db, who: WhoViewer, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> list[ConversationOut]:
    q = select(Conversation).order_by(Conversation.created_at.desc()).limit(limit)
    if who.role != Role.ADMIN:
        q = q.where(Conversation.owner == who.actor)
    return [
        ConversationOut(id=c.id, title=c.title, owner=c.owner, created_at=c.created_at) for c in db.scalars(q)
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation(
    db: Db, who: WhoViewer, conversation_id: Annotated[str, Path(pattern=r"^[0-9a-f\-]{36}$")]
) -> ConversationDetail:
    c = db.get(Conversation, conversation_id)
    if c is None or (c.owner != who.actor and who.role != Role.ADMIN):
        raise HTTPException(404, "conversation not found")
    msgs = [
        ChatMessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            tool_name=m.tool_name,
            tool_args=m.tool_args,
            citations=_cit(m.citations) if m.citations is not None else None,
            warnings=m.warnings,
            provider=m.provider,
            model=m.model,
            created_at=m.created_at,
        )
        for m in chat_svc.conversation_messages(db, c)
    ]
    return ConversationDetail(id=c.id, title=c.title, owner=c.owner, created_at=c.created_at, messages=msgs)


# -- threat correlation --------------------
@router.post("/threat-correlation", response_model=AnalysisOut)
def threat_correlation(
    body: ThreatCorrelationRequest, db: Db, cfg: Cfg, factory: Factory, who: Who
) -> AnalysisOut:
    _limit(who, cfg)

    def go() -> AnalysisOut:
        row, det = correlation.correlate(db, cfg, factory, who, body.anomaly_id, body.provider, body.model)
        return service.to_out(row, body.anomaly_id, det)

    return _run(go)


# -- reports --------------------
def _meta(r: IntelligenceReport) -> ReportMeta:
    return ReportMeta(
        id=r.id,
        title=r.title,
        subject_type=r.subject_type,
        subject=r.subject,
        created_by=r.created_by,
        created_at=r.created_at,
        includes_ai=r.includes_ai,
    )


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(body: ReportRequest, db: Db, who: Who) -> ReportOut:
    def go() -> ReportOut:
        st, subj = (
            ("anomaly", body.anomaly_id) if body.anomaly_id else ("aircraft", (body.icao24 or "").lower())
        )
        r = builder.build(db, who, st, subj, body.include_ai)
        return ReportOut(**_meta(r).model_dump(), structured=r.structured, markdown=r.markdown)

    return _run(go)


@router.get("/reports", response_model=list[ReportMeta], dependencies=[viewer])
def list_reports(db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 30) -> list[ReportMeta]:
    return [
        _meta(r)
        for r in db.scalars(
            select(IntelligenceReport).order_by(IntelligenceReport.created_at.desc()).limit(limit)
        )
    ]


@router.get("/reports/{report_id}", response_model=ReportOut, dependencies=[viewer])
def get_report(db: Db, report_id: Annotated[int, Path(ge=1)]) -> ReportOut:
    r = _run(lambda: builder.get(db, report_id))
    return ReportOut(**_meta(r).model_dump(), structured=r.structured, markdown=r.markdown)


@router.get("/reports/{report_id}/export", dependencies=[viewer])
def export_report(
    db: Db, who: WhoViewer, report_id: Annotated[int, Path(ge=1)], format: Literal["md", "pdf"] = "md"
) -> Response:
    r = _run(lambda: builder.get(db, report_id))
    if format == "pdf":
        content, media = pdf.render(r.structured, r.id), "application/pdf"
    else:
        content, media = md.render(r.structured).encode(), "text/markdown; charset=utf-8"
    from app.models import AuditLog

    db.add(
        AuditLog(
            actor=who.actor,
            action="report.exported",
            entity_type="report",
            entity_id=str(r.id),
            details={"format": format},
        )
    )
    db.commit()
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="aerosecurity-report-{r.id}.{format}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


# -- threat intelligence --------------------
def _intel_out(i: ThreatIntelligence) -> IntelOut:
    return IntelOut(
        id=i.id,
        source_name=i.source_name,
        source_url=i.source_url,
        title=i.title,
        authors=i.authors,
        publication_date=str(i.publication_date) if i.publication_date else None,
        retrieved_at=i.retrieved_at,
        excerpt=i.excerpt,
        reliability_notes=i.reliability_notes,
        tags=list(i.tags or []),
        origin=i.origin,
        added_by=i.added_by,
    )


@intel_router.get("", response_model=Page[IntelOut], dependencies=[viewer])
def list_intel(
    db: Db,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[IntelOut]:
    items, total = intel.search(db, q, limit, offset)
    return Page(items=[_intel_out(i) for i in items], total=total, limit=limit, offset=offset)


@intel_router.post("", response_model=IntelOut, status_code=201)
def add_intel(body: IntelCreate, db: Db, who: Who) -> IntelOut:
    item = _run(
        lambda: intel.add_manual(
            db,
            who,
            source_name=body.source_name,
            source_url=body.source_url,
            title=body.title,
            authors=body.authors,
            publication_date=body.publication_date.date() if body.publication_date else None,
            excerpt=body.excerpt,
            reliability_notes=body.reliability_notes,
            tags=body.tags,
        )
    )
    return _intel_out(item)


@intel_router.post("/import/arxiv")
def import_arxiv(body: ArxivImport, db: Db, cfg: Cfg, who: Who) -> dict[str, int]:
    _limit(who, cfg)
    return _run(lambda: intel.import_arxiv(db, who, body.query, body.max_results))


@intel_router.get("/{item_id}", response_model=IntelOut, dependencies=[viewer])
def get_intel(db: Db, item_id: Annotated[int, Path(ge=1)]) -> IntelOut:
    return _intel_out(_run(lambda: intel.get(db, item_id)))
