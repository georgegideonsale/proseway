"""Fast character extraction with PDFium (via pypdfium2, Apache-2.0/BSD).

Produces the same character records as pdfplumber (text, fontname, size, x0, x1, top,
bottom, upright) so the line builder and layout stages don't care which engine ran.
In our benchmark this is several times faster than pdfminer-based extraction.
"""

from __future__ import annotations

import ctypes
import math

import pypdfium2 as pdfium
import pypdfium2.raw as raw

# Path objects count as "ruling lines" for deciding whether to look for tables.
_OBJ_PATH = raw.FPDF_PAGEOBJ_PATH
_OBJ_IMAGE = raw.FPDF_PAGEOBJ_IMAGE


def _font_name(textpage, index: int, cache: dict, buf) -> str:
    obj = raw.FPDFText_GetTextObject(textpage, index)
    key = ctypes.cast(obj, ctypes.c_void_p).value if obj else None
    if key is not None and key in cache:
        return cache[key]
    name = ""
    if obj:
        font = raw.FPDFTextObj_GetFont(obj)
        if font:
            n = raw.FPDFFont_GetBaseFontName(font, buf, len(buf))
            if n > 0:
                name = bytes(buf[: max(0, n - 1)]).decode("utf-8", "replace")
    if not name:
        flags = ctypes.c_int()
        n = raw.FPDFText_GetFontInfo(textpage, index, buf, len(buf), ctypes.byref(flags))
        if n > 0:
            name = bytes(buf[: max(0, n - 1)]).decode("utf-8", "replace")
    if key is not None:
        cache[key] = name
    return name


def _scale(textpage, index: int, cache: dict) -> float:
    """Vertical scale of the character's matrix: font size 1 scaled by the matrix is common."""
    obj = raw.FPDFText_GetTextObject(textpage, index)
    key = ctypes.cast(obj, ctypes.c_void_p).value if obj else None
    if key is not None and key in cache:
        return cache[key]
    m = raw.FS_MATRIX()
    scale = 1.0
    if raw.FPDFText_GetMatrix(textpage, index, m):
        scale = math.hypot(m.c, m.d) or 1.0
    if key is not None:
        cache[key] = scale
    return scale


def page_chars(page: pdfium.PdfPage) -> tuple[list[dict], float, float]:
    """Return (chars, width, height) for a page, in top-left page coordinates."""
    w, h = page.get_size()
    try:
        left, bottom, _right, _top = page.get_cropbox()
    except Exception:
        left, bottom = 0.0, 0.0
    tp = page.get_textpage()
    t = tp.raw
    n = raw.FPDFText_CountChars(t)
    rect = raw.FS_RECTF()
    cache: dict = {}
    scale_cache: dict = {}
    buf = (ctypes.c_char * 256)()
    chars: list[dict] = []
    try:
        pending_high = 0
        for i in range(n):
            u = raw.FPDFText_GetUnicode(t, i)
            # PDFium reports UTF-16 code units: rebuild characters outside the BMP (e.g.
            # mathematical alphanumerics) from surrogate pairs, and drop strays.
            if 0xD800 <= u <= 0xDBFF:
                pending_high = u
                continue
            if 0xDC00 <= u <= 0xDFFF:
                if not pending_high:
                    continue
                u = 0x10000 + ((pending_high - 0xD800) << 10) + (u - 0xDC00)
                pending_high = 0
            else:
                pending_high = 0
            if u == 2:  # PDFium marks hyphens at line ends with U+0002
                text = "-"
            elif u in (0, 0xFFFE, 0xFFFF):
                continue
            else:
                try:
                    text = chr(u)
                except ValueError:
                    continue
            if text in ("\r", "\n"):
                continue
            if raw.FPDFText_IsGenerated(t, i) == 1 and text == " ":
                # PDFium's inferred spaces are useful; keep them but they carry no box.
                chars.append({"text": " ", "fontname": "", "size": 0.0, "x0": -1, "x1": -1,
                              "top": -1, "bottom": -1, "upright": True, "generated": True})
                continue
            if not raw.FPDFText_GetLooseCharBox(t, i, rect):
                continue
            x0, x1 = rect.left - left, rect.right - left
            top, bot = h - (rect.top - bottom), h - (rect.bottom - bottom)
            if x1 < x0:
                x0, x1 = x1, x0
            if bot < top:
                top, bot = bot, top
            angle = raw.FPDFText_GetCharAngle(t, i)
            upright = angle < 0 or min(abs(angle), abs(angle - 2 * math.pi)) < 0.05
            size = raw.FPDFText_GetFontSize(t, i) * _scale(t, i, scale_cache)
            chars.append({
                "text": text,
                "fontname": _font_name(t, i, cache, buf),
                "size": round(size if size > 0 else (bot - top) * 0.8, 2),
                "x0": x0, "x1": x1, "top": top, "bottom": bot,
                "upright": upright,
            })
    finally:
        tp.close()
    # Generated spaces get the position of their left neighbour so sorting keeps them inline.
    out: list[dict] = []
    for i, c in enumerate(chars):
        if c.get("generated"):
            prev = chars[i - 1] if i > 0 else None
            if prev is None or prev.get("generated"):
                continue
            c.update(x0=prev["x1"], x1=prev["x1"] + 0.01, top=prev["top"], bottom=prev["bottom"],
                     size=prev["size"], fontname=prev["fontname"])
        out.append(c)
    return out, w, h


def page_objects(page: pdfium.PdfPage) -> tuple[int, list[tuple[float, float, float, float]]]:
    """Count vector path objects and return image boxes (x0, top, x1, bottom)."""
    _w, h = page.get_size()
    n_paths = 0
    images: list[tuple[float, float, float, float]] = []
    for obj in page.get_objects(filter=(_OBJ_PATH, _OBJ_IMAGE), max_depth=2):
        if obj.type == _OBJ_PATH:
            n_paths += 1
        else:
            try:
                left, bottom, right, top = obj.get_bounds()
            except Exception:  # noqa: S112 - an object without bounds is simply skipped
                continue
            images.append((left, h - top, right, h - bottom))
    return n_paths, images
