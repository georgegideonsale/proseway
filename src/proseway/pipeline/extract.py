"""Stage 1: per-page extraction of positioned lines, images and tables.

The output of this stage is deliberately plain JSON so that each finished page can be
written to disk as a checkpoint. Resuming a conversion means skipping pages whose JSON
already exists.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter
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
        meta: dict[str, Any] = {"title": "", "author": "", "language": "", "pages": len(doc), "outline": []}
        try:
            m = doc.get_metadata_dict()
            meta["title"] = (m.get("Title") or "").strip()
            meta["author"] = (m.get("Author") or "").strip()
        except Exception:  # noqa: S110 - metadata is optional
            pass
        try:  # the document catalog's /Lang, e.g. "en-GB" (UTF-16LE with a terminating NUL)
            import ctypes

            import pypdfium2.raw as pdfium_c

            n = pdfium_c.FPDFCatalog_GetLanguage(doc.raw, None, 0)
            if 2 < n <= 256:
                buf = (ctypes.c_ushort * (n // 2))()
                pdfium_c.FPDFCatalog_GetLanguage(doc.raw, buf, n)
                meta["language"] = bytes(buf).decode("utf-16-le", "ignore").rstrip("\x00").strip()
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


def _split_segments(row: list[dict]) -> list[list[dict]]:
    """Split a row where a large horizontal gap separates columns or table cells."""
    sizes = [c["size"] for c in row if c["text"].strip()]
    size = _median(sizes, 10.0)
    segments: list[list[dict]] = [[]]
    prev = None
    for ch in row:
        if prev is not None and ch["x0"] - prev["x1"] > max(1.6 * size, 9.0):
            segments.append([])
        segments[-1].append(ch)
        if ch["text"].strip():
            prev = ch
    return [s for s in segments if any(c["text"].strip() for c in s)]


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


def lines_from_chars(chars: list[dict]) -> list[dict]:
    for c in chars:
        if c.get("text"):
            c["text"] = _clean_char_text(c["text"])
    upright = [c for c in chars if c.get("upright", True) and c.get("text")]
    lines: list[dict] = []
    for row in _rows_from_chars(upright):
        for seg in _split_segments(row):
            line = _build_line(seg)
            if line is not None:
                lines.append(line)
    return lines


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
        if _render_crop(pdfium_doc, index, (im["x0"], im["top"], im["x1"], im["bot"]), w, h, assets_dir / name):
            entry = {key: round(v, 2) if isinstance(v, float) else v for key, v in im.items() if key != "i"}
            entry["file"] = name
            result["images"].append(entry)
    return result


def _extract_page_pdfium(src: Source, index: int, assets_dir: Path, ocr=None) -> dict:
    from .pdfium_chars import page_chars, page_objects

    page = src.pdfium[index]
    try:
        chars, w, h = page_chars(page)
        n_paths, image_boxes = page_objects(page)
    finally:
        page.close()
    lines = lines_from_chars(chars)
    page_area = w * h
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
    result: dict[str, Any] = {"n": index + 1, "w": round(w, 2), "h": round(h, 2), "lines": lines,
                              "images": [], "tables": tables, "scanned": scanned, "ocr": False}
    return _finish_page(result, images, src.pdfium, index, assets_dir, ocr, w, h)


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


def _find_tables(plumber_pdf, index: int) -> list[dict]:
    page = plumber_pdf.pages[index]
    out = []
    try:
        x_off, y_off = float(page.bbox[0]), float(page.bbox[1])
        if len(page.lines) + len(page.rects) < 6:
            return out
        for t in page.find_tables():
            rows = [[(cell or "").strip() for cell in r] for r in t.extract() if r]
            if len(rows) >= 2 and max(len(r) for r in rows) >= 2 and sum(1 for r in rows for c in r if c) >= 4:
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
        lines = lines_from_chars(chars)

        images = []
        page_area = w * h
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
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        bx0, btop, bx1, bbot = t.bbox
                        tables.append(
                            {
                                "bbox": [bx0 - x_off, btop - y_off, bx1 - x_off, bbot - y_off],
                                "rows": rows,
                            }
                        )
            except Exception as exc:
                log.debug("table detection failed on page %s: %s", index + 1, exc)

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
        return _finish_page(result, _merge_overlapping(images), pdfium_doc, index, assets_dir, ocr, w, h)
    finally:
        try:
            page.close()
        except Exception:  # noqa: S110
            pass
