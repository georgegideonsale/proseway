"""Pipeline tests against generated PDFs with known ground truth, for both engines."""

from __future__ import annotations

import json
import re

import pytest

import pdfgen
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


@pytest.mark.parametrize("engine", ENGINES)
def test_narrow_gutter_columns_are_not_read_across(lib, tmp_path, engine, monkeypatch):
    """Justified columns with a 12 pt gutter (narrower than the cell-gap threshold)."""
    paths, db = lib
    pdf = tmp_path / "narrow.pdf"
    left, right = pdfgen.make_two_column(pdf, gutter=12, justify=True)
    bid = convert(paths, db, pdf, engine, monkeypatch)
    texts = [norm(b["text"]) for b in blocks(db, bid) if b["type"] == "paragraph"]
    # (The one-page document's running header can't be told apart from text, so skip it.)
    assert [t for t in texts if t != "JOURNAL OF TESTS"] == [norm(p) for p in left + right]


@pytest.mark.parametrize("engine", ENGINES)
def test_text_inside_figures_belongs_to_the_figure(lib, tmp_path, engine, monkeypatch):
    paths, db = lib
    pdf = tmp_path / "figures.pdf"
    paras, caption = pdfgen.make_figure_page(pdf)
    bid = convert(paths, db, pdf, engine, monkeypatch)
    out = blocks(db, bid)
    body = [norm(b["text"]) for b in out if b["type"] in ("paragraph", "list_item")]
    # The prose, including the shaded sidebar, is all there and nothing else is.
    assert body == [norm(p) for p in paras]
    figs = [b for b in out if b["type"] == "figure"]
    assert len(figs) == 2
    diagram, shot = (json.loads(f["data_json"]) for f in figs)
    for label in pdfgen.FIGURE_LABELS:
        assert label in diagram["figure_text"]
    assert "Click Approve to keep" in shot["figure_text"] and "Rejected tasks" in shot["figure_text"]
    assert diagram["src"] and shot["src"]
    # The caption stays a caption, right after its figure, and points back to it.
    cap = next(b for b in out if b["type"] == "caption")
    assert norm(cap["text"]) == caption
    assert out.index(cap) == out.index(figs[0]) + 1
    assert diagram["caption"] == cap["id"]
    # Figure text is searchable and leads to the figure.
    with db.connect() as c:
        hit = c.execute("SELECT block_id FROM blocks_fts WHERE blocks_fts MATCH ? AND book_id=?",
                        ('"Classify"', bid)).fetchone()
    assert hit["block_id"] == figs[0]["id"]


@pytest.mark.parametrize("engine", ENGINES)
def test_table_without_rules_becomes_a_table(lib, tmp_path, engine, monkeypatch):
    paths, db = lib
    pdf = tmp_path / "table.pdf"
    paras, rows, items = pdfgen.make_borderless_table(pdf)
    bid = convert(paths, db, pdf, engine, monkeypatch)
    out = blocks(db, bid)
    tables = [b for b in out if b["type"] == "table"]
    assert len(tables) == 1
    assert json.loads(tables[0]["data_json"])["rows"] == rows
    assert [norm(b["text"]) for b in out if b["type"] == "paragraph"] == [norm(p) for p in paras]
    # The table sits between the paragraphs around it.
    seq = [b["type"] for b in out]
    assert seq.index("table") == seq.index("paragraph") + 1
    # A numbered list whose numbers are set apart is still a list, not a table.
    assert [norm(b["text"]) for b in out if b["type"] == "list_item"] == [f"{n}. {t}" for n, t in enumerate(items, 1)]


@pytest.mark.parametrize("engine", ENGINES)
def test_two_column_prose_is_never_a_table(lib, tmp_path, engine, monkeypatch):
    paths, db = lib
    for gutter in (24, 12):
        pdf = tmp_path / f"two-{gutter}.pdf"
        pdfgen.make_two_column(pdf, gutter=gutter, justify=True)
        bid = convert(paths, db, pdf, engine, monkeypatch)
        assert not [b for b in blocks(db, bid) if b["type"] == "table"]


def test_text_tables_and_display_maths():
    """A grid of numbers is a table even when the paper's font name looks like a maths font
    (STIX); stacked limits and sums of a display equation are not a table."""
    from proseway.pipeline.layout import Line, find_text_tables

    def grid(rows, math=0.0):
        out = []
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                out.append(Line(text=text, x0=100 + 90 * c, x1=100 + 90 * c + 6 * len(text), top=100 + 14 * r,
                                bot=110 + 14 * r, size=10, font="STIXTwoText", bold=False, italic=False,
                                mono=False, math=math, spans=[], page=1))
        return out

    numbers = [["Model", "Params", "Score"], ["Alpha", "11B", "25.7"], ["Beta", "175B", "33.1"], ["Gamma", "175B", "39.9"]]
    tables, rest = find_text_tables(grid(numbers, math=1.0))
    assert [t["rows"] for t in tables] == [numbers] and not rest
    equation = [["h(n+m)", "", "h(n)"], ["∑", "1+1/logX =", "∑"], ["n=a (qk) n", "", "n=a+m (qk) n"]]
    lines = [ln for ln in grid(equation) if ln.text]
    tables, rest = find_text_tables(lines)
    assert not tables and len(rest) == len(lines)
    # A back-of-book index set in three columns is running text, not a table.
    index = [["bar graph, 14", "critical value, 374", "F ratio, 745"],
             ["Bernoulli Trial, 254", "cumulative, 327", "fair, 176"],
             ["box plots, 96", "degrees of freedom, 569", "histogram, 77"],
             ["Cluster Sampling, 45", "error bound, 460", "independent, 181, 189"]]
    lines = grid(index)
    tables, rest = find_text_tables(lines)
    assert not tables and len(rest) == len(lines)


def test_ligature_letters_are_not_taken_for_overprint():
    """PDFium reports the 'ff' ligature of 'officers' as two f's with the same box; both stay.
    A copy of a glyph drawn later at the same spot (fake bold) is dropped."""
    from proseway.pipeline.extract import lines_from_chars

    def ch(t, x0, w=5.0):
        return {"text": t, "fontname": "Times", "size": 10.0, "x0": x0, "x1": x0 + w,
                "top": 100.0, "bottom": 110.0, "upright": True}

    word = [ch("o", 0), ch("f", 5, 9), ch("f", 5, 9), ch("i", 14), ch("c", 18), ch("e", 23), ch("r", 28), ch("s", 33)]
    assert lines_from_chars(word)[0]["t"] == "officers"
    bold = [ch("B", 0), ch("e", 5), ch("d", 10), ch("B", 0.3), ch("e", 5.3), ch("d", 10.3)]
    assert lines_from_chars(bold)[0]["t"] == "Bed"
    # A drop shadow: the same label drawn three times, 1.5 pt apart, reads once.
    shadow = [ch(t, 6 * k + d) for d in (0, 1.5, 3.0) for k, t in enumerate("correct")]
    assert [ln["t"] for ln in lines_from_chars(shadow)] == ["correct"]


def test_scan_text_layer_is_not_figure_text():
    """A sparse scanned page (title page) under its own OCR text layer: the page image stays a
    picture and the short title lines stay text, even though they look like labels."""
    from proseway.pipeline.extract import find_figures

    title = ["THE HISTORY", "OF THE", "DECLINE AND FALL", "OF THE", "ROMAN EMPIRE"]
    lines = [{"t": t, "x0": 200.0, "x1": 200.0 + 9 * len(t), "top": 200.0 + 30 * k, "bot": 214.0 + 30 * k,
              "sz": 14.0, "m": False} for k, t in enumerate(title)]
    page_image = {"x0": 0.0, "top": 0.0, "x1": 612.0, "bot": 550.0}
    kept, figs = find_figures(lines, [page_image], [], [], 612.0, 792.0)
    assert [ln["t"] for ln in kept] == title
    assert len(figs) == 1 and "text" not in figs[0]


def _ocr_line(text: str, x0: float, top: float, size: float, width: float | None = None) -> dict:
    """A line as the OCR engine reports it: size estimated from the box height."""
    return {"t": text, "x0": x0, "x1": x0 + (width or len(text) * size * 0.5), "top": top,
            "bot": top + size * 1.35, "sz": size, "font": "OCR", "b": False, "i": False,
            "m": False, "mt": 0.0, "sp": [], "conf": 0.9}


def test_ocr_watermarks_and_heading_sizes():
    """OCR pages: 'Digitized by Google' in its OCR spellings goes; wobbly OCR sizes don't make
    headings; a clearly larger, isolated title still does."""
    from proseway.pipeline.layout import assemble

    stamps = ["Digized by Google", "Diglied byGogle", "Dguiea ygGoogle", "Digtize by Google", None]
    body = ["The kitchen was cold and the table was not cleared and nobody",
            "had touched the bread since the morning before, said the sheriff,",
            "looking at the stove and then at the door of the little room.",
            "His wife stood by the window and said nothing at all to him."]
    pages = []
    for n, stamp in enumerate(stamps, 1):
        lines = []
        y = 80.0
        if n == 1:
            lines.append(_ocr_line("Trifles", 120, y, 18))
            y += 60
        for k, text in enumerate(body):
            # OCR size estimates wobble between 8.5 and 11.5 for the same type.
            lines.append(_ocr_line(text, 30, y, (8.5, 9.0, 11.5, 9.0)[k], width=260))
            y += 14
        if stamp:
            lines.append(_ocr_line(stamp, 215, 521, 12.5, width=72))
        else:  # the stamp read as two pieces
            lines += [_ocr_line("zed by", 228, 526, 5.5, width=19), _ocr_line("Google", 240, 520, 14.5, width=47)]
        pages.append({"n": n, "w": 330.0, "h": 560.0, "lines": lines, "images": [], "tables": [],
                      "scanned": True, "ocr": True})
    out = assemble(pages)
    texts = [b.text for b in out["blocks"]]
    assert not [t for t in texts if "oog" in t.casefold() or "zed by" in t]
    assert out["stats"]["removed"]["watermarks"] == 6
    headings = [b.text for b in out["blocks"] if b.type == "heading"]
    assert headings == ["Trifles"]
    joined = " ".join(texts)
    for line in body:
        assert line in joined  # every word of the play is still there


def test_ocr_scan_end_to_end(lib, tmp_path):
    """A generated image-only scan through the real OCR engine (skipped without the add-on)."""
    pytest.importorskip("rapidocr_onnxruntime")
    from rapidfuzz import fuzz

    paths, db = lib
    pdf = tmp_path / "scan.pdf"
    lines = pdfgen.make_scanned(pdf, pages=3)
    bid = convert(paths, db, pdf)
    assert book_row(db, bid)["status"] == "ready"
    out = blocks(db, bid)
    joined = " ".join(b["text"] for b in out)
    assert "oogle" not in joined and "Digitized" not in joined
    assert "COLD HOUSE" not in joined  # running head
    for line in lines:
        assert fuzz.partial_ratio(line, joined) >= 90
    headings = [b["text"] for b in out if b["type"] == "heading"]
    assert all(fuzz.ratio(h, "The Cold House") >= 80 for h in headings)


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
