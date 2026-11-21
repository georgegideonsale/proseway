"""Run a whole conversion for one book. Executed inside a separate worker process."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from .. import PIPELINE_VERSION
from ..anchoring import Anchor, BlockText, resolve
from ..db import Database, now
from ..paths import DataPaths
from . import errors, extract, layout
from . import ocr as ocr_mod

log = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


def _write_json_atomic(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _status(db: Database, book_id: str) -> str | None:
    with db.connect() as c:
        row = c.execute("SELECT status FROM books WHERE id=?", (book_id,)).fetchone()
    return row["status"] if row else None


def _update(db: Database, book_id: str, **fields) -> None:
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with db.connect() as c:
        c.execute(f"UPDATE books SET {cols} WHERE id=?", (*fields.values(), book_id))  # noqa: S608


def run_conversion(db_path: str, data_root: str, book_id: str, skip_pages: list[int] | None = None) -> None:
    db = Database(Path(db_path))
    paths = DataPaths(Path(data_root))
    pdf_path = paths.original_pdf(book_id)
    pages_dir = paths.pages_dir(book_id)
    assets_dir = paths.assets_dir(book_id)
    pages_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    skip = set(skip_pages or [])

    try:
        # Only start if nobody pressed Stop while this process was starting up.
        with db.connect() as c:
            started_ok = c.execute(
                "UPDATE books SET status='converting', error=NULL, updated_at=? WHERE id=? AND status != 'cancelled'",
                (now(), book_id),
            ).rowcount
        if not started_ok:
            return
        meta = extract.read_metadata(pdf_path)
        src = extract.Source(pdf_path)
        n_pages = len(src)
        with db.connect() as c:
            row = c.execute("SELECT title, author FROM books WHERE id=?", (book_id,)).fetchone()
        updates = {"page_count": n_pages}
        if meta["title"] and len(meta["title"]) > 2 and row and row["title"].endswith(".pdf"):
            updates["title"] = meta["title"][:300]
        if meta["author"] and row and not row["author"]:
            updates["author"] = meta["author"][:200]
        _update(db, book_id, **updates)
        cover = paths.book_dir(book_id) / "cover.jpg"
        if not cover.exists() and extract.render_cover(pdf_path, cover):
            _update(db, book_id, has_cover=1)

        ocr_engine = None
        try:
            started = time.monotonic()
            for i in range(n_pages):
                out = pages_dir / f"{i + 1:05d}.json"
                if not out.exists():
                    if (i + 1) in skip:
                        data = {"n": i + 1, "w": 612, "h": 792, "lines": [], "images": [], "tables": [],
                                "scanned": False, "ocr": False, "failed": True}
                    else:
                        data = extract.extract_page(src, i, assets_dir, ocr=ocr_engine)
                        if data.get("scanned") and not data.get("ocr") and ocr_engine is None and ocr_mod.available():
                            ocr_engine = ocr_mod.get_engine()
                            if ocr_engine is not None:
                                data = extract.extract_page(src, i, assets_dir, ocr=ocr_engine)
                    _write_json_atomic(out, data)
                # Progress after every page: the watchdog uses it to know exactly which page
                # is stuck, and the library shows it.
                if _status(db, book_id) == "cancelled":
                    raise Cancelled()
                _update(db, book_id, pages_done=i + 1)
            log.info("extracted %d pages in %.1fs", n_pages, time.monotonic() - started)

            pages = []
            for i in range(n_pages):
                pages.append(json.loads((pages_dir / f"{i + 1:05d}.json").read_text(encoding="utf-8")))
            result = layout.assemble(pages, meta.get("outline"))
            rows = [layout.block_to_row(b) for b in result["blocks"]]
            _render_equations(src.pdfium, rows, pages, assets_dir)
        finally:
            src.close()

        # No usable title in the PDF metadata: use the first prominent heading on page 1-2.
        with db.connect() as c:
            current = c.execute("SELECT title FROM books WHERE id=?", (book_id,)).fetchone()["title"]
        if current.endswith(".pdf"):
            first = next((r for r in rows if r["type"] == "heading" and r["page"] <= 2
                          and 4 <= len(r["text"]) <= 200), None)
            if first is not None:
                _update(db, book_id, title=" ".join(first["text"].split())[:300])

        _store(db, book_id, rows, result)
        _update(db, book_id, status="ready", pipeline_version=PIPELINE_VERSION, pages_done=n_pages,
                word_count=result["stats"]["words"], toc_json=json.dumps(result["toc"], ensure_ascii=False),
                stats_json=json.dumps(result["stats"]))
    except Cancelled:
        _update(db, book_id, status="cancelled")
    except errors.ConversionError as exc:
        _update(db, book_id, status="error", error=json.dumps({"code": exc.code, "message": exc.message}))
    except Exception as exc:
        log.exception("conversion failed")
        _update(db, book_id, status="error", error=json.dumps({
            "code": "internal",
            "message": f"Something went wrong while converting this book ({type(exc).__name__}). "
                       "You can try again; if it keeps failing, please report it.",
        }))


def _render_equations(pdfium_doc, rows: list[dict], pages: list[dict], assets_dir: Path) -> None:
    by_n = {p["n"]: p for p in pages}
    for r in rows:
        if r["type"] != "equation" or "bbox" not in r["data"]:
            continue
        p = by_n.get(r["page"])
        if p is None:
            continue
        x0, top, x1, bot = r["data"].pop("bbox")
        pad = 3.0
        name = f"eq-{r['id']}.png"
        if extract._render_crop(pdfium_doc, r["page"] - 1, (x0 - pad, top - pad, x1 + pad, bot + pad),
                                p["w"], p["h"], assets_dir / name, scale=3.0, fmt="PNG"):
            r["data"]["src"] = name


def _store(db: Database, book_id: str, rows: list[dict], result: dict) -> None:
    with db.transaction() as c:
        old = c.execute("SELECT COUNT(*) AS n FROM blocks WHERE book_id=?", (book_id,)).fetchone()["n"]
        c.execute("DELETE FROM blocks WHERE book_id=?", (book_id,))
        c.execute("DELETE FROM blocks_fts WHERE book_id=?", (book_id,))
        c.executemany(
            "INSERT INTO blocks(book_id, seq, id, chapter, type, page, level, text, data_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(book_id, i, r["id"], r["chapter"], r["type"], r["page"], r["level"], r["text"],
              json.dumps(r["data"], ensure_ascii=False)) for i, r in enumerate(rows)],
        )
        c.executemany(
            "INSERT INTO blocks_fts(text, book_id, block_id) VALUES (?,?,?)",
            # Text drawn inside a figure is searchable and leads to the figure.
            [(r["text"] or r["data"].get("figure_text", ""), book_id, r["id"])
             for r in rows if r["text"] or r["data"].get("figure_text")],
        )
        # Re-anchor existing annotations against the new blocks (re-conversion or restore).
        anns = c.execute("SELECT * FROM annotations WHERE book_id=?", (book_id,)).fetchall()
        if anns:
            texts = [BlockText(r["id"], r["text"], r["page"], i) for i, r in enumerate(rows)]
            for a in anns:
                res = resolve(Anchor(a["block_id"], a["start"], a["end"], a["exact"], a["prefix"], a["suffix"]),
                              texts, a["page"])
                c.execute(
                    "UPDATE annotations SET block_id=?, start=?, end=?, seq=?, page=?, orphaned=? WHERE id=?",
                    (res.block_id or a["block_id"], res.start, res.end, res.seq,
                     res.page if res.page is not None else a["page"],
                     1 if res.method == "orphaned" else 0, a["id"]),
                )
        # Keep the reading position too: same block if it still exists, else the same place.
        pos = c.execute("SELECT block_id, seq FROM positions WHERE book_id=?", (book_id,)).fetchone()
        if pos is not None and rows and not any(r["id"] == pos["block_id"] for r in rows):
            target = rows[min(max(pos["seq"], 0), len(rows) - 1)]
            c.execute("UPDATE positions SET block_id=?, seq=? WHERE book_id=?",
                      (target["id"], min(max(pos["seq"], 0), len(rows) - 1), book_id))
        log.info("stored %d blocks (replaced %d), re-anchored %d annotations", len(rows), old, len(anns))


def worker_main(db_path: str, data_root: str, book_id: str, skip_pages: list[int] | None = None) -> None:
    """Entry point for the converter process."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s convert %(levelname)s %(message)s")
    try:
        os.nice(5)  # type: ignore[attr-defined]  # be gentle with the reader UI (POSIX)
    except Exception:  # noqa: S110
        pass
    run_conversion(db_path, data_root, book_id, skip_pages)
