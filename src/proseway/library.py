"""Book import and queries shared by the API."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from .db import Database, now
from .paths import DataPaths
from .pipeline import errors

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GiB; big scanned textbooks can be large

ANNOTATION_COLUMNS = (
    "id", "book_id", "kind", "color", "group_id", "block_id", "start", "end", "exact",
    "prefix", "suffix", "note", "page", "seq", "orphaned", "created_at", "updated_at",
)


class UploadTooLarge(Exception):
    pass


def save_upload(paths: DataPaths, stream: BinaryIO, max_bytes: int = MAX_UPLOAD_BYTES) -> tuple[Path, str, int]:
    """Stream an upload to a temp file, hashing as we go. Returns (path, sha256, size)."""
    paths.tmp.mkdir(parents=True, exist_ok=True)
    tmp = paths.tmp / f"upload-{uuid.uuid4().hex}.pdf"
    h = hashlib.sha256()
    size = 0
    first = b""
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                if not first:
                    first = chunk[:1024]
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge()
                h.update(chunk)
                out.write(chunk)
        if b"%PDF-" not in first:
            raise errors.not_a_pdf()
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, h.hexdigest(), size


def title_from_filename(name: str) -> str:
    stem = Path(name).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(stem.split()) or "Untitled"


def create_book(db: Database, paths: DataPaths, tmp: Path, sha: str, size: int, file_name: str) -> tuple[str, bool]:
    """Register an uploaded PDF. Returns (book_id, created). Duplicate files are not re-imported."""
    with db.connect() as c:
        row = c.execute("SELECT id FROM books WHERE sha256=?", (sha,)).fetchone()
    if row:
        tmp.unlink(missing_ok=True)
        return row["id"], False
    book_id = uuid.uuid4().hex
    book_dir = paths.book_dir(book_id)
    book_dir.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, paths.original_pdf(book_id))
    t = now()
    safe_name = Path(file_name).name[:255] if file_name else "book.pdf"
    try:
        with db.connect() as c:
            c.execute(
                "INSERT INTO books(id, sha256, title, file_name, file_size, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,'queued',?,?)",
                (book_id, sha, title_from_filename(safe_name) + ".pdf", safe_name, size, t, t),
            )
    except sqlite3.IntegrityError:
        # The same file was imported twice at the same moment: keep the first one.
        shutil.rmtree(book_dir, ignore_errors=True)
        with db.connect() as c:
            row = c.execute("SELECT id FROM books WHERE sha256=?", (sha,)).fetchone()
        return row["id"], False
    return book_id, True


def book_public(row) -> dict[str, Any]:
    d = dict(row)
    title = d["title"]
    if title.endswith(".pdf"):
        title = title[:-4]
    error = None
    if d.get("error"):
        try:
            error = json.loads(d["error"])
        except ValueError:
            error = {"code": "internal", "message": d["error"]}
    return {
        "id": d["id"],
        "title": title,
        "author": d["author"],
        "fileName": d["file_name"],
        "fileSize": d["file_size"],
        "pageCount": d["page_count"],
        "pagesDone": d["pages_done"],
        "status": d["status"],
        "error": error,
        "wordCount": d["word_count"],
        "hasCover": bool(d["has_cover"]),
        "createdAt": d["created_at"],
        "updatedAt": d["updated_at"],
        "lastOpenedAt": d["last_opened_at"],
        "pipelineVersion": d["pipeline_version"],
    }


def delete_book(db: Database, paths: DataPaths, book_id: str, keep_annotations: bool = True) -> None:
    """Delete a book's converted data and file.

    Highlights and notes are exported into a 'detached' JSON file next to the database first,
    so deleting a book never silently destroys someone's notes (a common complaint about other
    readers). Re-importing the same file restores them.
    """
    with db.connect() as c:
        book = c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if book is None:
            return
        anns = [dict(r) for r in c.execute("SELECT * FROM annotations WHERE book_id=?", (book_id,))]
    if keep_annotations and anns:
        detached = paths.root / "detached-annotations"
        detached.mkdir(exist_ok=True)
        (detached / f"{book['sha256']}.json").write_text(
            json.dumps({"sha256": book["sha256"], "title": book["title"], "annotations": anns},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    with db.transaction() as c:
        c.execute("DELETE FROM blocks_fts WHERE book_id=?", (book_id,))
        c.execute("DELETE FROM books WHERE id=?", (book_id,))
    shutil.rmtree(paths.book_dir(book_id), ignore_errors=True)


def reattach_annotations(db: Database, paths: DataPaths, book_id: str, sha: str) -> int:
    """If notes for this file were kept when it was deleted, bring them back."""
    f = paths.root / "detached-annotations" / f"{sha}.json"
    if not f.exists():
        return 0
    data = json.loads(f.read_text(encoding="utf-8"))
    n = 0
    with db.transaction() as c:
        for a in data.get("annotations", []):
            a = {k: v for k, v in dict(a).items() if k in ANNOTATION_COLUMNS}
            a["book_id"] = book_id
            cols = ", ".join(a.keys())
            marks = ", ".join("?" for _ in a)
            c.execute(f"INSERT OR IGNORE INTO annotations({cols}) VALUES ({marks})", tuple(a.values()))  # noqa: S608
            n += 1
    f.unlink(missing_ok=True)
    return n
