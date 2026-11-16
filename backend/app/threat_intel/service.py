"""Threat-intelligence store. Items carry source, URL, retrieval time, excerpt and reliability limits."""

import re
from datetime import date
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models import AuditLog, ThreatIntelligence
from app.services.aviation import NotFoundError
from app.threat_intel import arxiv

_TAG = re.compile(r"^[a-z0-9][a-z0-9 \-]{0,30}$")


class IntelError(Exception):
    status_code = 422


def validate_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https" or not p.netloc or len(url) > 512 or any(c in url for c in " \n\r\t<>\"'"):
        raise IntelError("source_url must be a plain https URL")
    return url


def add_manual(
    session: Session,
    who: Principal,
    *,
    source_name: str,
    source_url: str,
    title: str,
    authors: str | None,
    publication_date: date | None,
    excerpt: str,
    reliability_notes: str,
    tags: list[str],
) -> ThreatIntelligence:
    url = validate_url(source_url)
    if session.scalar(select(ThreatIntelligence.id).where(ThreatIntelligence.source_url == url)):
        raise IntelError("an item with this source_url already exists")
    clean_tags = sorted({t.strip().lower() for t in tags if _TAG.match(t.strip().lower())})[:10]
    item = ThreatIntelligence(
        source_name=source_name,
        source_url=url,
        title=title,
        authors=authors,
        publication_date=publication_date,
        excerpt=excerpt,
        reliability_notes=reliability_notes,
        tags=clean_tags,
        origin="manual",
        added_by=who.actor,
    )
    session.add(item)
    session.flush()
    session.add(
        AuditLog(
            actor=who.actor,
            action="intel.added",
            entity_type="threat_intel",
            entity_id=str(item.id),
            details={"origin": "manual", "source": source_name, "url": url},
        )
    )
    session.commit()
    return item


def import_arxiv(
    session: Session,
    who: Principal,
    query: str,
    max_results: int,
    entries: list[arxiv.ArxivEntry] | None = None,
) -> dict[str, int]:
    found = entries if entries is not None else arxiv.search(query, max_results)
    added = skipped = 0
    for e in found:
        if session.scalar(select(ThreatIntelligence.id).where(ThreatIntelligence.source_url == e.url)):
            skipped += 1
            continue
        session.add(
            ThreatIntelligence(
                source_name="arXiv",
                source_url=e.url,
                title=e.title,
                authors=e.authors or None,
                publication_date=e.published,
                excerpt=e.abstract,
                reliability_notes=arxiv.RELIABILITY,
                tags=["arxiv", "research"],
                origin="arxiv",
                added_by=who.actor,
            )
        )
        added += 1
    session.add(
        AuditLog(
            actor=who.actor,
            action="intel.imported",
            entity_type="threat_intel",
            entity_id=None,
            details={"source": "arXiv", "query": query, "added": added, "skipped": skipped},
        )
    )
    session.commit()
    return {"found": len(found), "added": added, "skipped_existing": skipped}


def search(session: Session, q: str | None, limit: int, offset: int) -> tuple[list[ThreatIntelligence], int]:
    """Full-text search (websearch syntax is parsed safely by PostgreSQL; no SQL is built from `q`)."""
    stmt = select(ThreatIntelligence)
    if q:
        doc = func.to_tsvector("english", ThreatIntelligence.title + " " + ThreatIntelligence.excerpt)
        stmt = stmt.where(doc.op("@@")(func.websearch_to_tsquery("english", q)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(ThreatIntelligence.publication_date.desc().nulls_last(), ThreatIntelligence.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get(session: Session, item_id: int) -> ThreatIntelligence:
    item = session.get(ThreatIntelligence, item_id)
    if item is None:
        raise NotFoundError(f"intel item {item_id} not found")
    return item


def relevant_for(session: Session, text: str, limit: int = 5) -> list[ThreatIntelligence]:
    """Documents relevant to a free-text description, ranked by full-text relevance."""
    words = re.findall(r"[A-Za-z]{4,}", text)[:25]
    if not words:
        return []
    doc = func.to_tsvector("english", ThreatIntelligence.title + " " + ThreatIntelligence.excerpt)
    q = func.to_tsquery("english", " | ".join(sorted({w.lower() for w in words})))
    rank = func.ts_rank(doc, q)
    return list(
        session.scalars(select(ThreatIntelligence).where(doc.op("@@")(q)).order_by(rank.desc()).limit(limit))
    )
