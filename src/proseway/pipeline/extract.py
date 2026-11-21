"""Stage 1: per-page extraction of positioned lines, images and tables.

The output of this stage is deliberately plain JSON so that each finished page can be
written to disk as a checkpoint. Resuming a conversion means skipping pages whose JSON
already exists.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import errors
from .fonts import clean_font_name, font_flags

log = logging.getLogger(__name__)

MIN_FIGURE_AREA_RATIO = 0.015  # images smaller than this share of the page are ignored
MIN_FIGURE_SIDE = 36.0  # points


# ---------------------------------------------------------------------------
# Opening documents safely
# ---------------------------------------------------------------------------


def check_pdf_header(path: Path) -> None:
    with open(path, "rb") as fh:
        head = fh.read(1024)
    if b"%PDF-" not in head:
        raise errors.not_a_pdf()


def open_pdfplumber(path: Path):
    import pdfplumber
    from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
    from pdfminer.pdfparser import PDFSyntaxError

    check_pdf_header(path)
    try:
        pdf = pdfplumber.open(str(path), password="")
        doc = pdf.doc
    except PDFPasswordIncorrect as exc:
        raise errors.password_protected() from exc
    except PDFEncryptionError as exc:
        # Unknown security handlers (e.g. DRM schemes) end up here.
        raise errors.password_protected() from exc
    except PDFSyntaxError as exc:
        raise errors.corrupt(str(exc)[:120]) from exc
    except Exception as exc:  # pdfminer raises a wide range of things on broken files
        if "password" in str(exc).lower() or "encrypt" in str(exc).lower():
            raise errors.password_protected() from exc
        raise errors.corrupt(type(exc).__name__) from exc
    try:
        extractable = doc.is_extractable
    except Exception:
        extractable = True
    if not extractable:
        pdf.close()
        raise errors.extraction_forbidden()
    try:
        n = len(pdf.pages)
    except Exception as exc:
        pdf.close()
        raise errors.corrupt(type(exc).__name__) from exc
    if n == 0:
        pdf.close()
        raise errors.empty()
    return pdf


def open_pdfium(path: Path):
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise errors.password_protected() from exc
        raise errors.corrupt(str(exc)[:120]) from exc


def read_metadata(path: Path) -> dict[str, Any]:
    """Title, author, page count and outline, using pdfium (fast, tolerant)."""
    doc = open_pdfium(path)
    try:
        meta: dict[str, Any] = {"title": "", "author": "", "pages": len(doc), "outline": []}
        try:
            m = doc.get_metadata_dict()
            meta["title"] = (m.get("Title") or "").strip()
            meta["author"] = (m.get("Author") or "").strip()
        except Exception:  # noqa: S110 - metadata is optional
            pass
        try:
            for item in doc.get_toc(max_depth=4):
                title = (item.get_title() or "").strip()
                dest = item.get_dest()
                page_index = dest.get_index() if dest is not None else None
                if title and page_index is not None:
                    meta["outline"].append(
                        {"level": item.level, "title": title, "page": page_index + 1}
                    )
        except Exception as exc:
            log.debug("outline unreadable: %s", exc)
        return meta
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Line building
# ---------------------------------------------------------------------------


def _median(values: list[float], default: float = 0.0) -> float:
    return statistics.median(values) if values else default


def _h(c: dict) -> float:
    return max(c["bottom"] - c["top"], 0.1)


def _rows_from_chars(chars: list[dict]) -> list[list[dict]]:
    """Group characters into visual rows by vertical overlap.

    Tall glyphs (drop caps, display initials) would otherwise swallow the two or three
    lines beside them, so they never absorb other characters; afterwards a lone drop cap is
    attached to the start of the line it belongs to.
    """
    visible = [c for c in chars if c["text"].strip()]
    median_h = _median([_h(c) for c in visible], 10.0)
    chars = sorted(chars, key=lambda c: ((c["top"] + c["bottom"]) / 2, c["x0"]))
    rows: list[dict] = []
    for ch in chars:
        center = (ch["top"] + ch["bottom"]) / 2
        h = _h(ch)
        big = h > 1.7 * median_h
        placed = False
        for row in reversed(rows[-5:]):
            # Tall glyphs only join tall rows (headings), normal glyphs only normal rows.
            if row["big"] != big:
                continue
            ratio = h / row["h"]
            # Smaller glyphs (superscripts, footnote markers) may join; much taller may not.
            if not (0.35 <= ratio <= 1.6):
                continue
            if row["top"] - 0.5 <= center <= row["bottom"] + 0.5:
                row["chars"].append(ch)
                # Only grow the row box with full-size characters so superscripts don't
                # stretch it into the next line.
                if 0.8 <= ratio <= 1.3:
                    row["top"] = min(row["top"], ch["top"])
                    row["bottom"] = max(row["bottom"], ch["bottom"])
                placed = True
                break
        if not placed:
            rows.append({"top": ch["top"], "bottom": ch["bottom"], "h": h, "big": big, "chars": [ch]})

    # Attach drop caps (a row of 1-2 tall glyphs) to the line that starts right after them.
    normal = [r for r in rows if not r["big"]]
    keep: list[dict] = []
    for r in rows:
        vis = [c for c in r["chars"] if c["text"].strip()]
        if r["big"] and 0 < len(vis) <= 2:
            cap_x1 = max(c["x1"] for c in vis)
            target = None
            for n in sorted(normal, key=lambda n: n["top"]):
                first = min(n["chars"], key=lambda c: c["x0"])
                if r["top"] - 2 <= n["top"] <= r["bottom"] and 0 <= first["x0"] - cap_x1 < 4 * median_h:
                    target = n
                    break
            if target is not None:
                first = min(target["chars"], key=lambda c: c["x0"])
                size = _median([c["size"] for c in target["chars"]], first["size"])
                for k, c in enumerate(sorted(vis, key=lambda c: c["x0"])):
                    c2 = dict(c)
                    c2.update(x0=first["x0"] - 0.02 * (len(vis) - k) - 0.01, x1=first["x0"] - 0.02 * (len(vis) - k - 1),
                              top=first["top"], bottom=first["bottom"], size=size)
                    target["chars"].append(c2)
                continue
        keep.append(r)
    keep.sort(key=lambda r: r["top"])
    return [sorted(r["chars"], key=lambda c: c["x0"]) for r in keep]


def _split_segments(row: list[dict], gutters: list[float] | None = None) -> list[list[dict]]:
    """Split a row where a large horizontal gap separates columns or table cells.

    `gutters` are x positions of page-wide column gutters (see `_find_gutters`): a gap that
    contains one is split even when it is narrower than the usual threshold, because narrow
    gutters (about 1.5 em in many two-column papers) look like wide word spaces."""
    sizes = [c["size"] for c in row if c["text"].strip()]
    size = _median(sizes, 10.0)
    segments: list[list[dict]] = [[]]
    prev = None
    for ch in row:
        if prev is not None:
            gap = ch["x0"] - prev["x1"]
            if gap > max(1.6 * size, 9.0) or (
                gutters and gap > 0.45 * size and any(prev["x1"] < g < ch["x0"] for g in gutters)
            ):
                segments.append([])
        segments[-1].append(ch)
        if ch["text"].strip():
            prev = ch
    return [s for s in segments if any(c["text"].strip() for c in s)]


def _find_gutters(rows: list[list[dict]]) -> list[float]:
    """Find x positions that are blank on most rows that have text on both sides of them.

    A column gutter is a vertical strip of white space that many rows straddle. Word spaces in
    justified text move from row to row, so in single-column text every x position is covered
    by glyphs on most rows and nothing is found."""
    gap_rows: Counter = Counter()
    cover_rows: Counter = Counter()
    for row in rows:
        vis = [c for c in row if c["text"].strip() and c["x1"] > c["x0"]]
        if len(vis) < 2:
            continue
        size = _median([c["size"] for c in vis], 10.0)
        covered: set[int] = set()
        for c in vis:
            covered.update(range(int(c["x0"]), int(c["x1"]) + 1))
        for b in covered:
            cover_rows[b] += 1
        left_edge, right_edge = vis[0]["x0"], max(c["x1"] for c in vis)
        for a, b in zip(vis, vis[1:], strict=False):
            # Both sides must be real text, not a list number or a short label before a tab.
            if (b["x0"] - a["x1"] > 0.45 * size and a["x1"] - left_edge > 5 * size
                    and right_edge - b["x0"] > 5 * size):
                for x in range(int(a["x1"]) + 1, int(b["x0"])):
                    if x not in covered:
                        gap_rows[x] += 1
    good = sorted(x for x, n in gap_rows.items() if n >= 6 and n >= 3 * cover_rows.get(x, 0))
    gutters: list[float] = []
    run: list[int] = []
    for x in good + [None]:  # type: ignore[list-item]
        if x is not None and run and x == run[-1] + 1:
            run.append(x)
            continue
        if run:
            # The strongest bin in the run, so all straddling rows are split at the same place.
            gutters.append(max(run, key=lambda b: (gap_rows[b], -abs(b - (run[0] + run[-1]) / 2))) + 0.5)
        run = [x] if x is not None else []
    return gutters


def _build_line(chars: list[dict]) -> dict | None:
    visible = [c for c in chars if c["text"].strip()]
    if not visible:
        return None
    size_counts = Counter(round(c["size"] * 2) / 2 for c in visible)
    main_size = size_counts.most_common(1)[0][0]
    main_chars = [c for c in visible if abs(c["size"] - main_size) <= 0.6] or visible
    main_bottom = _median([c["bottom"] for c in main_chars])
    font_counts = Counter(clean_font_name(c.get("fontname")) for c in visible)
    font = font_counts.most_common(1)[0][0]

    text_parts: list[str] = []
    spans: list[list[Any]] = []
    cur_style: str | None = None
    style_start = 0
    length = 0
    prev = None
    n_bold = n_italic = n_mono = n_math = 0

    last_visible = 0

    def close_style(at: int) -> None:
        nonlocal cur_style
        # A style run ends at its last visible character, never on a trailing space.
        at = min(at, last_visible) if last_visible > style_start else at
        if cur_style is not None and at > style_start:
            spans.append([style_start, at, cur_style])
        cur_style = None

    for ch in chars:
        t = ch["text"]
        if not t.strip():
            if text_parts and not text_parts[-1].endswith(" "):
                text_parts.append(" ")
                length += 1
            continue
        if prev is not None and text_parts and not text_parts[-1].endswith(" "):
            gap = ch["x0"] - prev["x1"]
            ref = min(ch["size"], prev["size"])
            if gap > 0.15 * ref:
                text_parts.append(" ")
                length += 1
        bold, italic, mono, math = font_flags(ch.get("fontname"))
        n_bold += bold
        n_italic += italic
        n_mono += mono
        n_math += math
        is_sup = ch["size"] < main_size * 0.86 and ch["bottom"] < main_bottom - 0.18 * main_size
        style = "sup" if is_sup else ("i" if italic and not math else None)
        if style != cur_style:
            close_style(length)
            if style is not None:
                cur_style = style
                style_start = length
        # Soft hyphens inside a line are invisible break hints; drop them.
        t = t.replace("­", "") if t != "­" else t
        text_parts.append(t)
        length += len(t)
        last_visible = length
        prev = ch
    close_style(length)

    text = "".join(text_parts)
    stripped = text.rstrip()
    if len(stripped) < len(text):
        text = stripped
        spans = [[s, min(e, len(text)), k] for s, e, k in spans if s < len(text)]
    n = len(visible)
    return {
        "t": text,
        "x0": round(min(c["x0"] for c in visible), 2),
        "x1": round(max(c["x1"] for c in visible), 2),
        "top": round(min(c["top"] for c in main_chars), 2),
        "bot": round(max(c["bottom"] for c in main_chars), 2),
        "sz": main_size,
        "font": font,
        "b": n_bold / n > 0.6,
        "i": n_italic / n > 0.6,
        "m": n_mono / n > 0.6,
        "mt": round(n_math / n, 2),
        "sp": spans,
    }


def _clean_char_text(t: str) -> str:
    # Control characters come from fonts with broken encodings (e.g. digits mapped to
    # U+0018). They are unreadable either way; dropping them keeps the text clean.
    if any(ord(ch) < 32 for ch in t):
        t = "".join(ch for ch in t if ord(ch) >= 32)
    # Private-use glyphs are similarly meaningless outside their font.
    if any(0xE000 <= ord(ch) <= 0xF8FF for ch in t):
        t = "".join(ch for ch in t if not 0xE000 <= ord(ch) <= 0xF8FF)
    return t


def _dedupe_overprint(chars: list[dict]) -> list[dict]:
    """Drop glyphs drawn twice in the same place (fake bold, shadows). pdfplumber's
    dedupe_chars does this for the other engine.

    PDFium splits ligatures into their letters with one shared box: the "ff" of "officers"
    is two "f"s drawn one right after the other at the same spot. Those are real letters, so
    only a copy drawn at some other point in the content stream counts as a duplicate.

    A copy must also be the same size and sit within a point of the first glyph: the same
    letter in another word, another size or another line is never a duplicate."""
    seen: dict[tuple, dict] = {}
    out: list[dict] = []
    for c in chars:
        if c["text"].strip() and c["x1"] > c["x0"]:
            key = (c["text"], round(c["x0"]), round(c["top"]))
            first = seen.get(key)
            if first is not None and _same_glyph_spot(c, first):
                ligature = abs(c.get("_i", 0) - first.get("_i", 0)) == 1 and (
                    c["x0"], c["x1"], c["top"], c["bottom"]) == (first["x0"], first["x1"], first["top"], first["bottom"])
                if not ligature:
                    continue
            seen[key] = c
        out.append(c)
    return out


def _same_size(a: float, b: float) -> bool:
    return abs(a - b) <= 0.1 * max(a, b, 1.0)


def _same_glyph_spot(c: dict, first: dict) -> bool:
    return (_same_size(c.get("size", 0.0), first.get("size", 0.0))
            and abs(c["x0"] - first["x0"]) <= 1.0 and abs(c["top"] - first["top"]) <= 1.0
            and abs((c["x1"] - c["x0"]) - (first["x1"] - first["x0"])) <= 1.0)


def _untangle(seg: list[dict]) -> list[list[dict]]:
    """Separate text runs that were drawn on top of each other.

    Overlapping labels in figures put two strings on the same row; sorted by x their letters
    interleave ("SOeuetdp utatsks"). When glyphs overlap heavily, split the segment back into
    runs following the order the PDF drew them in, which is the order of each string."""
    vis = [c for c in seg if c["text"].strip() and c["x1"] > c["x0"]]
    if len(vis) < 4:
        return [seg]
    overlaps = sum(
        1 for a, b in zip(vis, vis[1:], strict=False)
        if a["x1"] - b["x0"] > 0.5 * min(a["x1"] - a["x0"], b["x1"] - b["x0"])
    )
    if overlaps < 2 or overlaps < 0.15 * len(vis):
        return [seg]
    runs: list[list[dict]] = []
    for c in sorted(seg, key=lambda c: c.get("_i", 0)):
        run = runs[-1] if runs else None
        last = next((x for x in reversed(run) if x["text"].strip()), None) if run else None
        if run is not None and (last is None or not c["text"].strip()
                                or last["x0"] - 0.5 <= c["x0"] <= last["x1"] + 2.5 * max(c["size"], 1.0)):
            run.append(c)
        else:
            runs.append([c])
    return [sorted(r, key=lambda c: c["x0"]) for r in runs]


def lines_from_chars(chars: list[dict], counts: Counter | None = None, scan_layer: bool = False) -> list[dict]:
    """Build lines from glyphs. `counts` receives how many glyphs and lines the de-duplication
    passes dropped, so a book's stats show it.

    `scan_layer`: the text is a scan's own OCR layer (invisible text over a page-sized image).
    Its boxes come from an OCR engine, so they overlap and wobble; the passes that read
    overlap as a drawing effect (untangling, shadow lines) or blank strips as a column gutter
    are skipped there."""
    for k, c in enumerate(chars):
        c["_i"] = k  # drawing order, used to untangle overlapping text
        if c.get("text"):
            c["text"] = _clean_char_text(c["text"])
    candidates = [c for c in chars if c.get("upright", True) and c.get("text")]
    upright = _dedupe_overprint(candidates)
    lines: list[dict] = []
    rows = _rows_from_chars(upright)
    gutters = [] if scan_layer else _find_gutters(rows)
    for row in rows:
        for seg in _split_segments(row, gutters):
            for part in [seg] if scan_layer else _untangle(seg):
                line = _build_line(part)
                if line is not None:
                    lines.append(line)
    kept = lines if scan_layer else _drop_shadow_lines(lines)
    if counts is not None:
        if len(candidates) > len(upright):
            counts["overprint_glyphs"] += len(candidates) - len(upright)
        if len(lines) > len(kept):
            counts["shadow_lines"] += len(lines) - len(kept)
    return kept


def _drop_shadow_lines(lines: list[dict]) -> list[dict]:
    """Drop a line that repeats another line drawn almost on top of it (a drop shadow or
    blur effect drawn as offset copies of the text). Real text never overlaps itself.

    A copy is within 20% of the other's size, within about half a line of its height, and
    starts within 2.5 em of where its text sits in the other line. A short line that merely
    overlaps a longer one containing the same words ("Ibid." over a footnote at another
    size, or words that sit elsewhere in the line) is kept."""
    from rapidfuzz import fuzz

    def area(d: dict) -> float:
        return max((d["x1"] - d["x0"]) * (d["bot"] - d["top"]), 0.01)

    def is_copy(s: dict, o: dict) -> bool:
        # Shadow and pseudo-3D copies are scaled a little (up to 20%) and offset a few points.
        size = max(s["sz"], o["sz"], 1.0)
        if abs(s["sz"] - o["sz"]) > 0.2 * size or abs(s["top"] - o["top"]) > 0.6 * size:
            return False
        al = fuzz.partial_ratio_alignment(s["t"], o["t"])
        if al is None or al.score < 90:
            return False
        expected = o["x0"] + (o["x1"] - o["x0"]) * al.dest_start / max(len(o["t"]), 1)
        return abs(s["x0"] - expected) <= 2.5 * size

    order = sorted(range(len(lines)), key=lambda i: lines[i]["top"])
    drop: set[int] = set()
    for a, i in enumerate(order):
        li = lines[i]
        for j in order[a + 1:]:
            lj = lines[j]
            if lj["top"] >= li["bot"]:
                break  # sorted by top: nothing further down overlaps this line
            if i in drop or j in drop:
                continue
            ix = min(li["x1"], lj["x1"]) - max(li["x0"], lj["x0"])
            iy = min(li["bot"], lj["bot"]) - max(li["top"], lj["top"])
            short, other = (i, j) if len(li["t"]) <= len(lj["t"]) else (j, i)
            if (ix > 0 and iy > 0 and ix * iy >= 0.5 * area(lines[short]) and len(lines[short]["t"]) >= 4
                    and is_copy(lines[short], lines[other])):
                drop.add(short)
    return [ln for k, ln in enumerate(lines) if k not in drop] if drop else lines


# ---------------------------------------------------------------------------
# Page extraction
# ---------------------------------------------------------------------------


MAX_RENDER_PIXELS = 40_000_000  # ~160 MB of RGBA; a hostile page can't ask for more


def capped_scale(width_pt: float, height_pt: float, scale: float, max_pixels: int = MAX_RENDER_PIXELS) -> float:
    """Reduce a render scale so the bitmap stays under max_pixels, whatever size the page claims."""
    pixels = max(width_pt, 1.0) * max(height_pt, 1.0) * scale * scale
    if pixels <= max_pixels:
        return scale
    return scale * (max_pixels / pixels) ** 0.5


def _render_crop(pdfium_doc, page_index: int, bbox, page_w: float, page_h: float, out: Path,
                 scale: float = 2.0, fmt: str = "JPEG") -> bool:
    x0, top, x1, bottom = bbox
    x0, x1 = max(0.0, x0), min(page_w, x1)
    top, bottom = max(0.0, top), min(page_h, bottom)
    if x1 - x0 < 4 or bottom - top < 4:
        return False
    scale = capped_scale(x1 - x0, bottom - top, scale)
    try:
        page = pdfium_doc[page_index]
        bitmap = page.render(
            scale=scale,
            crop=(x0, page_h - bottom, page_w - x1, top),
            may_draw_forms=False,
        )
        img = bitmap.to_pil()
        if fmt == "JPEG":
            img = img.convert("RGB")
            img.save(out, "JPEG", quality=85, optimize=True)
        else:
            img.save(out, "PNG", optimize=True)
        page.close()
        return True
    except Exception as exc:
        log.warning("could not render crop on page %s: %s", page_index + 1, exc)
        return False


def render_cover(path: Path, out: Path, width: int = 480) -> bool:
    doc = open_pdfium(path)
    try:
        page = doc[0]
        w, h = page.get_size()
        bitmap = page.render(scale=capped_scale(w, h, width / max(w, 1.0), max_pixels=4_000_000),
                             may_draw_forms=False)
        bitmap.to_pil().convert("RGB").save(out, "JPEG", quality=82, optimize=True)
        page.close()
        return True
    except Exception as exc:
        log.warning("cover render failed: %s", exc)
        return False
    finally:
        doc.close()


class Source:
    """An open PDF. PDFium is always open; pdfplumber is opened only when needed."""

    def __init__(self, path: Path, engine: str | None = None):
        import os

        self.path = path
        self.engine = (engine or os.environ.get("PROSEWAY_ENGINE") or "pdfium").lower()
        self.pdfium = open_pdfium(path)
        self._plumber = None
        if self.engine == "plumber":
            self._plumber = open_pdfplumber(path)
        else:
            check_pdf_header(path)
            _check_permissions(self.pdfium)

    @property
    def plumber(self):
        if self._plumber is None:
            self._plumber = open_pdfplumber(self.path)
        return self._plumber

    def __len__(self) -> int:
        return len(self.pdfium)

    def close(self) -> None:
        if self._plumber is not None:
            self._plumber.close()
        self.pdfium.close()


def _check_permissions(pdfium_doc) -> None:
    """Refuse PDFs whose author disabled text extraction (bit 5 of the permission flags)."""
    import pypdfium2.raw as raw

    try:
        if raw.FPDF_GetSecurityHandlerRevision(pdfium_doc.raw) == -1:
            return  # not encrypted
        perms = raw.FPDF_GetDocPermissions(pdfium_doc.raw) & 0xFFFFFFFF
    except Exception:
        return
    if not perms & (1 << 4):
        raise errors.extraction_forbidden()


def extract_page(src: Source, index: int, assets_dir: Path, ocr=None) -> dict:
    if src.engine == "plumber":
        return _extract_page_plumber(src.plumber, src.pdfium, index, assets_dir, ocr)
    return _extract_page_pdfium(src, index, assets_dir, ocr)


def _finish_page(result: dict, images: list[dict], pdfium_doc, index: int, assets_dir: Path,
                 ocr, w: float, h: float) -> dict:
    if result["scanned"]:
        if ocr is not None:
            try:
                result["lines"] = ocr.page_lines(pdfium_doc, index, w, h)
                result["ocr"] = True
                images = []
            except Exception as exc:
                log.warning("OCR failed on page %s: %s", index + 1, exc)
        if not result["ocr"]:
            images = [{"x0": 0.0, "x1": w, "top": 0.0, "bot": h, "scan": True}]
    assets_dir.mkdir(parents=True, exist_ok=True)
    for k, im in enumerate(images):
        name = f"p{index + 1:05d}-img{k}.jpg"
        rendered = _render_crop(pdfium_doc, index, (im["x0"], im["top"], im["x1"], im["bot"]), w, h, assets_dir / name)
        if rendered or im.get("text"):
            # A figure that couldn't be rendered still carries its text, which must not be lost.
            entry = {key: round(v, 2) if isinstance(v, float) else v for key, v in im.items() if key != "i"}
            if rendered:
                entry["file"] = name
            result["images"].append(entry)
    return result


def _extract_page_pdfium(src: Source, index: int, assets_dir: Path, ocr=None) -> dict:
    from .pdfium_chars import page_chars, page_objects

    page = src.pdfium[index]
    try:
        chars, w, h = page_chars(page)
        n_paths, image_boxes, path_boxes = page_objects(page)
    finally:
        page.close()
    page_area = w * h
    scan_layer = _is_scan_layer(len(chars), image_boxes, page_area)
    counts: Counter = Counter()
    lines = lines_from_chars(chars, counts, scan_layer)
    graphics = path_boxes + image_boxes
    covered = 0.0
    images = []
    for x0, top, x1, bot in image_boxes:
        x0, x1, top, bot = max(0.0, x0), min(w, x1), max(0.0, top), min(h, bot)
        iw, ih = x1 - x0, bot - top
        if iw <= 0 or ih <= 0:
            continue
        covered += min(iw * ih, page_area)
        if iw * ih < page_area * MIN_FIGURE_AREA_RATIO or min(iw, ih) < MIN_FIGURE_SIDE:
            continue
        images.append({"x0": x0, "x1": x1, "top": top, "bot": bot})
    images = _merge_overlapping(images)
    n_chars = sum(len(ln["t"]) for ln in lines)
    scanned = n_chars < 20 and covered > page_area * 0.5
    images = _drop_scan_backgrounds(images, n_chars, page_area)
    tables = []
    if not scanned and n_paths >= 6:
        tables = _find_tables(src.plumber, index)
    if not scanned:
        lines, images = find_figures(lines, images, graphics, tables, w, h)
    result: dict[str, Any] = {"n": index + 1, "w": round(w, 2), "h": round(h, 2), "lines": lines,
                              "images": [], "tables": tables, "scanned": scanned, "ocr": False}
    _note_passes(result, counts, scan_layer)
    return _finish_page(result, images, src.pdfium, index, assets_dir, ocr, w, h)


def _is_scan_layer(n_chars: int, image_boxes: list, page_area: float) -> bool:
    """A scanned page with its own OCR text layer: plenty of text over a page-sized image."""
    return n_chars >= 200 and any(
        max(b[2] - b[0], 0.0) * max(b[3] - b[1], 0.0) >= page_area * 0.7 for b in image_boxes)


def _note_passes(result: dict, counts: Counter, scan_layer: bool) -> None:
    if counts:
        result["dropped"] = dict(counts)  # glyphs and lines removed as overprint or shadows
    if scan_layer:
        result["scan_layer"] = True


def _drop_scan_backgrounds(images: list[dict], n_chars: int, page_area: float) -> list[dict]:
    """A scanned page with an OCR text layer is a page-sized image under invisible text.

    The text is the content; the image is not a figure."""
    if n_chars < 200:
        return images
    return [im for im in images if (im["x1"] - im["x0"]) * (im["bot"] - im["top"]) < page_area * 0.7]


def _merge_overlapping(images: list[dict]) -> list[dict]:
    """Figures are often drawn as several image tiles; merge tiles that touch."""
    merged: list[dict] = []
    for im in sorted(images, key=lambda i: (i["top"], i["x0"])):
        for m in merged:
            if im["x0"] <= m["x1"] + 2 and im["x1"] >= m["x0"] - 2 and im["top"] <= m["bot"] + 2 and im["bot"] >= m["top"] - 2:
                m.update(x0=min(m["x0"], im["x0"]), x1=max(m["x1"], im["x1"]),
                         top=min(m["top"], im["top"]), bot=max(m["bot"], im["bot"]))
                break
        else:
            merged.append(dict(im))
    return merged


# ---------------------------------------------------------------------------
# Figures drawn with vector graphics, and text that belongs to a figure
# ---------------------------------------------------------------------------

GRAPHIC_GAP = 3.0  # vector shapes closer than this belong to the same drawing
FIGURE_NEAR = 12.0  # small labels this close to a drawing (axis ticks, legends) belong to it
SMALL_TEXT = 0.8  # text below this share of the page's body size reads as figure labels
MAX_CLUSTER_BOXES = 6000  # beyond this a page is all drawing; keep the work bounded


def _area(b: tuple[float, float, float, float]) -> float:
    return max(b[2] - b[0], 0.0) * max(b[3] - b[1], 0.0)


def _near(a, b, gap: float) -> bool:
    return a[0] <= b[2] + gap and b[0] <= a[2] + gap and a[1] <= b[3] + gap and b[1] <= a[3] + gap


def _union(a, b) -> list[float]:
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _cluster(boxes: list, gap: float) -> list[dict]:
    """Group boxes that touch (within `gap`) into clusters: union-find over a coarse grid."""
    parent = list(range(len(boxes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell = 24.0
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, b in enumerate(boxes):
        cx0, cx1 = int((b[0] - gap) // cell), int((b[2] + gap) // cell)
        cy0, cy1 = int((b[1] - gap) // cell), int((b[3] + gap) // cell)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                bucket = grid[(cx, cy)]
                for j in bucket:
                    if find(i) != find(j) and _near(b, boxes[j], gap):
                        parent[find(i)] = find(j)
                bucket.append(i)
    groups: dict[int, dict] = {}
    for i, b in enumerate(boxes):
        g = groups.setdefault(find(i), {"box": list(b), "n": 0})
        g["box"] = _union(g["box"], b)
        g["n"] += 1
    clusters = list(groups.values())
    merged = True
    while merged:  # growing boxes can come to touch each other
        merged = False
        out: list[dict] = []
        for cl in clusters:
            for o in out:
                if _near(o["box"], cl["box"], gap):
                    o["box"] = _union(o["box"], cl["box"])
                    o["n"] += cl["n"]
                    merged = True
                    break
            else:
                out.append(cl)
        clusters = out
    return clusters


def _line_box(ln: dict) -> tuple[float, float, float, float]:
    return (ln["x0"], ln["top"], ln["x1"], ln["bot"])


def _inside(ln: dict, region) -> bool:
    """Most of the line's box lies within the region."""
    x0, top, x1, bot = _line_box(ln)
    ix = min(x1, region[2] + 1) - max(x0, region[0] - 1)
    iy = min(bot, region[3] + 1) - max(top, region[1] - 1)
    if ix <= 0 or iy <= 0:
        return False
    return ix * iy >= 0.6 * max((x1 - x0) * (bot - top), 0.01)


def page_body_size(lines: list[dict]) -> float:
    """The type size that carries most of the page's characters."""
    weights: Counter = Counter()
    for ln in lines:
        weights[ln["sz"]] += len(ln["t"])
    return weights.most_common(1)[0][0] if weights else 10.0


def _is_caption(ln: dict) -> bool:
    """'Figure 3: …', 'Table 2.1 Smoking levels …' — but not 'Table 1.15 contains …',
    which is a sentence that refers to a table."""
    from .layout import CAPTION

    text = ln["t"].strip()
    m = CAPTION.match(text)
    if not m:
        return False
    rest = text[m.end():].lstrip(".0123456789 ")
    return not rest or not rest[0].islower()


def small_share(inside: list[dict], body: float) -> float:
    """Share of the characters that are set clearly smaller than the body text."""
    total = sum(len(ln["t"]) for ln in inside) or 1
    return sum(len(ln["t"]) for ln in inside if ln["sz"] < body * SMALL_TEXT) / total


def figure_text_ok(inside: list[dict], body: float, n_shapes: int = 1) -> bool:
    """Does the text inside a drawn area read as part of a figure rather than as prose?

    Figure text is small (labels, annotated examples), or short labels scattered over a
    drawing with many shapes (a diagram, a sunburst chart). A box around normal-size
    sentences (a sidebar, a note, a worked example) or around code is not a figure, and its
    text stays in the reading flow."""
    text = [ln for ln in inside if ln["t"].strip()]
    if not text:
        return True
    if prose_in_frame(text, n_shapes):
        return False  # a framed note or aside, even in footnote type: the author's prose
    total = sum(len(ln["t"]) for ln in text) or 1
    if sum(len(ln["t"]) for ln in text if ln.get("m") and ln["sz"] >= body * SMALL_TEXT) / total >= 0.5:
        return False  # a code listing in a box
    if small_share(text, body) >= 0.6:
        return True
    prose = sum(len(ln["t"]) for ln in text if ln["sz"] >= body * SMALL_TEXT and len(ln["t"].split()) >= 7)
    if n_shapes >= 100 and n_shapes >= 3 * len(text):
        # A dense drawing (a chart with a normal-size legend): only text that is mostly
        # sentences makes it a box of prose.
        return prose / total <= 0.6
    if prose / total > 0.3:
        return False
    words = sorted(len(ln["t"].split()) for ln in text)
    # Normal-size labels only count as figure text over a real drawing, not a box or two,
    # and not when they line up in rows and columns: that is a table with shaded rows.
    return (len(text) >= 3 and words[len(words) // 2] <= 3 and n_shapes >= 2 * len(text)
            and not _grid_aligned(text))


SENTENCE_WORDS = 6  # a line this long is running text, whatever its size; labels are shorter


def in_sentences(text: list[dict]) -> float:
    """Share of the (non-code) characters that sit in lines of sentence length."""
    prose = [ln for ln in text if not ln.get("m")]
    total = sum(len(ln["t"]) for ln in prose)
    if not total:
        return 0.0
    return sum(len(ln["t"]) for ln in prose if len(ln["t"].split()) >= SENTENCE_WORDS) / total


def prose_in_frame(text: list[dict], n_shapes: int) -> bool:
    """Running text in a frame: a note or aside, in footnote type or not. Lines of sentence
    length make up nearly all of it, or most of it inside a plain frame of a few shapes.
    (Diagrams also hold a few sentence-long examples among their labels.)"""
    share = in_sentences(text)
    return share >= 0.8 or (share >= 0.5 and n_shapes <= 12)


def body_size_text(text: list[dict], body: float, n_shapes: int, shapes: list | None = None) -> bool:
    """Is the text in a drawn region set at body size? Then the region is a frame around the
    author's text (a title page ornament, a boxed formula, an exercise grid), not a figure.

    Charts may label themselves at body size too. A dense one (a sunburst) stays a figure.
    So does a chart whose labels are mostly numbers set outside its shapes (ticks under the
    bars); an exercise grid sets its labels inside the drawn cells."""
    lines = [ln for ln in text if ln["t"].strip()]
    sizes = sorted(ln["sz"] for ln in lines)
    if not sizes:
        return False
    median = sizes[len(sizes) // 2]
    if median <= body * 0.85:
        return False
    if median > body * 1.05:
        return True  # a title, larger than the body: never a label
    if n_shapes >= 100 and n_shapes >= 3 * len(sizes) and len(sizes) >= 5:
        return False
    if shapes is None or n_shapes < 20 or n_shapes < 3 * len(lines):
        return True
    numeric = sum(1 for ln in lines if any(ch.isdigit() for ch in ln["t"])) / len(lines)
    return numeric < 0.4 or _in_cells(lines, shapes) >= 0.5


def _in_cells(lines: list[dict], shapes: list) -> float:
    """Share of the lines whose centre lies inside one of the drawing's own boxes (a cell),
    leaving out frames and backgrounds that span most of the drawing."""
    if not shapes:
        return 0.0
    x0 = min(b[0] for b in shapes)
    y0 = min(b[1] for b in shapes)
    x1 = max(b[2] for b in shapes)
    y1 = max(b[3] for b in shapes)
    limit = 0.5 * _area((x0, y0, x1, y1))
    cells = [b for b in shapes if _area(b) < limit and b[2] - b[0] > 2 and b[3] - b[1] > 2]
    inside = 0
    for ln in lines:
        cx, cy = (ln["x0"] + ln["x1"]) / 2, (ln["top"] + ln["bot"]) / 2
        inside += any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in cells)
    return inside / len(lines)


def _grid_aligned(text: list[dict]) -> bool:
    """Most lines share a row with another line and a column edge with another line."""
    def same_col(a: dict, b: dict) -> bool:
        return (abs(a["x0"] - b["x0"]) < 2 or abs(a["x1"] - b["x1"]) < 2
                or abs((a["x0"] + a["x1"]) - (b["x0"] + b["x1"])) < 4)

    aligned = 0
    for ln in text:
        others = [o for o in text if o is not ln]
        row = any(abs(o["top"] - ln["top"]) < 2 for o in others)
        col = any(same_col(o, ln) and abs(o["top"] - ln["top"]) >= 2 for o in others)
        aligned += row and col
    return aligned >= 0.7 * len(text)


def find_figures(lines: list[dict], images: list[dict], graphics: list, tables: list[dict],
                 w: float, h: float) -> tuple[list[dict], list[dict]]:
    """Turn drawings into figure regions and move the text drawn inside figures onto them.

    `images` are raster figures (already size-filtered); `graphics` are the boxes of every
    vector path and image on the page. Returns (lines left for the reading flow, figures).
    Each figure that had text inside gets it as "text" (reading order), for search and alt
    text; the words are kept, just no longer read as garbled body paragraphs."""
    page_area = w * h
    body = page_body_size(lines)
    shapes = [b for b in graphics
              if _area(b) < page_area * 0.5 and b[2] > 0 and b[3] > 0 and b[0] < w and b[1] < h]
    regions: list[dict] = []
    if 2 <= len(shapes) <= MAX_CLUSTER_BOXES:
        for cl in _cluster(shapes, GRAPHIC_GAP):
            box = [max(0.0, cl["box"][0]), max(0.0, cl["box"][1]), min(w, cl["box"][2]), min(h, cl["box"][3])]
            # Size is checked again after the labels around the drawing have joined it.
            if cl["n"] < 2 or max(box[2] - box[0], box[3] - box[1]) < MIN_FIGURE_SIDE or _area(box) > page_area * 0.75:
                continue
            if any(_overlap_share(box, t["bbox"]) > 0.3 for t in tables):
                continue  # a ruled table: pdfplumber reads its cells
            regions.append({"box": box, "n": cl["n"], "vector": True})
    for im in images:
        regions.append({"box": [im["x0"], im["top"], im["x1"], im["bot"]], "n": 1, "vector": False, "im": im})
    for region in regions:
        _trim_at_captions(region, lines)
    # Body size from text outside drawings: a big figure full of small labels must not make
    # its labels look like the page's body text.
    outside = [ln for ln in lines if not any(_inside(ln, r["box"]) for r in regions)]
    body = page_body_size(outside) if sum(len(ln["t"]) for ln in outside) >= 200 else body
    caption_lines = _caption_continuations(lines)

    def grow(region: dict) -> list[int]:
        """Indexes of lines that belong to the region, growing it over nearby small labels."""
        box = region["box"]
        members: set[int] = set()
        for _ in range(3):
            added = False
            for i, ln in enumerate(lines):
                if i in members or _is_caption(ln):
                    continue
                # A label next to a drawing joins it; the second line of its caption doesn't.
                if _inside(ln, box) or (
                    region["vector"] and ln["sz"] < body * SMALL_TEXT and i not in caption_lines
                    and _near(box, _line_box(ln), FIGURE_NEAR) and (ln["x1"] - ln["x0"]) < (box[2] - box[0]) * 1.2
                ):
                    members.add(i)
                    box = _union(box, _line_box(ln))
                    added = True
            if not added:
                break
        region["grown"] = box
        return sorted(members)

    accepted: list[dict] = []
    for region in regions:
        members = grow(region)
        inside = [lines[i] for i in members]
        if region["vector"]:
            if not inside and region["n"] < 3:
                continue
            own = [b for b in shapes if _overlap_share(b, region["grown"]) > 0.9]
            if body_size_text(inside, body, region["n"], own) or not figure_text_ok(inside, body, region["n"]):
                continue
            # Aligned text with rules or shaded rows around it is a table. Small value labels
            # aligned over a chart's many bars and gridlines are still a chart.
            if (small_share(inside, body) < 0.6 or region["n"] < 30) and _looks_like_table(inside):
                continue
            g = region["grown"]
            if not page_area * MIN_FIGURE_AREA_RATIO <= _area(g) <= page_area * 0.75:
                continue
            short, long = sorted((g[2] - g[0], g[3] - g[1]))
            if short < MIN_FIGURE_SIDE * (0.66 if inside else 1.0) or long > 8 * short:
                continue  # rules, bars and banner strips are decoration, not figures
        elif inside and (not figure_text_ok(inside, body) or _area(region["box"]) > page_area * 0.5):
            # An image behind prose, or a scanned page under its own text layer: the text
            # stays in the reading flow.
            members = []
        region["members"] = set(members)
        accepted.append(region)

    # Neighbouring parts of one drawing (boxes of a diagram, panels of a chart) become one figure.
    figures: list[dict] = []
    for region in sorted(accepted, key=lambda r: (r["grown"][1], r["grown"][0])):
        for f in figures:
            if _near(f["grown"], region["grown"], 6.0) and not _text_between(f["grown"], region["grown"], lines, f["members"] | region["members"]):
                f["grown"] = _union(f["grown"], region["grown"])
                f["members"] |= region["members"]
                f["vector"] = f["vector"] or region["vector"]
                break
        else:
            figures.append(region)

    taken: set[int] = set()
    out_figs: list[dict] = []
    for f in figures:
        x0, top, x1, bot = f["grown"]
        entry: dict[str, Any] = {"x0": max(0.0, x0 - 2), "top": max(0.0, top - 2), "x1": min(w, x1 + 2), "bot": min(h, bot + 2)}
        if f["vector"]:
            entry["vector"] = True
        if "im" in f and "i" in f["im"]:
            entry["i"] = f["im"]["i"]
        members = sorted(f["members"] - taken, key=lambda i: (lines[i]["top"], lines[i]["x0"]))
        taken |= set(members)
        text = " ".join(lines[i]["t"].strip() for i in members if lines[i]["t"].strip())
        if text:
            entry["text"] = text
        out_figs.append(entry)
    return [ln for i, ln in enumerate(lines) if i not in taken], out_figs


def _caption_continuations(lines: list[dict]) -> set[int]:
    """Indexes of the lines that carry on a caption: each sits right under the caption (or
    under its previous line), at its size, starting near its left edge."""
    order = sorted(range(len(lines)), key=lambda i: (lines[i]["top"], lines[i]["x0"]))
    out: set[int] = set()
    heads = [i for i in order if _is_caption(lines[i])]
    for h in heads:
        prev = lines[h]
        for j in order:
            ln = lines[j]
            if j == h or j in out or ln["top"] <= prev["top"]:
                continue
            gap = ln["top"] - prev["bot"]
            if (-1.0 <= gap <= 0.8 * prev["sz"] and abs(ln["sz"] - prev["sz"]) <= 0.5
                    and abs(ln["x0"] - lines[h]["x0"]) <= 2 * prev["sz"] and not _is_caption(ln)):
                out.add(j)
                prev = ln
            elif ln["top"] > prev["bot"] + 2 * prev["sz"]:
                break
    return out


def _trim_at_captions(region: dict, lines: list[dict]) -> None:
    """A caption marks the edge of its figure: drawing bounds that reach past it (invisible
    backgrounds, unclipped shapes) are cut back to the caption."""
    box = region["box"]
    mid = (box[1] + box[3]) / 2
    for ln in lines:
        if not _is_caption(ln) or not _inside(ln, box):
            continue
        if ln["top"] >= mid:
            box[3] = min(box[3], ln["top"] - 1)
        else:
            box[1] = max(box[1], ln["bot"] + 1)


def _looks_like_table(inside: list[dict]) -> bool:
    """Text in a grid (a table drawn with a few rules) is a table, not a figure."""
    from .layout import _to_line, find_text_tables

    if len(inside) < 6:
        return False
    lns = [_to_line(d, 0) for d in inside]
    tables, rest = find_text_tables(lns)
    return bool(tables) and len(rest) <= 0.4 * len(lns)


def _overlap_share(a, b) -> float:
    """Share of box a covered by box b."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    return ix * iy / max(_area(a), 0.01)


def _text_between(a, b, lines: list[dict], members: set[int]) -> bool:
    """Would joining two regions swallow flow text that sits beside or between them?"""
    joined = _union(a, b)
    for i, ln in enumerate(lines):
        if i in members or not _inside(ln, joined):
            continue
        if not (_inside(ln, a) or _inside(ln, b)):
            return True
    return False


def plausible_table(rows: list[list[str]]) -> bool:
    """pdfplumber also finds 'tables' in the gridlines and bars of charts: dozens of columns,
    almost every cell empty. Those are drawings, and figure detection handles them."""
    if len(rows) < 2 or max(len(r) for r in rows) < 2:
        return False
    cells = sum(len(r) for r in rows)
    filled = sum(1 for r in rows for c in r if c)
    return filled >= 4 and filled >= 0.3 * cells


def _find_tables(plumber_pdf, index: int) -> list[dict]:
    page = plumber_pdf.pages[index]
    out = []
    try:
        x_off, y_off = float(page.bbox[0]), float(page.bbox[1])
        if len(page.lines) + len(page.rects) < 6:
            return out
        for t in page.find_tables():
            rows = [[(cell or "").strip() for cell in r] for r in t.extract() if r]
            if plausible_table(rows):
                bx0, btop, bx1, bbot = t.bbox
                out.append({"bbox": [bx0 - x_off, btop - y_off, bx1 - x_off, bbot - y_off], "rows": rows})
    except Exception as exc:
        log.debug("table detection failed on page %s: %s", index + 1, exc)
    finally:
        try:
            page.close()
        except Exception:  # noqa: S110
            pass
    return out


def _plumber_visible(o: dict) -> bool:
    """pdfplumber twin of pdfium_chars._visible_path: skip unstroked white or unpainted shapes."""
    if o.get("stroke"):
        return True
    if not o.get("fill"):
        return False
    color = o.get("non_stroking_color")
    if isinstance(color, (int, float)):
        color = (color,)
    if isinstance(color, (list, tuple)) and color and all(isinstance(v, (int, float)) for v in color):
        if len(color) in (1, 3) and min(color) >= 0.98:
            return False  # gray or RGB white
        if len(color) == 4 and max(color) <= 0.02:
            return False  # CMYK white
    return True


def _extract_page_plumber(plumber_pdf, pdfium_doc, index: int, assets_dir: Path, ocr=None) -> dict:
    """Extract one page (0-based index) into a JSON-able dict."""
    page = plumber_pdf.pages[index]
    try:
        w, h = float(page.width), float(page.height)
        x_off, y_off = float(page.bbox[0]), float(page.bbox[1])
        try:
            dpage = page.dedupe_chars(tolerance=1)
            chars = list(dpage.chars)
        except Exception:
            chars = list(page.chars)
        for c in chars:  # normalise to page-relative coordinates
            c["x0"] -= x_off
            c["x1"] -= x_off
            c["top"] -= y_off
            c["bottom"] -= y_off
        page_area = w * h
        image_boxes = [(float(im["x0"]) - x_off, float(im["top"]) - y_off, float(im["x1"]) - x_off,
                        float(im["bottom"]) - y_off) for im in page.images]
        scan_layer = _is_scan_layer(len(chars), image_boxes, page_area)
        counts: Counter = Counter()
        lines = lines_from_chars(chars, counts, scan_layer)

        images = []
        covered = 0.0
        for i, im in enumerate(page.images):
            x0, x1 = float(im["x0"]) - x_off, float(im["x1"]) - x_off
            top, bot = float(im["top"]) - y_off, float(im["bottom"]) - y_off
            iw, ih = x1 - x0, bot - top
            if iw <= 0 or ih <= 0:
                continue
            covered += min(iw * ih, page_area)
            if iw * ih < page_area * MIN_FIGURE_AREA_RATIO or min(iw, ih) < MIN_FIGURE_SIDE:
                continue
            images.append({"x0": x0, "x1": x1, "top": top, "bot": bot, "i": i})

        n_chars = sum(len(ln["t"]) for ln in lines)
        scanned = n_chars < 20 and covered > page_area * 0.5
        images = _drop_scan_backgrounds(images, n_chars, page_area)

        tables = []
        if not scanned and len(page.lines) + len(page.rects) >= 6:
            try:
                for t in page.find_tables():
                    rows = t.extract()
                    rows = [[(cell or "").strip() for cell in r] for r in rows if r]
                    if plausible_table(rows):
                        bx0, btop, bx1, bbot = t.bbox
                        tables.append(
                            {
                                "bbox": [bx0 - x_off, btop - y_off, bx1 - x_off, bbot - y_off],
                                "rows": rows,
                            }
                        )
            except Exception as exc:
                log.debug("table detection failed on page %s: %s", index + 1, exc)

        images = _merge_overlapping(images)
        if not scanned:
            graphics = [
                (float(o["x0"]) - x_off, float(o["top"]) - y_off, float(o["x1"]) - x_off, float(o["bottom"]) - y_off)
                for o in (*page.rects, *page.lines, *page.curves, *page.images)
                if "stream" in o or _plumber_visible(o)
            ]
            lines, images = find_figures(lines, images, graphics, tables, w, h)

        result: dict[str, Any] = {
            "n": index + 1,
            "w": round(w, 2),
            "h": round(h, 2),
            "lines": lines,
            "images": [],
            "tables": tables,
            "scanned": scanned,
            "ocr": False,
        }
        _note_passes(result, counts, scan_layer)
        return _finish_page(result, images, pdfium_doc, index, assets_dir, ocr, w, h)
    finally:
        try:
            page.close()
        except Exception:  # noqa: S110
            pass
