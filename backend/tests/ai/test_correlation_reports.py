"""Threat correlation (layer separation) and report generation/export. Seeded data is synthetic."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIAnalysis, Anomaly, AuditLog, IntelligenceReport, ThreatIntelligence
from app.reports import markdown as md
from app.reports import pdf
from tests.ai.test_chat import ADM, A, V, api, env  # noqa: F401  (fixtures)
from tests.ai.test_tools import world

pytestmark = pytest.mark.integration


def add_doc(db: Session) -> None:
    db.add(
        ThreatIntelligence(
            source_name="arXiv",
            source_url="https://arxiv.org/abs/0000.00009",
            title="ADS-B security anomaly detection study",
            authors="A. Author",
            excerpt="This security anomaly study describes spoofing of ADS-B emergency squawk messages in a lab.",
            reliability_notes="Preprint; abstract only; lab attack.",
            tags=["arxiv"],
            origin="arxiv",
            added_by="test",
        )
    )
    db.flush()


GOOD = {
    "verified_observations": [{"text": "Squawk 7700 for 5 observations.", "refs": ["E0", "RULE"]}],
    "external_facts": [
        {"text": "A study describes lab spoofing of emergency squawk messages.", "refs": ["D1"]}
    ],
    "analytical_hypotheses": [
        {"text": "Could be a genuine emergency or a decoding artefact.", "refs": ["E0", "D1"]}
    ],
    "ai_interpretation": "The pattern is consistent with a squawk event; the study does not show it happened here.",
    "consistent_with_categories": ["emergency squawk event"],
    "gaps_and_limitations": ["Single source", "Lab research only"],
}


def correlate(api: TestClient, a: Anomaly, **kw: Any) -> Any:
    return api.post(
        "/api/v1/intelligence/threat-correlation", json={"anomaly_id": f"ANM-{a.id:04d}", **kw}, headers=A
    )


# ---- threat correlation --------------------------------------------------------------------------------------
def test_correlation_keeps_layers_apart_and_attaches_documents(
    api: TestClient, env: Any, db_session: Session
) -> None:
    a = world(db_session)
    add_doc(db_session)
    before = (a.severity, a.status, a.confidence)
    env.replies = [json.dumps(GOOD)]
    r = correlate(api, a)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (
        d["kind"] == "threat_correlation"
        and d["ai_generated"] is True
        and d["prompt_version"] == "threat-correlation/1"
    )
    out = d["output"]
    assert out["external_facts"][0]["refs"] == ["D1"] and out["verified_observations"][0]["refs"] == [
        "E0",
        "RULE",
    ]
    sup = out["documents_supplied"][0]
    assert (
        sup["ref"] == "D1"
        and sup["url"] == "https://arxiv.org/abs/0000.00009"
        and "lab attack" in sup["reliability"]
    )
    user = env.providers[0].seen[0][1].content
    ctx = json.loads(user[user.index("<data>") + 6 : user.index("</data>")])
    assert ctx["documents"][0]["ref"] == "D1" and "NOT evidence about this platform" in ctx["documents_note"]
    assert (
        "external_facts" in env.providers[0].seen[0][0].content
        and "NOT evidence that such an" in env.providers[0].seen[0][0].content
    )
    db_session.refresh(a)
    assert (a.severity, a.status, a.confidence) == before
    assert db_session.scalar(select(AIAnalysis).where(AIAnalysis.kind == "threat_correlation")) is not None


@pytest.mark.parametrize(
    ("mutation", "why"),
    [
        (
            {"verified_observations": [{"text": "x", "refs": ["D1"]}]},
            "document cited as a platform observation",
        ),
        ({"verified_observations": [{"text": "x", "refs": []}]}, "uncited verified observation"),
        ({"external_facts": [{"text": "x", "refs": ["E0"]}]}, "platform record cited as an external fact"),
        ({"external_facts": [{"text": "x", "refs": []}]}, "uncited external fact"),
    ],
)
def test_layer_violations_are_repaired_then_rejected(
    api: TestClient,
    env: Any,
    db_session: Session,
    mutation: dict[str, Any],
    why: str,
) -> None:
    a = world(db_session)
    add_doc(db_session)
    bad = json.dumps({**GOOD, **mutation})
    env.replies = [bad, json.dumps(GOOD)]
    assert correlate(api, a).status_code == 200, why  # first answer violated a layer rule, repair succeeded
    env.replies = [bad, bad, bad]  # correlation allows two repair attempts
    assert correlate(api, a).status_code == 502, why


def test_no_documents_means_no_external_facts(api: TestClient, env: Any, db_session: Session) -> None:
    a = world(db_session)  # world() adds an intel doc, but it does not match this anomaly's text
    db_session.query(ThreatIntelligence).delete()
    db_session.flush()
    env.replies = [
        json.dumps(GOOD),
        json.dumps(
            {
                **GOOD,
                "external_facts": [],
                "analytical_hypotheses": [{"text": "Genuine emergency.", "refs": ["E0"]}],
            }
        ),
    ]
    d = correlate(api, a).json()
    assert d["output"]["external_facts"] == [] and d["output"]["documents_supplied"] == []
    assert "no documents were supplied" in env.providers[0].seen[1][-1].content


def test_correlation_requires_analyst_and_valid_id(api: TestClient, env: Any, db_session: Session) -> None:
    a = world(db_session)
    url = "/api/v1/intelligence/threat-correlation"
    assert api.post(url, json={"anomaly_id": f"ANM-{a.id:04d}"}).status_code == 401
    assert api.post(url, json={"anomaly_id": f"ANM-{a.id:04d}"}, headers=V).status_code == 403
    assert api.post(url, json={"anomaly_id": "bad"}, headers=A).status_code == 422
    assert api.post(url, json={"anomaly_id": "ANM-999999"}, headers=A).status_code == 404


# ---- reports -------------------------------------------------------------------------------------------------
def make_report(api: TestClient, **body: Any) -> Any:
    return api.post("/api/v1/intelligence/reports", json=body, headers=A)


def test_report_without_ai_is_entirely_platform_data(api: TestClient, env: Any, db_session: Session) -> None:
    a = world(db_session)
    r = make_report(api, anomaly_id=f"ANM-{a.id:04d}")
    assert r.status_code == 201, r.text
    d = r.json()
    ids = [s["id"] for s in d["structured"]["sections"]]
    assert ids[:5] == ["executive_summary", "aircraft", "timeline", "anomalies", "evidence"] and ids[-2:] == [
        "limitations",
        "sources",
    ]
    assert {s["provenance"] for s in d["structured"]["sections"]} == {"VERIFIED_PLATFORM_DATA"}
    assert d["includes_ai"] is False and d["status"] == "UNREVIEWED" and "ai_analysis" not in ids
    m = d["markdown"]
    assert (
        "UNREVIEWED" in m
        and "not the probability of malicious activity" in m
        and "VERIFIED PLATFORM DATA" in m
    )
    assert (
        "AI-GENERATED" not in m.split("## ")[1] and "abc123" in m and "TST1" not in "AI"
    )  # facts present, no AI section
    assert "not available" in m  # unknown registration/type are stated, never invented
    assert "volunteer receivers" in m and "no accuracy claim" in m


def test_report_with_ai_requires_an_existing_analysis_and_labels_it(
    api: TestClient, env: Any, db_session: Session
) -> None:
    a = world(db_session)
    pid = f"ANM-{a.id:04d}"
    r = make_report(api, anomaly_id=pid, include_ai=True)
    assert r.status_code == 409 and "request one first" in r.json()["error"]["message"]
    env.replies = [
        json.dumps(
            {
                "what_happened": "Squawk 7700 was transmitted.",
                "rule_triggered": "DET-005",
                "supporting_evidence": [{"ref": "E0", "note": "first"}],
                "alternative_explanations": ["Crew training"],
                "why_it_may_matter": "General emergency code.",
                "next_steps": ["Check ATC records"],
                "limitations": ["One source"],
            }
        )
    ]
    assert (
        api.post("/api/v1/intelligence/anomaly-explanation", json={"anomaly_id": pid}, headers=A).status_code
        == 200
    )
    d = make_report(api, anomaly_id=pid, include_ai=True).json()
    secs = {s["id"]: s for s in d["structured"]["sections"]}
    assert d["includes_ai"] is True and secs["ai_analysis"]["provenance"] == "AI_GENERATED_UNVERIFIED"
    assert (
        secs["recommendations"]["provenance"] == "AI_GENERATED_UNVERIFIED"
        and secs["relevance_ai"]["provenance"] == "AI_GENERATED_UNVERIFIED"
    )
    assert secs["executive_summary"]["provenance"] == "VERIFIED_PLATFORM_DATA"  # AI never writes the summary
    assert "Check ATC records" not in json.dumps(secs["executive_summary"]) and "Crew training" in json.dumps(
        secs["alternatives_ai"]
    )
    assert "AI-GENERATED, UNVERIFIED" in d["markdown"] and "Unverified." in d["markdown"]
    row = db_session.get(IntelligenceReport, d["id"])
    assert row and row.ai_analysis_ids and db_session.get(AIAnalysis, row.ai_analysis_ids[0]) is not None
    srcs = json.dumps(secs["sources"])
    assert "AI: ollama/local-model" in srcs and "DET-005 v1.0.0" in srcs


def test_aircraft_report_and_request_validation(api: TestClient, env: Any, db_session: Session) -> None:
    world(db_session)
    d = make_report(api, icao24="ABC123").json()
    assert d["subject_type"] == "aircraft" and d["subject"] == "abc123"
    secs = {s["id"]: s for s in d["structured"]["sections"]}
    assert (
        "5 stored observations" in json.dumps(secs["executive_summary"])
        and secs["anomalies"]["blocks"][0]["type"] == "table"
    )
    assert any(
        "begins: Squawk 7700" in json.dumps(b) for b in secs["timeline"]["blocks"]
    )  # detection event on the timeline
    assert "not available" in json.dumps(
        secs["executive_summary"]
    )  # unknown first/last seen is stated, not invented
    for bad in ({}, {"anomaly_id": "ANM-1", "icao24": "abc123"}, {"icao24": "zz"}, {"anomaly_id": "x"}):
        assert make_report(api, **bad).status_code == 422, bad
    assert make_report(api, icao24="ffffff").status_code == 404
    assert make_report(api, icao24="abc123", include_ai=True).status_code == 409


def test_report_markdown_escapes_hostile_content(api: TestClient, env: Any, db_session: Session) -> None:
    a = world(db_session)
    a.title = "<script>alert(1)</script> | **bold** [x](javascript:alert(1))\nnew line"
    db_session.flush()
    m = make_report(api, anomaly_id=f"ANM-{a.id:04d}").json()["markdown"]
    assert (
        "<script>" not in m
        and "\\<script\\>" in m
        and "\\|" in m
        and "\\*\\*bold\\*\\*" in m
        and "\\[x\\]" in m
    )
    assert "\nnew line" not in m  # newlines cannot start new markdown blocks


def test_export_markdown_and_pdf(api: TestClient, env: Any, db_session: Session) -> None:
    a = world(db_session)
    a.title = "Squawk → 7700 中文 <b>x</b> & more"
    db_session.flush()
    rid = make_report(api, anomaly_id=f"ANM-{a.id:04d}").json()["id"]
    url = f"/api/v1/intelligence/reports/{rid}/export"
    m = api.get(url, headers=V)
    assert m.status_code == 200 and m.headers["content-type"].startswith("text/markdown")
    assert m.headers["content-disposition"] == f'attachment; filename="aerosecurity-report-{rid}.md"'
    assert m.headers["x-content-type-options"] == "nosniff" and m.headers["cache-control"] == "no-store"
    p = api.get(url, params={"format": "pdf"}, headers=V)
    assert (
        p.status_code == 200
        and p.headers["content-type"] == "application/pdf"
        and p.content.startswith(b"%PDF-")
    )
    assert len(p.content) > 2000 and p.content.rstrip().endswith(b"%%EOF")
    assert p.headers["content-disposition"].endswith(f'report-{rid}.pdf"')
    assert api.get(url, params={"format": "exe"}, headers=V).status_code == 422
    assert (
        api.get(url).status_code == 401
        and api.get("/api/v1/intelligence/reports/999999/export", headers=V).status_code == 404
    )
    acts = [
        x.details["format"]
        for x in db_session.scalars(select(AuditLog).where(AuditLog.action == "report.exported"))
        if x.details
    ]
    assert sorted(acts) == ["md", "pdf"]


def test_pdf_renderer_survives_hostile_and_non_latin_text() -> None:
    nasty = "<para>&amp; </b></para> → ≥ 中文 ‹/data› \x00"
    structured = {
        "title": nasty,
        "status": "UNREVIEWED",
        "notice": nasty,
        "generated_at": "x",
        "subject": {"type": "anomaly", "id": nasty},
        "sections": [
            {
                "id": "s",
                "title": nasty,
                "provenance": "AI_GENERATED_UNVERIFIED",
                "blocks": [
                    {"type": "paragraph", "text": nasty},
                    {"type": "bullets", "items": [nasty]},
                    {"type": "table", "columns": [nasty], "rows": [[nasty]]},
                ],
            }
        ],
    }
    out = pdf.render(structured, 1)
    assert out.startswith(b"%PDF-") and md.render(structured).startswith("# ")


def test_report_listing_access_and_audit(api: TestClient, env: Any, db_session: Session) -> None:
    a = world(db_session)
    pid = f"ANM-{a.id:04d}"
    assert api.post("/api/v1/intelligence/reports", json={"anomaly_id": pid}).status_code == 401
    assert api.post("/api/v1/intelligence/reports", json={"anomaly_id": pid}, headers=V).status_code == 403
    rid = make_report(api, anomaly_id=pid).json()["id"]
    listing = api.get("/api/v1/intelligence/reports", headers=V).json()
    assert (
        [r["id"] for r in listing] == [rid]
        and listing[0]["status"] == "UNREVIEWED"
        and "structured" not in listing[0]
    )
    assert api.get(f"/api/v1/intelligence/reports/{rid}", headers=V).json()["markdown"].startswith("# ")
    log = db_session.scalar(select(AuditLog).where(AuditLog.action == "report.generated"))
    assert log and log.details and log.details["subject"] == pid and log.actor.startswith("analyst:")
    assert api.get("/api/v1/intelligence/reports/abc", headers=V).status_code == 422 and ADM


def test_ungrounded_hypotheses_are_removed_not_fatal(api: TestClient, env: Any, db_session: Session) -> None:
    """Small local models often leave a hypothesis uncited. That layer degrades gracefully; the factual layers stay strict."""
    a = world(db_session)
    add_doc(db_session)
    mixed = {
        **GOOD,
        "analytical_hypotheses": [
            {"text": "Grounded guess.", "refs": ["E0"]},
            {"text": "Uncited guess.", "refs": []},
            {"text": "Invented source.", "refs": ["D9"]},
        ],
    }
    env.replies = [json.dumps(mixed)]
    r = correlate(api, a)
    assert r.status_code == 200, r.text
    out = r.json()["output"]
    assert [h["text"] for h in out["analytical_hypotheses"]] == ["Grounded guess."] and out[
        "removed_ungrounded_hypotheses"
    ] == 2
    assert any("2 AI hypothesis(es) were removed" in w for w in r.json()["warnings"])
    assert len(env.providers[0].seen) == 1  # no repair round-trip was needed for this


def test_model_cannot_set_the_removed_counter(api: TestClient, env: Any, db_session: Session) -> None:
    a = world(db_session)
    add_doc(db_session)
    env.replies = [json.dumps({**GOOD, "removed_ungrounded_hypotheses": 99})]
    assert correlate(api, a).json()["output"]["removed_ungrounded_hypotheses"] == 0  # server value wins


def test_omitted_optional_fields_default_instead_of_failing(
    api: TestClient, env: Any, db_session: Session
) -> None:
    a = world(db_session)
    add_doc(db_session)
    slim = {k: v for k, v in GOOD.items() if k not in ("gaps_and_limitations", "consistent_with_categories")}
    env.replies = [json.dumps(slim)]
    out = correlate(api, a).json()["output"]
    assert out["gaps_and_limitations"] == [] and out["consistent_with_categories"] == []
