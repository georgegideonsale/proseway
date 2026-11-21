"""EPUB 3 export, written from scratch (EbookLib is AGPL, so we don't use it).

The EPUB contains the converted text, figures and equation images, a navigation document
built from the table of contents, and page-number markers so citations still work.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

from . import __version__
from .db import Database
from .paths import DataPaths
from .render import block_html, escape

CSS = """
body { font-family: serif; line-height: 1.5; margin: 0 4%; }
h2, h3, h4, h5 { font-family: sans-serif; line-height: 1.25; margin: 1.6em 0 0.6em; }
p { margin: 0 0 0.8em; text-align: left; }
p.li { padding-left: 1.4em; text-indent: -1.4em; }
p.caption { font-size: 0.9em; font-style: italic; }
aside.footnote { font-size: 0.85em; border-top: 1px solid #ccc; margin-top: 0.6em; padding-top: 0.3em; }
pre { font-size: 0.85em; white-space: pre-wrap; }
figure { margin: 1em 0; text-align: center; }
img { max-width: 100%; }
.equation { text-align: center; margin: 0.8em 0; }
table { border-collapse: collapse; font-size: 0.9em; margin: 1em 0; }
td { border: 1px solid #bbb; padding: 0.2em 0.4em; vertical-align: top; }
span.pagebreak { display: none; }
"""


def build_epub(db: Database, paths: DataPaths, book_id: str) -> bytes:
    with db.connect() as c:
        book = c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        rows = c.execute("SELECT * FROM blocks WHERE book_id=? ORDER BY seq", (book_id,)).fetchall()
    title = book["title"][:-4] if book["title"].endswith(".pdf") else book["title"]
    toc = json.loads(book["toc_json"] or "[]")
    blocks = [{"id": r["id"], "type": r["type"], "page": r["page"], "level": r["level"], "text": r["text"],
               "chapter": r["chapter"], "data": json.loads(r["data_json"])} for r in rows]
    chapter_of = {b["id"]: b["chapter"] for b in blocks}
    chapters: dict[int, list[dict]] = {}
    for b in blocks:
        chapters.setdefault(b["chapter"], []).append(b)

    def fname(ch: int) -> str:
        return f"ch{ch:04d}.xhtml"

    def link_for(target: str) -> str:
        return f"{fname(chapter_of.get(target, 0))}#{target}"

    assets: set[str] = set()

    def asset_url(name: str) -> str:
        assets.add(name)
        return f"images/{name}"

    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml",
               '<?xml version="1.0" encoding="UTF-8"?>\n<container version="1.0" '
               'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile '
               'full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    z.writestr("OEBPS/style.css", CSS)

    spine = []
    marked_pages: set[int] = set()
    for ch, items in sorted(chapters.items()):
        parts = []
        for b in items:
            # One marker per original page, at its first block (footnotes can repeat a page).
            if b["page"] not in marked_pages:
                marked_pages.add(b["page"])
                parts.append(f'<span epub:type="pagebreak" role="doc-pagebreak" id="page{b["page"]}" '
                             f'title="{b["page"]}" class="pagebreak"></span>')
            parts.append(block_html(b, asset_url, link_for))
        doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
               '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
               f'<head><meta charset="utf-8"/><title>{escape(title)}</title>'
               '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
               + "\n".join(parts) + "</body></html>")
        z.writestr(f"OEBPS/{fname(ch)}", doc)
        spine.append(fname(ch))

    nav_items = "".join(
        f'<li><a href="{link_for(t["block"])}">{escape(t["title"][:200])}</a></li>'
        for t in toc if t.get("level", 1) <= 2 and t.get("block") in chapter_of
    ) or "".join(f'<li><a href="{f}">Part {i + 1}</a></li>' for i, f in enumerate(spine))
    z.writestr("OEBPS/nav.xhtml",
               '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" '
               'xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>Contents</title></head>'
               f'<body><nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{nav_items}</ol></nav></body></html>')

    assets_dir = paths.assets_dir(book_id)
    manifest_imgs = []
    for i, name in enumerate(sorted(assets)):
        f = assets_dir / name
        if f.is_file():
            z.write(f, f"OEBPS/images/{name}")
            media = "image/png" if name.endswith(".png") else "image/jpeg"
            manifest_imgs.append(f'<item id="img{i}" href="images/{escape(name)}" media-type="{media}"/>')

    uid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'proseway:' + book['sha256'])}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = "".join(f'<item id="c{i}" href="{f}" media-type="application/xhtml+xml"/>' for i, f in enumerate(spine))
    refs = "".join(f'<itemref idref="c{i}"/>' for i in range(len(spine)))
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="uid">{uid}</dc:identifier><dc:title>{escape(title)}</dc:title>'
        f'<dc:creator>{escape(book["author"] or "Unknown")}</dc:creator><dc:language>en</dc:language>'
        f'<meta property="dcterms:modified">{modified}</meta>'
        f'<meta name="generator" content="Proseway {__version__}"/></metadata><manifest>'
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="css" href="style.css" media-type="text/css"/>'
        f'{items}{"".join(manifest_imgs)}</manifest><spine>{refs}</spine></package>'
    )
    z.writestr("OEBPS/content.opf", opf)
    z.close()
    return buf.getvalue()
