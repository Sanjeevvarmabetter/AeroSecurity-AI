"""PDF rendering with ReportLab (pure Python). All text is XML-escaped (ReportLab paragraphs parse mini-markup)
and reduced to Latin-1 because the built-in fonts cover nothing wider."""

import io
from html import escape
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_MAP = {
    "→": "->",
    "≥": ">=",
    "≤": "<=",
    "‹": "<",
    "›": ">",
    "—": "-",
    "–": "-",
    "·": "-",
    "…": "...",
    "’": "'",
    "“": '"',
    "”": '"',
    "±": "+/-",
}
_TAGS = {
    "VERIFIED_PLATFORM_DATA": "VERIFIED PLATFORM DATA",
    "AI_GENERATED_UNVERIFIED": "AI-GENERATED - UNVERIFIED",
}


def _t(x: object) -> str:
    s = str(x)
    for k, v in _MAP.items():
        s = s.replace(k, v)
    return escape(s.encode("latin-1", "replace").decode("latin-1"), quote=False)


def render(r: dict[str, Any], report_id: int) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=_t(r["title"])[:200],
        author="AeroSecurity AI",
    )
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
    cell = ParagraphStyle("c", parent=body, fontSize=8, leading=10)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=2)
    tag = ParagraphStyle("t", parent=body, fontSize=7.5, textColor=colors.grey)
    banner = ParagraphStyle(
        "n",
        parent=body,
        backColor=colors.HexColor("#fff3cd"),
        borderColor=colors.HexColor("#c9a227"),
        borderWidth=0.6,
        borderPadding=5,
        fontSize=8.5,
    )
    story: list[Any] = [
        Paragraph(_t(r["title"]), ss["Title"]),
        Spacer(1, 3),
        Paragraph(f"<b>{_t(r['status'])}.</b> {_t(r['notice'])}", banner),
        Spacer(1, 4),
        Paragraph(
            f"Generated {_t(r['generated_at'])} | subject {_t(r['subject']['type'])} {_t(r['subject']['id'])}",
            tag,
        ),
    ]
    for s in r["sections"]:
        story += [
            Paragraph(_t(s["title"]), h2),
            Paragraph(f"Provenance: {_TAGS.get(s['provenance'], _t(s['provenance']))}", tag),
        ]
        for b in s["blocks"]:
            if b["type"] == "paragraph":
                story.append(Paragraph(_t(b["text"]), body))
            elif b["type"] == "bullets":
                story += [Paragraph(f"- {_t(i)}", body) for i in b["items"]]
            elif b["type"] == "table":
                data = [[Paragraph(f"<b>{_t(c)}</b>", cell) for c in b["columns"]]] + [
                    [Paragraph(_t(c), cell) for c in row] for row in b["rows"]
                ]
                t = Table(data, repeatRows=1, hAlign="LEFT")
                t.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef9")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                story += [t, Spacer(1, 3)]

    def footer(c: Any, d: Any) -> None:
        c.saveState()
        c.setFont("Helvetica", 7)
        c.drawString(18 * mm, 9 * mm, f"AeroSecurity AI - report #{report_id} - UNREVIEWED")
        c.drawRightString(A4[0] - 18 * mm, 9 * mm, f"page {d.page}")
        c.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
