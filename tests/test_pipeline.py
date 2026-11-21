"""Pipeline tests against generated PDFs with known ground truth, for both engines."""

from __future__ import annotations

import json
import re

import pdfgen
import pytest
from conftest import blocks, book_row, convert

from proseway.pipeline.layout import PAGE_NUMBER, running_key, should_join_hyphen

ENGINES = ["pdfium", "plumber"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.parametrize("engine", ENGINES)
def test_novel_is_faithful_and_clean(lib, tmp_path, engine, monkeypatch):
    paths, db = lib
    pdf = tmp_path / "novel.pdf"
    paras = pdfgen.make_novel(pdf, pages=3)
    bid = convert(paths, db, pdf, engine, monkeypatch)
    assert book_row(db, bid)["status"] == "ready"
    out = blocks(db, bid)
    texts = [norm(b["text"]) for b in out if b["type"] == "paragraph"]
    # Every paragraph comes back word for word, in order, hyphenation undone.
    assert texts == [norm(p) for p in paras]
    joined = " ".join(b["text"] for b in out)
    assert "A TEST BOOK" not in joined  # running header removed
    assert not any(PAGE_NUMBER.match(b["text"].strip()) for b in out)  # page numbers removed
    assert "extra-" not in joined and "extraordinary" in joined
    assert out[0]["type"] == "heading" and out[0]["text"] == "Chapter One"
    # Every block knows its source page, and pages only move forward.
    pages = [b["page"] for b in out]
    assert pages == sorted(pages) and pages[0] == 1 and pages[-1] >= 3


@pytest.mark.parametrize("engine", ENGINES)
def test_two_columns_read_in_order(lib, tmp_path, engine, monkeypatch):
    paths, db = lib
    pdf = tmp_path / "two.pdf"
    left, right = pdfgen.make_two_column(pdf)
    bid = convert(paths, db, pdf, engine, monkeypatch)
    texts = [norm(b["text"]) for b in blocks(db, bid) if b["type"] == "paragraph"]
    expected = [norm(p) for p in left + right]
    got = [t for t in texts if t in expected]
    assert got == expected


@pytest.mark.parametrize("engine", ENGINES)
def test_footnotes_are_linked(lib, tmp_path, engine, monkeypatch):
    paths, db = lib
    pdf = tmp_path / "notes.pdf"
    pdfgen.make_footnotes(pdf)
    bid = convert(paths, db, pdf, engine, monkeypatch)
    out = blocks(db, bid)
    notes = [b for b in out if b["type"] == "footnote"]
    assert len(notes) == 1
    assert "See the discussion in the appendix" in notes[0]["text"]
    body = next(b for b in out if "historian" in b["text"])
    spans = json.loads(body["data_json"]).get("spans", [])
    refs = [s for s in spans if s[2] == "fnref"]
    assert refs and refs[0][3] == notes[0]["id"]
    assert body["text"][refs[0][0]:refs[0][1]] == "1"
    # The footnote comes after the paragraph it belongs to, never splitting it.
    assert out.index(notes[0]) > out.index(body)


def test_password_protected_pdf_gets_friendly_error(lib, tmp_path):
    paths, db = lib
    pdf = tmp_path / "locked.pdf"
    pdfgen.make_encrypted(pdf)
    bid = convert(paths, db, pdf)
    row = book_row(db, bid)
    assert row["status"] == "error"
    err = json.loads(row["error"])
    assert err["code"] == "password"
    assert "password" in err["message"].lower()


def test_corrupt_pdf_gets_friendly_error(lib, tmp_path):
    paths, db = lib
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF")
    bid = convert(paths, db, pdf)
    row = book_row(db, bid)
    assert row["status"] == "error"
    assert json.loads(row["error"])["code"] in ("corrupt", "empty")


def test_non_pdf_upload_is_rejected(lib, tmp_path):
    from proseway import library
    from proseway.pipeline.errors import ConversionError

    paths, _db = lib
    f = tmp_path / "evil.pdf"
    f.write_bytes(b"<html><script>alert(1)</script></html>")
    with open(f, "rb") as fh, pytest.raises(ConversionError) as exc:
        library.save_upload(paths, fh)
    assert exc.value.code == "not_pdf"
    assert not list(paths.tmp.iterdir())  # temp file cleaned up


def test_resume_skips_finished_pages(lib, tmp_path, monkeypatch):
    """A conversion that was interrupted continues from its page checkpoints."""
    from proseway.pipeline import convert as conv
    from proseway.pipeline import extract

    paths, db = lib
    pdf = tmp_path / "novel.pdf"
    pdfgen.make_novel(pdf, pages=3)
    bid = convert(paths, db, pdf)
    pages_dir = paths.pages_dir(bid)
    assert len(list(pages_dir.glob("*.json"))) >= 3
    calls = []
    original = extract.extract_page
    monkeypatch.setattr(extract, "extract_page", lambda *a, **k: calls.append(a[1]) or original(*a, **k))
    (pages_dir / "00002.json").unlink()  # pretend we stopped after page 1
    conv.run_conversion(str(paths.db), str(paths.root), bid)
    assert calls == [1]  # only the missing page (0-based index 1) was extracted again
    assert book_row(db, bid)["status"] == "ready"


def test_hyphen_rules():
    from collections import Counter

    vocab = Counter({"extraordinary": 3, "self": 5, "evident": 4, "something": 2, "some": 9, "thing": 7})
    assert should_join_hyphen("an extra", "ordinary day", vocab)
    assert should_join_hyphen("some", "thing", vocab)  # joined form is a known word
    assert not should_join_hyphen("self", "evident truth", vocab)  # both halves are words
    assert should_join_hyphen("con", "tinue", vocab)  # unknown fragments: a typographic break
    assert not should_join_hyphen("pre", "War", vocab)  # capital after the hyphen: keep it


def test_running_key_ignores_numbers():
    assert running_key("12 Pride and Prejudice") == running_key("214 Pride and Prejudice")
    assert running_key("CHAPTER IV") == running_key("CHAPTER XI")
