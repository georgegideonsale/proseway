"""Stage 2: whole-book layout analysis that turns positioned lines into reading blocks.

Faithfulness rule: blocks contain the PDF's own words in the PDF's own order. We only remove
layout artefacts (running headers/footers, printed page numbers, line-break hyphens) and
never rewrite text.
"""

from __future__ import annotations

import hashlib
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

PAGE_NUMBER = re.compile(
    r"^[\s\-–—|·•\[\(]*(?:page\s+|p\.\s*)?(?:\d{1,4}|[ivxlcdm]{1,8})"
    r"(?:\s*(?:/|of)\s*\d{1,4})?[\s\-–—|·•\]\)]*$",
    re.I,
)
BULLET = re.compile(r"^(?:[•◦▪▫‣⁃●○■□\-–—*]|\(?\d{1,3}[.)]|\(?[a-z][.)]|\(?[ivx]{1,5}[.)])\s+", re.I)
CAPTION = re.compile(r"^(?:figure|fig\.|table|plate|chart|diagram|exhibit|map|listing)\s*[\dIVXLC]+", re.I)
FOOTNOTE_MARK = re.compile(r"^\s*(\d{1,3}|[*†‡§¶‖#]{1,3}|[a-z])(?=[\s.)\]]|[A-Z])")
TERMINAL = re.compile(r"[.!?:;…\"”’)\]»]$")
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
MATH_SYMBOLS = set("=+−×÷±∓∑∏∫∮∂∇√∞≤≥≠≈≡∈∉⊂⊃⊆⊇∪∩∀∃→←↔⇒⇔^_αβγδεθλμπσφωΓΔΘΛΠΣΦΨΩ")


@dataclass
class Line:
    text: str
    x0: float
    x1: float
    top: float
    bot: float
    size: float
    font: str
    bold: bool
    italic: bool
    mono: bool
    math: float
    spans: list[list[Any]]
    page: int
    col: str = "full"  # left | right | full
    col_x0: float = 0.0
    col_x1: float = 0.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass
class Block:
    type: str  # heading | paragraph | footnote | list_item | code | equation | figure | caption | table | page_image
    page: int
    text: str = ""
    level: int = 0
    spans: list[list[Any]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    lines: list[Line] = field(default_factory=list)
    id: str = ""
    chapter: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_for_id(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def running_key(text: str) -> str:
    t = text.casefold()
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"\b[ivxlcdm]{1,8}\b", "#", t)
    return re.sub(r"[\W_]+", "", t.replace("#", "0"))


def _mode(values: list[float], default: float) -> float:
    if not values:
        return default
    return Counter(values).most_common(1)[0][0]


def _to_line(d: dict, page: int) -> Line:
    return Line(
        text=d["t"], x0=d["x0"], x1=d["x1"], top=d["top"], bot=d["bot"], size=d["sz"],
        font=d.get("font", ""), bold=d.get("b", False), italic=d.get("i", False),
        mono=d.get("m", False), math=d.get("mt", 0.0), spans=[list(s) for s in d.get("sp", [])],
        page=page,
    )


# ---------------------------------------------------------------------------
# Book-level statistics
# ---------------------------------------------------------------------------


@dataclass
class BookStats:
    body_size: float
    heading_sizes: list[float]
    vocab: Counter
    indent_style: bool


def compute_stats(pages: list[list[Line]]) -> BookStats:
    weighted: Counter = Counter()
    for lines in pages:
        for ln in lines:
            weighted[round(ln.size * 2) / 2] += len(ln.text)
    body = weighted.most_common(1)[0][0] if weighted else 10.0
    big = sorted({s for s, n in weighted.items() if s >= body * 1.18 and n >= 3}, reverse=True)
    vocab: Counter = Counter()
    for lines in pages:
        for ln in lines:
            text = ln.text[:-1] if ln.text.endswith("-") else ln.text
            for w in WORD.findall(text):
                vocab[w.casefold()] += 1
    return BookStats(body_size=body, heading_sizes=big[:4], vocab=vocab, indent_style=False)


# ---------------------------------------------------------------------------
# Running headers, footers and page numbers
# ---------------------------------------------------------------------------


def remove_running_elements(pages: list[list[Line]], heights: list[float], body: float,
                            removed: Counter) -> list[list[Line]]:
    """Drop lines in the top/bottom margins that repeat on nearby pages or are page numbers."""
    zones: list[list[tuple[int, str, str]]] = []  # per page: (line idx, zone, key)
    for lines, h in zip(pages, heights, strict=True):
        cand = []
        if lines:
            ordered = sorted(range(len(lines)), key=lambda i: lines[i].top)
            top_idx = set(ordered[:3])
            bot_idx = set(ordered[-3:])
            # Body extent, to recognise lines that sit apart in the margins.
            for i, ln in enumerate(lines):
                if ln.size > body * 1.3:
                    continue
                if i in top_idx and ln.top < h * 0.16:
                    cand.append((i, "top", running_key(ln.text)))
                elif i in bot_idx and ln.bot > h * 0.80:
                    cand.append((i, "bot", running_key(ln.text)))
        zones.append(cand)

    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for p, cand in enumerate(zones):
        for _i, zone, key in cand:
            if key:
                by_key[(zone, key)].append(p)

    out: list[list[Line]] = []
    for p, (lines, cand) in enumerate(zip(pages, zones, strict=True)):
        drop: set[int] = set()
        for i, zone, key in cand:
            text = lines[i].text.strip()
            if PAGE_NUMBER.match(text):
                drop.add(i)
                removed["page_numbers"] += 1
                continue
            if not key:
                continue
            hits = by_key[(zone, key)]
            # Repeats on at least two other pages within a window of +-8 pages, or on
            # a large share of the whole book.
            near = sum(1 for q in hits if q != p and abs(q - p) <= 8)
            if near >= 2 or (len(hits) >= 4 and len(hits) >= 0.3 * len(pages)) or _fuzzy_running(
                key, zone, p, zones
            ):
                drop.add(i)
                removed["running_lines"] += 1
        out.append([ln for i, ln in enumerate(lines) if i not in drop])
    return out


def _fuzzy_running(key: str, zone: str, p: int, zones: list[list[tuple[int, str, str]]]) -> bool:
    """Scanned books with an OCR text layer spell their running heads slightly differently on
    every page ("THE DECLINE AND FALL" / "TIIE DECLINE AND FALL"). Accept near-matches in the
    same margin on pages of the same parity (recto/verso) nearby."""
    from rapidfuzz import fuzz

    if len(key) < 8:
        return False
    matches = 0
    for q in (p - 2, p + 2, p - 4, p + 4, p - 1, p + 1):
        if 0 <= q < len(zones):
            for _i, z, k in zones[q]:
                if z == zone and len(k) >= 8 and fuzz.ratio(key, k) >= 75:
                    matches += 1
                    break
        if matches >= 2:
            return True
    return False


# ---------------------------------------------------------------------------
# Reading order (columns)
# ---------------------------------------------------------------------------


def classify_columns(lines: list[Line]) -> bool:
    """Mark each line left / right / full and say whether the page is set in two columns."""
    if not lines:
        return False
    left_edge = min(ln.x0 for ln in lines)
    right_edge = max(ln.x1 for ln in lines)
    width = max(right_edge - left_edge, 1.0)
    mid = (left_edge + right_edge) / 2
    slack = width * 0.03
    for ln in lines:
        if ln.x1 <= mid + slack and ln.width < width * 0.6:
            ln.col = "left"
        elif ln.x0 >= mid - slack and ln.width < width * 0.6:
            ln.col = "right"
        else:
            ln.col = "full"
    n_left = sum(1 for ln in lines if ln.col == "left")
    n_right = sum(1 for ln in lines if ln.col == "right")
    right_starts = [round(ln.x0) for ln in lines if ln.col == "right"]
    return bool(
        n_left >= 5 and n_right >= 5
        and right_starts
        and Counter(right_starts).most_common(1)[0][1] >= max(3, n_right * 0.3)
    )


def order_page(lines: list[Line], page_w: float) -> list[Line]:
    if not lines:
        return lines
    left_edge = min(ln.x0 for ln in lines)
    right_edge = max(ln.x1 for ln in lines)
    mid = (left_edge + right_edge) / 2
    two_col = classify_columns(lines)
    if not two_col:
        for ln in lines:
            ln.col = "full"
            ln.col_x0, ln.col_x1 = left_edge, right_edge
        ordered = sorted(lines, key=lambda ln: (round(ln.top / 2), ln.x0))
        return _merge_same_baseline(ordered)

    left_x1 = max((ln.x1 for ln in lines if ln.col == "left"), default=mid)
    right_x0 = min((ln.x0 for ln in lines if ln.col == "right"), default=mid)
    for ln in lines:
        if ln.col == "left":
            ln.col_x0, ln.col_x1 = left_edge, left_x1
        elif ln.col == "right":
            ln.col_x0, ln.col_x1 = right_x0, right_edge
        else:
            ln.col_x0, ln.col_x1 = left_edge, right_edge

    ordered: list[Line] = []
    band_left: list[Line] = []
    band_right: list[Line] = []

    def flush() -> None:
        ordered.extend(sorted(band_left, key=lambda ln: ln.top))
        ordered.extend(sorted(band_right, key=lambda ln: ln.top))
        band_left.clear()
        band_right.clear()

    for ln in sorted(lines, key=lambda ln: (ln.top, ln.x0)):
        if ln.col == "full":
            flush()
            ordered.append(ln)
        elif ln.col == "left":
            band_left.append(ln)
        else:
            band_right.append(ln)
    flush()
    return ordered


def _merge_same_baseline(lines: list[Line]) -> list[Line]:
    """In single-column pages, rejoin segments that share a baseline (e.g. 'Title .... 12')."""
    out: list[Line] = []
    for ln in lines:
        prev = out[-1] if out else None
        if (
            prev is not None
            and abs(prev.top - ln.top) < 1.5
            and abs(prev.size - ln.size) < 0.6
            and ln.x0 > prev.x1
            and not prev.mono
        ):
            offset = len(prev.text) + 1
            prev.text = prev.text + " " + ln.text
            prev.spans.extend([[s + offset, e + offset, k] for s, e, k in ln.spans])
            prev.x1 = ln.x1
            prev.bot = max(prev.bot, ln.bot)
        else:
            out.append(ln)
    return out


# ---------------------------------------------------------------------------
# Tables without ruling lines
# ---------------------------------------------------------------------------

EQ_NUMBER = re.compile(r"^\(\s*[\dA-Z]{1,4}(?:\.\d{1,3})?[a-z]?\s*\)$")
LIST_MARK = re.compile(r"^(?:[•◦▪▫‣⁃●○■□\-–—*]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|\(?[ivxIVX]{1,5}[.)])$")


def _center_in(ln: Line, bbox) -> bool:
    x0, top, x1, bot = bbox
    return x0 - 2 <= (ln.x0 + ln.x1) / 2 <= x1 + 2 and top - 2 <= (ln.top + ln.bot) / 2 <= bot + 2


def _visual_rows(lines: list[Line]) -> list[list[Line]]:
    """Group lines that share a row (vertical overlap of their centres), left to right."""
    rows: list[list[Line]] = []
    for ln in sorted(lines, key=lambda ln: (ln.top, ln.x0)):
        c = (ln.top + ln.bot) / 2
        for row in reversed(rows[-3:]):
            top = min(r.top for r in row)
            bot = max(r.bot for r in row)
            rc = (top + bot) / 2
            if top - 0.5 <= c <= bot + 0.5 or ln.top - 0.5 <= rc <= ln.bot + 0.5:
                row.append(ln)
                break
        else:
            rows.append([ln])
    return [sorted(r, key=lambda ln: ln.x0) for r in rows]


def _row_cells_ok(row: list[Line]) -> bool:
    return len(row) >= 2 and all(b.x0 - a.x1 > 0.6 * min(a.size, b.size) for a, b in zip(row, row[1:], strict=False))


def _grid_runs(rows: list[list[Line]]) -> list[list[list[Line]]]:
    """Runs of consecutive rows that could be one table: multi-cell rows, with at most two
    narrow single-cell rows (group labels, wrapped cells) between them."""
    runs: list[list[list[Line]]] = []
    cur: list[list[Line]] = []
    singles: list[list[Line]] = []
    for row in rows:
        size = statistics.median(ln.size for ln in row)
        if cur:
            prev_bot = max(ln.bot for ln in (singles[-1] if singles else cur[-1]))
            if min(ln.top for ln in row) - prev_bot > 2.2 * size:
                runs.append(cur)
                cur, singles = [], []
        if _row_cells_ok(row):
            cur.extend(singles)
            singles = []
            cur.append(row)
        elif cur and len(row) == 1 and len(singles) < 2:
            run_w = max(ln.x1 for r in cur for ln in r) - min(ln.x0 for r in cur for ln in r)
            if row[0].width <= 0.6 * run_w:
                singles.append(row)
            else:
                runs.append(cur)
                cur, singles = [], []
        else:
            if cur:
                runs.append(cur)
            cur, singles = [], []
    if cur:
        runs.append(cur)
    return runs


def _bands(rows: list[list[Line]]) -> list[tuple[float, float]]:
    """Column bands: x ranges covered by cells on a good share of the rows."""
    cover: Counter = Counter()
    multi = [r for r in rows if len(r) >= 2]
    for row in multi:
        bins: set[int] = set()
        for ln in row:
            bins.update(range(int(ln.x0), int(ln.x1) + 1))
        for b in bins:
            cover[b] += 1
    need = max(2, 0.25 * len(multi))
    bands: list[tuple[float, float]] = []
    start = prev = None
    for b in sorted(x for x, n in cover.items() if n >= need):
        if prev is not None and b == prev + 1:
            prev = b
            continue
        if start is not None:
            bands.append((start, prev + 1))
        start = prev = b
    if start is not None:
        bands.append((start, prev + 1))
    return bands


def _band_of(ln: Line, bands: list[tuple[float, float]]) -> int:
    for k, (a, b) in enumerate(bands):
        if a - 1 <= ln.x0 <= b:
            return k
    # Right-aligned or centred cells may start left of their band: take the largest overlap.
    best, best_ov = 0, -1.0
    for k, (a, b) in enumerate(bands):
        ov = min(b, ln.x1) - max(a, ln.x0)
        if ov > best_ov:
            best, best_ov = k, ov
    return best


def _is_table(run: list[list[Line]]) -> list[tuple[float, float]] | None:
    """Return the column bands if this run of rows is a table, else None. Deliberately strict:
    two-column prose, lists and numbered equations must stay what they are."""
    multi = [r for r in run if len(r) >= 2]
    if len(multi) < 3:
        return None
    bands = _bands(run)
    if len(bands) < 2:
        return None
    consistent = 0
    for row in multi:
        ks = [_band_of(ln, bands) for ln in row]
        if len(set(ks)) == len(ks):
            consistent += 1
    if consistent < 0.8 * len(multi):
        return None
    cells = [ln for r in run for ln in r]
    words = [len(ln.text.split()) for ln in cells]
    if sum(words) / len(words) > 5:
        return None  # sentences, not cells
    by_band: dict[int, list[Line]] = defaultdict(list)
    for ln in cells:
        by_band[_band_of(ln, bands)].append(ln)
    for k in by_band:
        if statistics.median(len(ln.text.split()) for ln in by_band[k]) > 6:
            return None
    first, last = by_band.get(0, []), by_band.get(len(bands) - 1, [])
    if len(bands) == 2 and first and all(LIST_MARK.match(ln.text.strip()) for ln in first):
        return None  # a list with its markers set apart
    if last and all(EQ_NUMBER.match(ln.text.strip()) for ln in last):
        return None  # numbered equations
    if len(bands) == 2 and len(multi) < 4 and sum(words) / len(words) > 3:
        return None  # two short columns of words over three rows: too little evidence
    table_w = max(ln.x1 for ln in cells) - min(ln.x0 for ln in cells)
    widths = [statistics.median(ln.width for ln in by_band[k]) for k in by_band]
    if len(bands) == 2 and max(widths) > 0.42 * table_w:
        return None  # two columns of running text
    return bands


def find_text_tables(lines: list[Line], two_col: bool = False) -> tuple[list[dict], list[Line]]:
    """Detect tables drawn without ruling lines: text aligned in columns over 3+ rows.

    Returns (tables as {"bbox", "rows"}, the lines that are not part of a table). Every line
    inside a detected table's box becomes a cell, so no text is lost."""
    tables: list[dict] = []
    remaining = list(lines)
    groups = [remaining]
    if two_col:
        groups.append([ln for ln in remaining if ln.col == "left"])
        groups.append([ln for ln in remaining if ln.col == "right"])
    for group in groups:
        group = [ln for ln in group if any(ln is r for r in remaining)]
        for run in _grid_runs(_visual_rows(group)):
            bands = _is_table(run)
            if bands is None:
                continue
            cells = [ln for r in run for ln in r]
            bbox = [min(ln.x0 for ln in cells), min(ln.top for ln in cells),
                    max(ln.x1 for ln in cells), max(ln.bot for ln in cells)]
            members = [ln for ln in remaining
                       if bbox[0] - 1 <= (ln.x0 + ln.x1) / 2 <= bbox[2] + 1
                       and bbox[1] - 1 <= (ln.top + ln.bot) / 2 <= bbox[3] + 1]
            rows: list[list[str]] = []
            for vr in _visual_rows(members):
                cellv = [""] * len(bands)
                for ln in vr:
                    k = _band_of(ln, bands)
                    cellv[k] = (cellv[k] + " " + ln.text.strip()).strip()
                rows.append(cellv)
            ids = {id(ln) for ln in members}
            remaining = [ln for ln in remaining if id(ln) not in ids]
            tables.append({"bbox": bbox, "rows": rows, "ruled": False})
    return tables, remaining


# ---------------------------------------------------------------------------
# Hyphenation
# ---------------------------------------------------------------------------


def should_join_hyphen(left: str, right: str, vocab: Counter) -> bool:
    """Decide whether 'left-' at a line end + 'right' at the next line start is one word."""
    lw = WORD.findall(left)
    rw = WORD.findall(right)
    if not lw or not rw:
        return False
    a, b = lw[-1], rw[0]
    if not b[:1].islower():
        return False
    joined = (a + b).casefold()
    hyphenated_seen = False
    if vocab.get(joined, 0) > 0:
        return True
    # Did the hyphenated form appear mid-line somewhere? The vocab tokenizer splits on '-',
    # so we approximate with "both halves are frequent standalone words".
    if vocab.get(a.casefold(), 0) >= 2 and vocab.get(b.casefold(), 0) >= 2 and len(a) >= 3 and len(b) >= 3:
        hyphenated_seen = True
    return not hyphenated_seen


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------


class Assembler:
    def __init__(self, stats: BookStats):
        self.stats = stats
        self.blocks: list[Block] = []
        self.open: Block | None = None
        self.removed: Counter = Counter()

    # -- paragraph accumulation -------------------------------------------------

    def _append_text(self, block: Block, line: Line) -> None:
        if not block.text:
            block.text = line.text
            block.spans = [list(s) for s in line.spans]
            block.lines.append(line)
            return
        prev = block.text
        joiner = " "
        cut = 0
        if prev.endswith("­"):
            cut, joiner = 1, ""
            self.removed["hyphens_joined"] += 1
        elif (
            prev.endswith("-")
            and not prev.endswith("--")
            and len(prev) >= 2
            and prev[-2].isalpha()
            and line.text[:1].isalpha()
        ):
            if should_join_hyphen(prev[:-1], line.text, self.stats.vocab):
                cut, joiner = 1, ""
                self.removed["hyphens_joined"] += 1
            else:
                joiner = ""
                self.removed["hyphens_kept"] += 1
        if cut:
            block.text = prev[:-cut]
            block.spans = [[s, min(e, len(block.text)), k] for s, e, k in block.spans if s < len(block.text)]
        offset = len(block.text) + len(joiner)
        block.text = block.text + joiner + line.text
        block.spans.extend([[s + offset, e + offset, k] for s, e, k in line.spans])
        block.lines.append(line)

    def close(self) -> None:
        if self.open is not None and self.open.text.strip():
            self.blocks.append(self.open)
        self.open = None

    def start(self, btype: str, line: Line, level: int = 0) -> Block:
        self.close()
        self.open = Block(type=btype, page=line.page, level=level)
        self._append_text(self.open, line)
        return self.open

    def emit(self, block: Block) -> None:
        self.close()
        self.blocks.append(block)

    # -- classification -----------------------------------------------------------

    def heading_level(self, line: Line) -> int:
        body = self.stats.body_size
        if len(line.text) > 160:
            return 0
        if line.size >= body * 1.18:
            for i, s in enumerate(self.stats.heading_sizes):
                if line.size >= s - 0.25:
                    return min(i + 1, 4)
            return min(len(self.stats.heading_sizes) + 1, 4) or 1
        return 0

    def is_bold_heading(self, line: Line, prev: Line | None, nxt: Line | None) -> bool:
        if not line.bold or len(line.text) > 90 or TERMINAL.search(line.text.rstrip("*")):
            return False
        if nxt is not None and nxt.bold and nxt.page == line.page and nxt.top - line.bot < line.size:
            return False
        gap_above = (line.top - prev.bot) if prev is not None and prev.page == line.page else line.size * 2
        return gap_above > line.size * 0.6 and abs(line.size - self.stats.body_size) < 1.5

    def is_equation(self, line: Line) -> bool:
        if line.mono or len(line.text) > 140:
            return False
        sym = sum(1 for ch in line.text if ch in MATH_SYMBOLS)
        words = WORD.findall(line.text)
        long_words = sum(1 for w in words if len(w) > 3)
        centered = line.col_x1 > line.col_x0 and abs(
            (line.x0 + line.x1) / 2 - (line.col_x0 + line.col_x1) / 2
        ) < (line.col_x1 - line.col_x0) * 0.08 and line.width < (line.col_x1 - line.col_x0) * 0.8
        if line.math >= 0.35 and centered and long_words <= 4:
            return True
        return centered and sym >= 2 and long_words <= 2 and line.math >= 0.15

    def paragraph_break(self, prev: Line, cur: Line, gap_ref: float) -> bool:
        if prev.page != cur.page or prev.col != cur.col:
            # Across a page or column boundary: continue the paragraph only if the
            # previous line looks unfinished or the new line isn't indented.
            unfinished = not TERMINAL.search(prev.text) or prev.text.endswith("-")
            indented = cur.x0 > cur.col_x0 + cur.size * 0.8
            if unfinished and cur.text[:1].islower():
                return False
            if unfinished and not indented:
                return False
            return not (self.stats.indent_style and not indented and not TERMINAL.search(prev.text))
        gap = cur.top - prev.bot
        if gap > gap_ref + cur.size * 0.55:
            return True
        # A change of type size starts a new paragraph only with some extra space as well:
        # small caps and inline size changes keep the normal line spacing.
        if abs(cur.size - prev.size) > max(prev.size * 0.15, 1.0) and gap > gap_ref + cur.size * 0.15:
            return True
        if cur.x0 > cur.col_x0 + cur.size * 0.8 and cur.x0 > prev.x0 + cur.size * 0.5:
            return True
        return prev.x1 < cur.col_x1 - cur.size * 3 and bool(TERMINAL.search(prev.text))

    # -- per page --------------------------------------------------------------

    def add_page(self, page_no: int, lines: list[Line], page_h: float, images: list[dict],
                 tables: list[dict]) -> None:
        body = self.stats.body_size

        # Tables: remove lines inside table areas, insert table blocks in reading order.
        table_blocks: list[tuple[float, tuple[float, float], Block]] = []
        for t in tables:
            x0, top, x1, bot = t["bbox"]
            inside = [ln for ln in lines if _center_in(ln, t["bbox"])]
            # Tables found from aligned text have already taken their lines out of the flow.
            if not inside and t.get("ruled", True):
                continue
            ids = {id(ln) for ln in inside}
            lines = [ln for ln in lines if id(ln) not in ids]
            text = "\n".join(" | ".join(cell.replace("\n", " ") for cell in row) for row in t["rows"])
            table_blocks.append((top, (x0, x1), Block(type="table", page=page_no, text=text, data={"rows": t["rows"]})))

        # Footnote region: small lines at the bottom of the page.
        foot_start = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            ln = lines[i]
            if ln.size <= body * 0.9 and ln.top > page_h * 0.55 and not CAPTION.match(ln.text):
                foot_start = i
            else:
                break
        footnote_lines = lines[foot_start:]
        if footnote_lines and not FOOTNOTE_MARK.match(footnote_lines[0].text) and not (
            self.blocks and self.blocks[-1].type == "footnote" or self._pending_footnotes
        ):
            # Small text at the bottom without a marker: probably not footnotes.
            footnote_lines = []
            foot_start = len(lines)
        main = lines[:foot_start]

        # Inline figures and tables in reading order: before the first line of their own column
        # (on two-column pages) that starts below their top edge.
        visuals: list[tuple[float, str, Block]] = []
        left = [ln for ln in main if ln.col == "left"]
        right = [ln for ln in main if ln.col == "right"]
        split = (max(ln.x1 for ln in left) + min(ln.x0 for ln in right)) / 2 if left and right else None

        def column_of(x0: float, x1: float) -> str:
            if split is None:
                return "full"
            if x1 <= split + 4:
                return "left"
            if x0 >= split - 4:
                return "right"
            return "full"

        for im in images:
            btype = "page_image" if im.get("scan") else "figure"
            data: dict[str, Any] = {"src": im.get("file"), "w": round(im["x1"] - im["x0"]),
                                    "h": round(im["bot"] - im["top"])}
            if im.get("text"):
                # Labels and annotations drawn inside the figure: kept for search and alt text.
                data["figure_text"] = im["text"]
            visuals.append((im["top"], column_of(im["x0"], im["x1"]), Block(type=btype, page=page_no, data=data)))
        for top, (tx0, tx1), tb in table_blocks:
            visuals.append((top, column_of(tx0, tx1), tb))
        visuals.sort(key=lambda v: v[0])

        gaps = [b.top - a.bot for a, b in zip(main, main[1:], strict=False)
                if a.col == b.col and 0 <= b.top - a.bot < body * 2]
        gap_ref = statistics.median(gaps) if gaps else body * 0.3

        prev: Line | None = self.open.lines[-1] if self.open is not None and self.open.lines else None
        all_visuals = list(visuals)
        for idx, ln in enumerate(main):
            due = [v for v in visuals if v[0] <= ln.top and (v[1] == "full" or ln.col in ("full", v[1]))]
            if ln.col == "right":
                # The left column of this band is finished: figures at its foot come first.
                band_end = min((x.top for x in main[idx:] if x.col == "full"), default=float("inf"))
                due += [v for v in visuals if v[1] == "left" and v[0] < band_end and v not in due]
                due.sort(key=lambda v: v[0])
            for v in due:
                self.emit(v[2])
                visuals.remove(v)
                prev = None
            nxt = main[idx + 1] if idx + 1 < len(main) else None
            text = ln.text.strip()
            if not text:
                continue
            level = self.heading_level(ln)
            if level == 0 and self.is_bold_heading(ln, prev, nxt):
                level = len(self.stats.heading_sizes) + 1 if self.stats.heading_sizes else 2
                level = min(level, 4)
            if level:
                o = self.open
                if (
                    o is not None and o.type == "heading" and o.level == level and prev is not None
                    and prev.page == ln.page and ln.top - prev.bot < ln.size * 0.9
                ):
                    self._append_text(o, ln)
                else:
                    self.start("heading", ln, level)
            elif ln.mono:
                o = self.open
                indent = " " * max(0, round((ln.x0 - ln.col_x0) / max(ln.size * 0.6, 1)))
                if o is not None and o.type == "code":
                    o.text += "\n" + indent + ln.text
                    o.lines.append(ln)
                else:
                    self.close()
                    self.open = Block(type="code", page=ln.page, text=indent + ln.text, lines=[ln])
            elif self.is_equation(ln):
                o = self.open
                if o is not None and o.type == "equation" and prev is not None and ln.top - prev.bot < ln.size * 1.2:
                    o.text += "\n" + ln.text
                    o.lines.append(ln)
                else:
                    self.close()
                    self.open = Block(type="equation", page=ln.page, text=ln.text, lines=[ln])
            elif CAPTION.match(text) and (ln.size < body * 0.98 or ln.bold or ln.italic or self._near_visual(ln, all_visuals)):
                self.start("caption", ln)
            elif BULLET.match(text) and (self.open is None or self.open.type != "paragraph" or prev is None
                                         or self.paragraph_break(prev, ln, gap_ref) or ln.x0 <= prev.x0 + 1):
                self.start("list_item", ln)
            else:
                o = self.open
                if o is not None and o.type in ("paragraph", "list_item", "caption") and prev is not None and not self.paragraph_break(prev, ln, gap_ref) or o is not None and o.type in ("paragraph", "list_item") and prev is None and o.lines and not self.paragraph_break(o.lines[-1], ln, gap_ref):
                    self._append_text(o, ln)
                else:
                    self.start("paragraph", ln)
            prev = ln
        # Paragraph may continue on next page; visuals after the last line go after it.
        pending_visuals = [v[2] for v in visuals]
        if pending_visuals:
            self.close()
            for b in pending_visuals:
                self.blocks.append(b)

        # Footnotes are emitted after the page's body, at the paragraph break nearest the end
        # of the page, so they never split a sentence.
        notes: list[Block] = []
        for ln in footnote_lines:
            m = FOOTNOTE_MARK.match(ln.text)
            starts_with_sup = bool(ln.spans and ln.spans[0][0] == 0 and ln.spans[0][2] == "sup")
            if m and (starts_with_sup or m.group(1).isdigit() or not m.group(1).isalpha()):
                notes.append(Block(type="footnote", page=ln.page, data={"marker": m.group(1)}))
                self._append_text(notes[-1], ln)
            elif notes:
                self._append_text(notes[-1], ln)
            elif self._pending_footnotes:
                self._append_text(self._pending_footnotes[-1], ln)
            elif self.blocks and self.blocks[-1].type == "footnote":
                self._append_text(self.blocks[-1], ln)
            else:
                notes.append(Block(type="footnote", page=ln.page, data={"marker": ""}))
                self._append_text(notes[-1], ln)
        self._pending_footnotes.extend(notes)
        if self.open is None or self.open.type != "paragraph":
            self.flush_footnotes()

    _pending_footnotes: list[Block]

    def flush_footnotes(self) -> None:
        if self._pending_footnotes:
            self.close()
            self.blocks.extend(self._pending_footnotes)
            self._pending_footnotes = []

    def _near_visual(self, ln: Line, visuals: list[tuple[float, Block]]) -> bool:
        return bool(visuals)


def assemble(pages_data: list[dict], outline: list[dict] | None = None) -> dict[str, Any]:
    """Turn the per-page JSON documents into blocks, chapters and a table of contents."""
    pages_data = sorted(pages_data, key=lambda p: p["n"])
    raw_pages = [[_to_line(d, p["n"]) for d in p["lines"]] for p in pages_data]
    heights = [p["h"] for p in pages_data]
    stats = compute_stats(raw_pages)
    removed: Counter = Counter()
    cleaned = remove_running_elements(raw_pages, heights, stats.body_size, removed)
    ordered: list[list[Line]] = []
    page_tables: list[list[dict]] = []
    for lines, p in zip(cleaned, pages_data, strict=True):
        found: list[dict] = []
        if not p.get("ocr"):  # OCR boxes are too unevenly placed to read as a grid
            ruled = [t["bbox"] for t in p.get("tables", [])]
            in_ruled = [ln for ln in lines if any(_center_in(ln, b) for b in ruled)]
            free = [ln for ln in lines if not any(_center_in(ln, b) for b in ruled)]
            found, free = find_text_tables(free, classify_columns(free))
            lines = free + in_ruled  # lines in ruled tables are taken out by add_page
            removed["text_tables"] += len(found)
        page_tables.append(list(p.get("tables", [])) + found)
        ordered.append(order_page(lines, p["w"]))

    # Indentation style: share of body lines that start ~1-3 em in from their column.
    body_lines = [ln for page in ordered for ln in page if abs(ln.size - stats.body_size) < 0.6]
    indented = sum(1 for ln in body_lines if ln.size * 0.8 < ln.x0 - ln.col_x0 < ln.size * 3.5)
    stats.indent_style = bool(body_lines) and indented / len(body_lines) > 0.03

    asm = Assembler(stats)
    asm._pending_footnotes = []
    asm.removed = removed
    for page, lines, tables in zip(pages_data, ordered, page_tables, strict=True):
        if page.get("failed"):
            # Never drop a page silently: leave a visible marker where it belongs.
            asm.emit(Block(type="page_image", page=page["n"], data={"failed": True}))
            continue
        asm.add_page(page["n"], lines, page["h"], page.get("images", []), tables)
        if asm.open is None or asm.open.type != "paragraph":
            asm.flush_footnotes()
    asm.close()
    asm.flush_footnotes()

    blocks = _merge_captions(asm.blocks)
    assign_ids(blocks)
    link_footnotes(blocks)
    toc = assign_chapters(blocks, outline or [])
    return {
        "blocks": blocks,
        "toc": toc,
        "stats": {
            "body_size": stats.body_size,
            "removed": dict(removed),
            "pages": len(pages_data),
            "ocr_pages": sum(1 for p in pages_data if p.get("ocr")),
            "scanned_pages": sum(1 for p in pages_data if p.get("scanned")),
            "failed_pages": [p["n"] for p in pages_data if p.get("failed")],
            "blocks": len(blocks),
            "words": sum(len(WORD.findall(b.text)) for b in blocks),
        },
    }


def _merge_captions(blocks: list[Block]) -> list[Block]:
    """Point figures at their captions when they sit next to each other."""
    for i, b in enumerate(blocks):
        if b.type != "caption":
            continue
        for j in (i - 1, i + 1, i - 2):
            if 0 <= j < len(blocks) and blocks[j].type in ("figure", "table") and blocks[j].page == b.page:
                blocks[j].data["caption_index"] = i
                break
    return blocks


def assign_ids(blocks: list[Block]) -> None:
    seen: Counter = Counter()
    fig_seen: Counter = Counter()
    for b in blocks:
        if b.type in ("figure", "page_image"):
            fig_seen[b.page] += 1
            base = f"f{b.page}x{fig_seen[b.page]}"
        else:
            norm = normalize_for_id(b.text)[:4000] or f"empty{b.page}"
            base = hashlib.sha1(norm.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
        seen[base] += 1
        b.id = base if seen[base] == 1 else f"{base}-{seen[base]}"
    # Captions are referenced by index until ids exist.
    for b in blocks:
        idx = b.data.pop("caption_index", None)
        if idx is not None:
            b.data["caption"] = blocks[idx].id


def link_footnotes(blocks: list[Block]) -> None:
    """Turn superscript markers in body text into links to the matching footnote."""
    notes_by_page: dict[int, dict[str, str]] = defaultdict(dict)
    for b in blocks:
        if b.type == "footnote" and b.data.get("marker"):
            notes_by_page[b.page].setdefault(b.data["marker"], b.id)
    if not notes_by_page:
        return
    for b in blocks:
        if b.type in ("footnote", "figure", "page_image", "table"):
            continue
        for span in b.spans:
            if span[2] != "sup":
                continue
            marker = b.text[span[0]:span[1]].strip()
            for page in (b.page, b.page + 1, b.page - 1):
                target = notes_by_page.get(page, {}).get(marker)
                if target:
                    span[2] = "fnref"
                    span.append(target)
                    break


def assign_chapters(blocks: list[Block], outline: list[dict]) -> list[dict]:
    """Split into chapters (for lazy loading) and build the table of contents."""
    toc: list[dict] = []
    if not blocks:
        return toc
    starts: list[int] = []
    top_level = [o for o in outline if o["level"] == min((x["level"] for x in outline), default=0)]
    if len(top_level) >= 2:
        for entry in outline:
            idx = _find_outline_block(blocks, entry)
            if idx is None:
                continue
            toc.append({"title": entry["title"], "level": entry["level"] - min(o["level"] for o in outline) + 1,
                        "block": blocks[idx].id, "page": blocks[idx].page, "_idx": idx})
            if entry in top_level:
                starts.append(idx)
    else:
        headings = [(i, b) for i, b in enumerate(blocks) if b.type == "heading"]
        if headings:
            top = min(b.level for _i, b in headings)
            for i, b in headings:
                if b.level <= top + 2:
                    toc.append({"title": b.text, "level": b.level - top + 1, "block": b.id, "page": b.page, "_idx": i})
                if b.level == top:
                    starts.append(i)
    # Keep chapters to a sane size for lazy loading: split very long ones by page.
    starts = sorted(set([0] + starts))
    bounds: list[int] = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(blocks)
        bounds.append(s)
        chunk_start = s
        for i in range(s, e):
            if i - chunk_start >= 400 and blocks[i].type in ("paragraph", "heading") and blocks[i].page != blocks[i - 1].page:
                bounds.append(i)
                chunk_start = i
    bounds = sorted(set(bounds))
    ch = -1
    bset = set(bounds)
    for i, b in enumerate(blocks):
        if i in bset:
            ch += 1
        b.chapter = ch
    toc.sort(key=lambda t: t["_idx"])
    for t in toc:
        t["chapter"] = blocks[t.pop("_idx")].chapter
    return toc


def _find_outline_block(blocks: list[Block], entry: dict) -> int | None:
    from rapidfuzz import fuzz

    page = entry["page"]
    best, best_score = None, 0.0
    first_on_page = None
    for i, b in enumerate(blocks):
        if b.page < page:
            continue
        if b.page > page:
            break
        if first_on_page is None:
            first_on_page = i
        if b.type in ("heading", "paragraph"):
            score = fuzz.partial_ratio(entry["title"].casefold(), b.text[:200].casefold())
            if score > best_score:
                best, best_score = i, score
    if best is not None and best_score >= 80:
        return best
    if first_on_page is not None:
        return first_on_page
    # Page had no blocks (e.g. blank); use the next block after it.
    for i, b in enumerate(blocks):
        if b.page > page:
            return i
    return None


def block_to_row(b: Block) -> dict[str, Any]:
    data = dict(b.data)
    if b.spans:
        data["spans"] = b.spans
    if b.type == "equation" and b.lines:
        data["bbox"] = [
            min(ln.x0 for ln in b.lines), min(ln.top for ln in b.lines),
            max(ln.x1 for ln in b.lines), max(ln.bot for ln in b.lines),
        ]
    return {"id": b.id, "type": b.type, "page": b.page, "level": b.level, "text": b.text,
            "chapter": b.chapter, "data": data}
