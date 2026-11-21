"""The multi-chapter fixture the reader-windowing browser test relies on."""

from __future__ import annotations

import pdfgen
from conftest import blocks, book_row, convert


def test_long_book_converts_into_one_chapter_per_heading(lib, tmp_path):
    paths, db = lib
    pdf = tmp_path / "long.pdf"
    headings = pdfgen.make_long_book(pdf, chapters=6, pages_per_chapter=3)
    book_id = convert(paths, db, pdf)
    assert book_row(db, book_id)["status"] == "ready"
    rows = blocks(db, book_id)
    assert sorted({r["chapter"] for r in rows}) == list(range(6))
    found = [r["text"] for r in rows if r["type"] == "heading"]
    assert found == headings
    # Each chapter opens with its heading, and its paragraphs name the chapter.
    for r in rows:
        if r["type"] == "paragraph" and r["text"].startswith("Paragraph "):
            name = r["text"].split(" of chapter ")[1].split(".")[0]
            assert headings[r["chapter"]] == f"Chapter {name.capitalize()}"
