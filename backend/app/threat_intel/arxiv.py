"""arXiv connector. Uses arXiv's documented public API (https://info.arxiv.org/help/api/); abstracts only.
No websites are scraped. The response is untrusted input and is parsed with defusedxml."""

import re
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from defusedxml import ElementTree

API = "https://export.arxiv.org/api/query"
USER_AGENT = "AeroSecurity-AI-research/0.1 (documented API use, one request per import)"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_NS = {"a": "http://www.w3.org/2005/Atom"}
_WS = re.compile(r"\s+")
QUERY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-+]{1,99}$")

RELIABILITY = (
    "Academic preprint hosted on arXiv: not necessarily peer reviewed. "
    "Only the abstract is stored, so detail and caveats in the full paper are not represented. "
    "It describes research or lab/simulated attacks; it is not evidence that any incident "
    "occurred in this platform's data."
)


class ArxivError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ArxivEntry:
    url: str
    title: str
    authors: str
    published: date | None
    abstract: str


def _clean(s: str | None, limit: int) -> str:
    return _WS.sub(" ", s or "").strip()[:limit]


def parse_feed(xml_bytes: bytes) -> list[ArxivEntry]:
    try:
        root = ElementTree.fromstring(xml_bytes)  # defusedxml: rejects entity expansion / external entities
    except Exception as exc:  # defusedxml raises several parser-specific types
        raise ArxivError(f"unparseable arXiv response ({type(exc).__name__})") from exc
    out: list[ArxivEntry] = []
    for e in root.findall("a:entry", _NS):
        raw_id = (e.findtext("a:id", default="", namespaces=_NS) or "").strip()
        m = re.match(r"^https?://arxiv\.org/abs/([A-Za-z0-9.\-/]+?)(?:v\d+)?$", raw_id)
        if not m:
            continue  # ignore anything that is not a recognisable arXiv abstract URL
        names = [
            _clean(a.findtext("a:name", default="", namespaces=_NS), 80) for a in e.findall("a:author", _NS)
        ]
        authors = ", ".join(names[:6]) + (" et al." if len(names) > 6 else "")
        pub = (e.findtext("a:published", default="", namespaces=_NS) or "")[:10]
        try:
            published: date | None = datetime.strptime(pub, "%Y-%m-%d").date()
        except ValueError:
            published = None
        title = _clean(e.findtext("a:title", default="", namespaces=_NS), 300)
        abstract = _clean(e.findtext("a:summary", default="", namespaces=_NS), 3900)
        if title and abstract:
            out.append(ArxivEntry(f"https://arxiv.org/abs/{m.group(1)}", title, authors, published, abstract))
    return out


def search(query: str, max_results: int, client: httpx.Client | None = None) -> list[ArxivEntry]:
    if not QUERY_RE.match(query):
        raise ArxivError("query may contain letters, digits, space, '.', '-', '+' (2-100 chars)")
    terms = " AND ".join(f"all:{w}" for w in query.split()[:8])
    c = client or httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
    try:
        r = c.get(
            API, params={"search_query": terms, "max_results": min(max_results, 10), "sortBy": "relevance"}
        )
    except httpx.HTTPError as exc:
        raise ArxivError("arXiv is unreachable") from exc
    if r.status_code != 200:
        raise ArxivError(f"arXiv returned HTTP {r.status_code}")
    if len(r.content) > MAX_RESPONSE_BYTES:
        raise ArxivError("arXiv response too large")
    return parse_feed(r.content)
