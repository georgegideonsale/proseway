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
_OBJ_FORM = raw.FPDF_PAGEOBJ_FORM


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


Box = tuple[float, float, float, float]  # x0, top, x1, bottom in top-left page coordinates
_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
MAX_GRAPHIC_OBJECTS = 20_000  # a pathological page can hold millions of paths; stop counting


def _compose(outer: tuple, inner: tuple) -> tuple:
    """Matrix product outer x inner for PDF matrices (a, b, c, d, e, f)."""
    a1, b1, c1, d1, e1, f1 = inner
    a2, b2, c2, d2, e2, f2 = outer
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2, c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)


def _transform_box(m: tuple, left: float, bottom: float, right: float, top: float) -> tuple[float, float, float, float]:
    a, b, c, d, e, f = m
    xs, ys = [], []
    for x, y in ((left, bottom), (left, top), (right, bottom), (right, top)):
        xs.append(a * x + c * y + e)
        ys.append(b * x + d * y + f)
    return min(xs), min(ys), max(xs), max(ys)


def _clip_box(obj) -> tuple[float, float, float, float] | None:
    """Bounding box of an object's clip path, in the same space as its bounds."""
    cp = raw.FPDFPageObj_GetClipPath(obj)
    if not cp:
        return None
    x, y = ctypes.c_float(), ctypes.c_float()
    xs: list[float] = []
    ys: list[float] = []
    for i in range(raw.FPDFClipPath_CountPaths(cp)):
        for j in range(raw.FPDFClipPath_CountPathSegments(cp, i)):
            seg = raw.FPDFClipPath_GetPathSegment(cp, i, j)
            if seg and raw.FPDFPathSegment_GetPoint(seg, x, y):
                xs.append(x.value)
                ys.append(y.value)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _visible_path(obj) -> bool:
    """False for paths that draw nothing you can see on white paper.

    Plotting libraries put a white rectangle behind every chart (often page-sized, inside an
    embedded form); counting those as drawings would turn the text around them into figures."""
    fill_mode, stroke = ctypes.c_int(), ctypes.c_int()
    if not raw.FPDFPath_GetDrawMode(obj, fill_mode, stroke):
        return True
    if stroke.value:
        return True
    if fill_mode.value == 0:
        return False  # neither filled nor stroked: only used for clipping
    r, g, b, a = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    painted = raw.FPDFPageObj_GetFillColor(obj, r, g, b, a)
    return not (painted and (a.value == 0 or min(r.value, g.value, b.value) >= 250))


def page_objects(page: pdfium.PdfPage) -> tuple[int, list[Box], list[Box]]:
    """Count vector paths and return (n_paths, image boxes, path boxes).

    Objects inside Form XObjects report their bounds in the form's own coordinate space, so
    we walk the object tree ourselves and apply each form's matrix on the way down. (Papers
    made with LaTeX embed most figures as forms; without this, their images land off-page.)
    """
    w, h = page.get_size()
    try:
        cl, cb, _cr, _ct = page.get_cropbox()
    except Exception:
        cl, cb = 0.0, 0.0
    n_paths = 0
    images: list[Box] = []
    paths: list[Box] = []
    fl, fb, fr, ft = ctypes.c_float(), ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
    matrix = raw.FS_MATRIX()
    seen = 0

    def to_page(m: tuple, obj) -> Box | None:
        if not raw.FPDFPageObj_GetBounds(obj, fl, fb, fr, ft):
            return None
        left, bottom, right, top = fl.value, fb.value, fr.value, ft.value
        clip = _clip_box(obj)
        if clip is not None:  # what is drawn outside the clip path is invisible
            left, bottom = max(left, clip[0]), max(bottom, clip[1])
            right, top = min(right, clip[2]), min(top, clip[3])
            if right <= left or top <= bottom:
                return None
        left, bottom, right, top = _transform_box(m, left, bottom, right, top)
        return (left - cl, h - (top - cb), right - cl, h - (bottom - cb))

    def walk(objs, m: tuple, depth: int) -> None:
        nonlocal n_paths, seen
        for obj in objs:
            seen += 1
            if seen > MAX_GRAPHIC_OBJECTS:
                return
            kind = raw.FPDFPageObj_GetType(obj)
            if kind == _OBJ_PATH:
                n_paths += 1
                if not _visible_path(obj):
                    continue
                box = to_page(m, obj)
                if box is not None:
                    paths.append(box)
            elif kind == _OBJ_IMAGE:
                box = to_page(m, obj)
                if box is not None:
                    images.append(box)
            elif kind == _OBJ_FORM and depth < 4:
                fm = m
                if raw.FPDFPageObj_GetMatrix(obj, matrix):
                    fm = _compose(m, (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f))
                n = raw.FPDFFormObj_CountObjects(obj)
                walk((raw.FPDFFormObj_GetObject(obj, k) for k in range(max(n, 0))), fm, depth + 1)

    top_level = raw.FPDFPage_CountObjects(page.raw)
    walk((raw.FPDFPage_GetObject(page.raw, k) for k in range(max(top_level, 0))), _IDENTITY, 0)
    _ = w
    return n_paths, images, paths
