"""Markdown rendering of a structured report. Content is escaped so untrusted text cannot inject formatting."""

import re
from typing import Any

_TAGS = {
    "VERIFIED_PLATFORM_DATA": "VERIFIED PLATFORM DATA",
    "AI_GENERATED_UNVERIFIED": "AI-GENERATED, UNVERIFIED",
}
_MD = re.compile(r"([\\`*_{}\[\]<>#|])")


def esc(text: object) -> str:
    return _MD.sub(r"\\\1", str(text)).replace("\r", " ").replace("\n", " ")


def render(r: dict[str, Any]) -> str:
    out = [
        f"# {esc(r['title'])}",
        "",
        f"> **{esc(r['status'])}.** {esc(r['notice'])}",
        "",
        f"Generated: {esc(r['generated_at'])}  ",
        f"Subject: {esc(r['subject']['type'])} {esc(r['subject']['id'])}",
        "",
    ]
    for s in r["sections"]:
        out += [
            f"## {esc(s['title'])}",
            "",
            f"*Provenance: {_TAGS.get(s['provenance'], esc(s['provenance']))}*",
            "",
        ]
        for b in s["blocks"]:
            if b["type"] == "paragraph":
                out += [esc(b["text"]), ""]
            elif b["type"] == "bullets":
                out += [f"- {esc(i)}" for i in b["items"]] + [""]
            elif b["type"] == "table":
                out += [
                    "| " + " | ".join(esc(c) for c in b["columns"]) + " |",
                    "|" + "---|" * len(b["columns"]),
                ]
                out += ["| " + " | ".join(esc(c) for c in row) + " |" for row in b["rows"]] + [""]
    return "\n".join(out)
