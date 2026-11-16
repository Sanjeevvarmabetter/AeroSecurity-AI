"""Threat-intel connector (offline: synthetic Atom XML) and store/API (PostGIS)."""

import os
from collections.abc import Iterator
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import Principal, Role
from app.main import app
from app.models import AuditLog, ThreatIntelligence
from app.threat_intel import arxiv
from app.threat_intel import service as intel

V = {"Authorization": "Bearer test-viewer-token"}
A = {"Authorization": "Bearer test-analyst-token"}
FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/abs/2204.01994v1</id><published>2022-04-05T10:00:00Z</published>
    <title>  Towards   Security-Optimized
      Placement of ADS-B Sensors </title><summary>  An abstract
      about sensors.  </summary>
    <author><name>A One</name></author><author><name>B Two</name></author></entry>
  <entry><id>http://evil.example/abs/1</id><published>2020-01-01T00:00:00Z</published><title>Not arXiv</title><summary>x</summary></entry>
  <entry><id>http://arxiv.org/abs/1907.04909v2</id><published>garbage</published><title>No date paper</title><summary>abc</summary>
    <author><name>1</name></author><author><name>2</name></author><author><name>3</name></author><author><name>4</name></author>
    <author><name>5</name></author><author><name>6</name></author><author><name>7</name></author></entry>
  <entry><id>http://arxiv.org/abs/1111.1111v1</id><published>2020-01-01T00:00:00Z</published><title></title><summary>empty title</summary></entry>
</feed>"""


# ---- connector (no DB) --------------------------------------------------------------------------------
def test_feed_parsing_normalises_and_ignores_unrecognised_entries() -> None:
    entries = arxiv.parse_feed(FEED)
    assert [e.url for e in entries] == [
        "https://arxiv.org/abs/2204.01994",
        "https://arxiv.org/abs/1907.04909",
    ]
    a, b = entries
    assert (
        a.title == "Towards Security-Optimized Placement of ADS-B Sensors"
        and a.abstract == "An abstract about sensors."
    )
    assert a.authors == "A One, B Two" and a.published == date(2022, 4, 5)
    assert b.published is None and b.authors.endswith("et al.") and b.authors.count(",") == 5


def test_untrusted_lengths_are_capped() -> None:
    big = FEED.replace(b"An abstract", b"X" * 9000)
    assert len(arxiv.parse_feed(big)[0].abstract) <= 3900


BILLION_LAUGHS = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">
<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;">]><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>&lol3;</title></entry></feed>"""
XXE = b"""<?xml version="1.0"?><!DOCTYPE f [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1.1</id><title>&x;</title><summary>s</summary></entry></feed>"""


@pytest.mark.parametrize("payload", [BILLION_LAUGHS, XXE, b"<not-xml", b""])
def test_hostile_or_broken_xml_is_rejected(payload: bytes) -> None:
    with pytest.raises(arxiv.ArxivError):
        arxiv.parse_feed(payload)


def client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_search_builds_a_safe_query_and_maps_failures() -> None:
    seen: dict[str, str] = {}

    def ok(r: httpx.Request) -> httpx.Response:
        seen.update(r.url.params)
        return httpx.Response(200, content=FEED)

    assert len(arxiv.search("ADS-B security", 50, client(httpx.MockTransport(ok)))) == 2
    assert seen["search_query"] == "all:ADS-B AND all:security" and seen["max_results"] == "10"  # capped
    for bad in ("", "a", "x; rm -rf /", "all:foo OR ti:bar'", "a" * 101):
        with pytest.raises(arxiv.ArxivError, match="query"):
            arxiv.search(bad, 5, client(httpx.MockTransport(ok)))
    with pytest.raises(arxiv.ArxivError, match="HTTP 503"):
        arxiv.search("ADS-B", 5, client(httpx.MockTransport(lambda r: httpx.Response(503))))

    def down(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=r)

    with pytest.raises(arxiv.ArxivError, match="unreachable"):
        arxiv.search("ADS-B", 5, client(httpx.MockTransport(down)))
    with pytest.raises(arxiv.ArxivError, match="too large"):
        arxiv.search(
            "ADS-B",
            5,
            client(httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * (3 * 1024 * 1024)))),
        )


@pytest.mark.skipif(
    not os.environ.get("RUN_NETWORK_TESTS"), reason="set RUN_NETWORK_TESTS=1 to call the real arXiv API"
)
def test_real_arxiv_api() -> None:
    entries = arxiv.search("ADS-B security", 3)
    assert entries and all(
        e.url.startswith("https://arxiv.org/abs/") and e.title and e.abstract for e in entries
    )


# ---- store and API --------------------------------------------------------------------------------------------
pytestmark_db = pytest.mark.integration


@pytest.fixture
def api(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


GOOD = {
    "source_name": "Example Journal",
    "source_url": "https://example.org/paper/1",
    "title": "A study of ADS-B anomalies",
    "authors": "A. Author",
    "publication_date": "2021-05-01T00:00:00Z",
    "excerpt": "Summary of how ADS-B anomalies and spoofing attacks were characterised in field data.",
    "reliability_notes": "Peer-reviewed; small sample; lab conditions.",
    "tags": ["ADS-B", "Spoofing", "bad tag!!", "x" * 50],
}


@pytest.mark.integration
def test_manual_registration_requires_provenance_and_valid_input(
    api: TestClient, db_session: Session
) -> None:
    assert api.post("/api/v1/threat-intel", json=GOOD).status_code == 401
    assert api.post("/api/v1/threat-intel", json=GOOD, headers=V).status_code == 403
    r = api.post("/api/v1/threat-intel", json=GOOD, headers=A)
    assert r.status_code == 201
    d = r.json()
    assert (
        d["origin"] == "manual"
        and d["publication_date"] == "2021-05-01"
        and d["retrieved_at"]
        and d["added_by"].startswith("analyst:")
    )
    assert (
        d["tags"] == ["adsb"[:0] + "ads-b", "spoofing"] and d["reliability_notes"]
    )  # invalid tags dropped, lower-cased
    assert api.post("/api/v1/threat-intel", json=GOOD, headers=A).status_code == 422  # duplicate URL
    for patch in (
        {"source_url": "http://insecure.example/x"},
        {"source_url": "javascript:alert(1)"},
        {"source_url": "https://a b/c"},
        {"source_url": "https://x.example/<script>"},
        {"reliability_notes": ""},
        {"reliability_notes": "short"},
        {"excerpt": "too short"},
        {"excerpt": "x" * 4001},
        {"title": "ab"},
        {"source_name": ""},
    ):
        assert (
            api.post(
                "/api/v1/threat-intel",
                json={**GOOD, "source_url": "https://example.org/other", **patch},
                headers=A,
            ).status_code
            == 422
        ), patch
    log = db_session.scalar(select(AuditLog).where(AuditLog.action == "intel.added"))
    assert log and log.details and log.details["origin"] == "manual"


@pytest.mark.integration
def test_search_listing_and_detail(api: TestClient, db_session: Session) -> None:
    api.post("/api/v1/threat-intel", json=GOOD, headers=A)
    api.post(
        "/api/v1/threat-intel",
        json={
            **GOOD,
            "source_url": "https://example.org/paper/2",
            "title": "Weather radar notes",
            "excerpt": "Nothing about aviation security here, only meteorological radar calibration notes.",
            "publication_date": None,
        },
        headers=A,
    )
    allr = api.get("/api/v1/threat-intel", headers=V).json()
    assert (
        allr["total"] == 2 and allr["items"][0]["publication_date"] == "2021-05-01"
    )  # dated first, undated last
    hit = api.get("/api/v1/threat-intel", params={"q": "spoofing attacks"}, headers=V).json()
    assert [i["title"] for i in hit["items"]] == ["A study of ADS-B anomalies"]
    assert (
        api.get(
            "/api/v1/threat-intel", params={"q": "'; DROP TABLE threat_intelligence;--"}, headers=V
        ).status_code
        == 200
    )
    assert api.get("/api/v1/threat-intel", headers=V).json()["total"] == 2  # table intact
    item = hit["items"][0]
    assert api.get(f"/api/v1/threat-intel/{item['id']}", headers=V).json()["source_url"] == GOOD["source_url"]
    assert api.get("/api/v1/threat-intel/999999", headers=V).status_code == 404
    assert api.get("/api/v1/threat-intel/abc", headers=V).status_code == 422


@pytest.mark.integration
def test_arxiv_import_is_idempotent_and_audited(
    api: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries = arxiv.parse_feed(FEED)
    monkeypatch.setattr(arxiv, "search", lambda q, n, client=None: entries)
    who = Principal(Role.ANALYST, "abcd1234")
    assert intel.import_arxiv(db_session, who, "ADS-B security", 5) == {
        "found": 2,
        "added": 2,
        "skipped_existing": 0,
    }
    assert intel.import_arxiv(db_session, who, "ADS-B security", 5) == {
        "found": 2,
        "added": 0,
        "skipped_existing": 2,
    }
    row = db_session.scalar(
        select(ThreatIntelligence).where(ThreatIntelligence.source_url == "https://arxiv.org/abs/2204.01994")
    )
    assert (
        row
        and row.origin == "arxiv"
        and row.source_name == "arXiv"
        and "not necessarily peer reviewed" in row.reliability_notes
    )
    assert "not evidence that any incident" in row.reliability_notes and row.added_by == "analyst:abcd1234"
    r = api.post(
        "/api/v1/threat-intel/import/arxiv", json={"query": "ADS-B security", "max_results": 5}, headers=A
    )
    assert r.status_code == 200 and r.json()["added"] == 0
    assert (
        api.post(
            "/api/v1/threat-intel/import/arxiv", json={"query": "x; rm", "max_results": 5}, headers=A
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/threat-intel/import/arxiv", json={"query": "ADS-B", "max_results": 99}, headers=A
        ).status_code
        == 422
    )
    assert (
        api.post("/api/v1/threat-intel/import/arxiv", json={"query": "ADS-B"}, headers=V).status_code == 403
    )


@pytest.mark.integration
def test_arxiv_outage_is_a_clean_502(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(q: str, n: int, client: object = None) -> list[arxiv.ArxivEntry]:
        raise arxiv.ArxivError("arXiv is unreachable")

    monkeypatch.setattr(arxiv, "search", boom)
    r = api.post("/api/v1/threat-intel/import/arxiv", json={"query": "ADS-B"}, headers=A)
    assert r.status_code == 502 and "unreachable" in r.json()["error"]["message"]
