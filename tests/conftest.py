from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from proseway import library  # noqa: E402
from proseway.db import Database  # noqa: E402
from proseway.paths import DataPaths  # noqa: E402
from proseway.pipeline.convert import run_conversion  # noqa: E402


@pytest.fixture
def lib(tmp_path):
    paths = DataPaths(tmp_path / "lib").ensure()
    db = Database(paths.db).init()
    return paths, db


def convert(paths: DataPaths, db: Database, pdf: Path, engine: str | None = None, monkeypatch=None) -> str:
    """Import and convert synchronously; returns the book id."""
    if engine and monkeypatch is not None:
        monkeypatch.setenv("PROSEWAY_ENGINE", engine)
    with open(pdf, "rb") as fh:
        tmp, sha, size = library.save_upload(paths, fh)
    book_id, _ = library.create_book(db, paths, tmp, sha, size, pdf.name)
    run_conversion(str(paths.db), str(paths.root), book_id)
    return book_id


def blocks(db: Database, book_id: str) -> list[dict]:
    with db.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM blocks WHERE book_id=? ORDER BY seq", (book_id,))]


def book_row(db: Database, book_id: str) -> dict:
    with db.connect() as c:
        return dict(c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone())
