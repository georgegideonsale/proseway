"""Server-side HTML rendering of blocks (used for EPUB export). Everything is escaped."""

from __future__ import annotations

import re
from html import escape as _escape
from typing import Any

# Characters that are not allowed in XML 1.0 at all (C0 controls except tab/newline/CR,
# lone surrogates, U+FFFE/U+FFFF). One of these makes a whole EPUB chapter unreadable.
_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def xml_safe(text: str) -> str:
    return _XML_INVALID.sub("", text)


def escape(text: str, quote: bool = True) -> str:
    return _escape(xml_safe(str(text)), quote=quote)


def inline_html(text: str, spans: list[list[Any]], link_for=None) -> str:
    """Render block text with inline spans (sup, i, fnref). Spans don't overlap by construction."""
    spans = sorted((s for s in spans if 0 <= s[0] < s[1] <= len(text)), key=lambda s: s[0])
    out: list[str] = []
    pos = 0
    for span in spans:
        start, end, kind = span[0], span[1], span[2]
        if start < pos:
            continue
        out.append(escape(text[pos:start]))
        inner = escape(text[start:end])
        if kind == "sup":
            out.append(f"<sup>{inner}</sup>")
        elif kind == "i":
            out.append(f"<i>{inner}</i>")
        elif kind == "fnref" and len(span) > 3:
            href = link_for(span[3]) if link_for else f"#{span[3]}"
            out.append(f'<sup><a epub:type="noteref" href="{escape(href)}">{inner}</a></sup>')
        else:
            out.append(inner)
        pos = end
    out.append(escape(text[pos:]))
    return "".join(out)


def block_html(b: dict[str, Any], asset_url, link_for=None) -> str:
    t = b["type"]
    data = b.get("data") or {}
    bid = escape(b["id"])
    body = inline_html(b["text"], data.get("spans", []), link_for)
    page = f' data-page="{b["page"]}"'
    if t == "heading":
        level = min(max(int(b.get("level") or 1), 1), 4) + 1  # h1 is the book title
        return f'<h{level} id="{bid}"{page}>{body}</h{level}>'
    if t == "footnote":
        return f'<aside epub:type="footnote" id="{bid}" class="footnote"{page}><p>{body}</p></aside>'
    if t == "list_item":
        return f'<p id="{bid}" class="li"{page}>{body}</p>'
    if t == "code":
        return f'<pre id="{bid}"{page}><code>{escape(b["text"])}</code></pre>'
    if t == "caption":
        return f'<p id="{bid}" class="caption"{page}>{body}</p>'
    if t == "equation":
        if data.get("src"):
            return (f'<div id="{bid}" class="equation"{page}><img src="{escape(asset_url(data["src"]))}" '
                    f'alt="{escape(b["text"])}"/></div>')
        return f'<p id="{bid}" class="equation"{page}>{body}</p>'
    if t in ("figure", "page_image"):
        alt = "Scanned page" if t == "page_image" else "Figure"
        return (f'<figure id="{bid}"{page}><img src="{escape(asset_url(data["src"]))}" alt="{alt} on page '
                f'{b["page"]}"/></figure>')
    if t == "table":
        rows = data.get("rows") or []
        trs = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
        return f'<table id="{bid}"{page}>{trs}</table>'
    return f'<p id="{bid}"{page}>{body}</p>'
