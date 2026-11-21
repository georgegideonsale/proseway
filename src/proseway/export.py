"""Exporting highlights and notes (Markdown) and full backups (JSON) with restore."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from . import __version__
from .anchoring import Anchor, BlockText, resolve
from .db import Database
from .library import ANNOTATION_COLUMNS
from .paths import DataPaths

BACKUP_FORMAT = "proseway-backup"
BACKUP_VERSION = 1
COLOR_NAMES = {"yellow": "Yellow", "green": "Green", "blue": "Blue", "pink": "Pink", "purple": "Purple"}


def _chapter_titles(toc: list[dict]) -> dict[int, str]:
    titles: dict[int, str] = {}
    for entry in toc:
        ch = entry.get("chapter")
        if ch is not None and ch not in titles:
            titles[ch] = entry["title"]
    return titles


def markdown_for_book(db: Database, book_id: str) -> str:
    with db.connect() as c:
        book = c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if book is None:
            raise KeyError(book_id)
        anns = c.execute(
            "SELECT a.*, b.chapter AS chapter FROM annotations a "
            "LEFT JOIN blocks b ON b.book_id=a.book_id AND b.id=a.block_id "
            "WHERE a.book_id=? ORDER BY COALESCE(a.seq, 0), a.start", (book_id,)
        ).fetchall()
    toc = json.loads(book["toc_json"] or "[]")
    titles = _chapter_titles(toc)
    title = book["title"][:-4] if book["title"].endswith(".pdf") else book["title"]
    highlights = [a for a in anns if a["kind"] == "highlight"]
    bookmarks = [a for a in anns if a["kind"] == "bookmark"]
    groups: dict[str, list[Any]] = {}
    for a in highlights:
        groups.setdefault(a["group_id"] or a["id"], []).append(a)

    out = [f"# {title}", ""]
    if book["author"]:
        out += [f"*{book['author']}*", ""]
    n_notes = sum(1 for g in groups.values() if any(x["note"] for x in g))
    today = dt.date.today().isoformat()
    out += [f"Exported from Proseway on {today}. {len(groups)} highlights, {n_notes} notes.", ""]

    current_chapter: object = object()
    for parts in groups.values():
        first = parts[0]
        ch = first["chapter"]
        if ch != current_chapter:
            current_chapter = ch
            heading = titles.get(ch) if ch is not None else None
            if heading:
                out += [f"## {heading}", ""]
            elif ch is None:
                out += ["## Unplaced highlights", ""]
        quote = " ".join(p["exact"] for p in parts).strip()
        for line in quote.splitlines() or [""]:
            out.append(f"> {line}")
        meta = []
        if first["page"]:
            meta.append(f"p. {first['page']}")
        if first["color"]:
            meta.append(COLOR_NAMES.get(first["color"], first["color"]))
        if any(p["orphaned"] for p in parts):
            meta.append("could not be placed after re-conversion")
        out.append(f">\n> — {' · '.join(meta)}" if meta else "")
        note = "\n".join(p["note"] for p in parts if p["note"]).strip()
        if note:
            out += ["", note]
        out.append("")
    if bookmarks:
        out += ["## Bookmarks", ""]
        for b in bookmarks:
            label = b["note"] or (b["exact"][:80] if b["exact"] else "")
            out.append(f"- p. {b['page']}" + (f": {label}" if label else ""))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def build_backup(db: Database, book_ids: list[str] | None = None) -> dict[str, Any]:
    with db.connect() as c:
        books = c.execute("SELECT * FROM books ORDER BY created_at").fetchall()
        out_books = []
        for b in books:
            if book_ids and b["id"] not in book_ids:
                continue
            anns = [
                {k: r[k] for k in ANNOTATION_COLUMNS if k != "book_id"}
                for r in c.execute("SELECT * FROM annotations WHERE book_id=? ORDER BY seq", (b["id"],))
            ]
            pos = c.execute("SELECT block_id, seq, progress, updated_at FROM positions WHERE book_id=?",
                            (b["id"],)).fetchone()
            out_books.append({
                "sha256": b["sha256"],
                "title": b["title"][:-4] if b["title"].endswith(".pdf") else b["title"],
                "author": b["author"],
                "fileName": b["file_name"],
                "position": dict(pos) if pos else None,
                "annotations": anns,
            })
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "app": f"proseway {__version__}",
        "exportedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "books": out_books,
    }


class BackupError(ValueError):
    pass


COLORS = {"yellow", "green", "blue", "pink", "purple"}
_HEX32 = re.compile(r"[0-9a-f]{32}")


def _number(v: Any, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise BackupError(f"bad {what}")
    return float(v)


def _clean_annotation(a: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(a, dict):
        raise BackupError("annotation is not an object")
    out = {k: a.get(k) for k in ANNOTATION_COLUMNS if k != "book_id" and k in a}
    if not isinstance(out.get("id"), str) or not out["id"] or len(out["id"]) > 64:
        raise BackupError("annotation without a valid id")
    if out.get("kind") not in ("highlight", "bookmark"):
        raise BackupError("unknown annotation kind")
    for key in ("exact", "prefix", "suffix", "note", "block_id"):
        if key in out and out[key] is not None and not isinstance(out[key], str):
            raise BackupError(f"bad {key}")
    for key in ("start", "end", "page", "seq", "orphaned"):
        if out.get(key) is not None and (isinstance(out[key], bool) or not isinstance(out[key], int)):
            raise BackupError(f"bad {key}")
    if out.get("color") is not None and out["color"] not in COLORS:
        raise BackupError("bad color")
    if out.get("group_id") is not None and not (isinstance(out["group_id"], str) and _HEX32.fullmatch(out["group_id"])):
        raise BackupError("bad group id")
    out["created_at"] = _number(out.get("created_at", 0.0), "created_at")
    out["updated_at"] = _number(out.get("updated_at", out["created_at"]), "updated_at")
    out.setdefault("block_id", "")
    if len(out.get("note") or "") > 20000:
        out["note"] = out["note"][:20000]
    return out


def _clean_position(pos: Any) -> dict[str, Any] | None:
    if not isinstance(pos, dict) or not isinstance(pos.get("block_id"), str):
        return None
    seq = pos.get("seq") or 0
    if isinstance(seq, bool) or not isinstance(seq, int):
        raise BackupError("bad position")
    return {
        "block_id": pos["block_id"][:64],
        "seq": seq,
        "progress": max(0.0, min(1.0, _number(pos.get("progress") or 0, "progress"))),
        "updated_at": _number(pos.get("updated_at") or 0, "position time"),
    }


def restore_backup(db: Database, paths: DataPaths, data: Any) -> dict[str, int]:
    """Merge a backup into the library. Newer edits win; nothing is deleted.

    The whole backup is validated before anything is written, and the merge happens in one
    transaction, so a bad file never leaves a half-restored library behind.
    """
    if not isinstance(data, dict) or data.get("format") != BACKUP_FORMAT:
        raise BackupError("this file isn't a Proseway backup")
    if not isinstance(data.get("version"), int) or data["version"] > BACKUP_VERSION:
        raise BackupError("it was made by a newer version of Proseway")
    books = data.get("books", [])
    if not isinstance(books, list):
        raise BackupError("no books list")
    entries = []
    for entry in books:
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", entry["sha256"]
        ):
            raise BackupError("book entry without a valid file fingerprint")
        raw_anns = entry.get("annotations", [])
        if not isinstance(raw_anns, list):
            raise BackupError("bad annotations list")
        entries.append((entry, [_clean_annotation(a) for a in raw_anns], _clean_position(entry.get("position"))))

    stats = {"books_matched": 0, "books_waiting": 0, "annotations_added": 0, "annotations_updated": 0}
    waiting: list[tuple[dict, list[dict]]] = []
    with db.transaction() as c:
        for entry, anns, pos in entries:
            book = c.execute("SELECT id FROM books WHERE sha256=?", (entry["sha256"],)).fetchone()
            if book is None:
                waiting.append((entry, anns))
                continue
            book_id = book["id"]
            stats["books_matched"] += 1
            blocks = [BlockText(r["id"], r["text"], r["page"], r["seq"])
                      for r in c.execute("SELECT id, text, page, seq FROM blocks WHERE book_id=? ORDER BY seq", (book_id,))]
            for a in anns:
                cur = c.execute("SELECT book_id, updated_at FROM annotations WHERE id=?", (a["id"],)).fetchone()
                if cur is not None and cur["book_id"] != book_id:
                    continue  # never move another book's annotation
                if cur is not None and (cur["updated_at"] or 0) >= a["updated_at"]:
                    continue
                if blocks:
                    res = resolve(Anchor(a["block_id"], a.get("start") or 0, a.get("end") or 0,
                                         a.get("exact") or "", a.get("prefix") or "", a.get("suffix") or ""),
                                  blocks, a.get("page"))
                    a.update(block_id=res.block_id or a["block_id"], start=res.start, end=res.end,
                             seq=res.seq, orphaned=1 if res.method == "orphaned" else 0)
                a["book_id"] = book_id
                cols = ", ".join(a.keys())
                marks = ", ".join("?" for _ in a)
                c.execute(f"INSERT OR REPLACE INTO annotations({cols}) VALUES ({marks})", tuple(a.values()))  # noqa: S608
                stats["annotations_updated" if cur is not None else "annotations_added"] += 1
            if pos is not None:
                cur = c.execute("SELECT updated_at FROM positions WHERE book_id=?", (book_id,)).fetchone()
                if cur is None or cur["updated_at"] < pos["updated_at"]:
                    c.execute(
                        "INSERT OR REPLACE INTO positions(book_id, block_id, seq, progress, updated_at) VALUES (?,?,?,?,?)",
                        (book_id, pos["block_id"], pos["seq"], pos["progress"], pos["updated_at"]),
                    )

    # Notes for books that aren't imported yet wait in a side file until the PDF arrives.
    for entry, anns in waiting:
        detached = paths.root / "detached-annotations"
        detached.mkdir(exist_ok=True)
        f = detached / f"{entry['sha256']}.json"
        if f.resolve().parent != detached.resolve():
            raise BackupError("invalid file fingerprint")
        existing = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"annotations": []}
        known = {a["id"] for a in existing["annotations"]}
        existing["annotations"] += [a for a in anns if a["id"] not in known]
        title = entry.get("title", "")
        existing.update({"sha256": entry["sha256"], "title": title if isinstance(title, str) else ""})
        f.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
        stats["books_waiting"] += 1
    return stats
