"""Robust anchoring of highlights and notes, modelled on the W3C Web Annotation selectors.

An anchor records three things about a highlighted range:

* a block id plus character offsets inside that block (fast, exact),
* a TextQuoteSelector: the exact quote with a short prefix and suffix,
* the source page, used to narrow fuzzy searches.

When a book is converted again (for example with a better pipeline), block ids may change
for blocks whose text changed. Re-anchoring tries, in order: same block and offsets with the
same quote; the quote inside the same block; the quote (with context) anywhere in the book;
a fuzzy match near the original page. If all of that fails the annotation is kept and
flagged as orphaned. It is never deleted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

CONTEXT = 32


@dataclass
class Anchor:
    block_id: str
    start: int
    end: int
    exact: str
    prefix: str
    suffix: str


@dataclass
class BlockText:
    id: str
    text: str
    page: int
    seq: int


@dataclass
class Resolved:
    block_id: str
    start: int
    end: int
    method: str  # exact | quote_in_block | quote_in_book | fuzzy | orphaned
    seq: int = 0
    page: int | None = None


def make_anchor(block_id: str, text: str, start: int, end: int) -> Anchor:
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    return Anchor(
        block_id=block_id,
        start=start,
        end=end,
        exact=text[start:end],
        prefix=text[max(0, start - CONTEXT):start],
        suffix=text[end:end + CONTEXT],
    )


def _context_score(text: str, pos: int, anchor: Anchor) -> int:
    """How many characters of prefix/suffix context match around a candidate position."""
    score = 0
    pre = text[max(0, pos - len(anchor.prefix)):pos]
    for a, b in zip(reversed(pre), reversed(anchor.prefix), strict=False):
        if a != b:
            break
        score += 1
    end = pos + len(anchor.exact)
    suf = text[end:end + len(anchor.suffix)]
    for a, b in zip(suf, anchor.suffix, strict=False):
        if a != b:
            break
        score += 1
    return score


def _find_all(text: str, needle: str) -> list[int]:
    out, i = [], text.find(needle)
    while i != -1 and needle:
        out.append(i)
        i = text.find(needle, i + 1)
    return out


def resolve(anchor: Anchor, blocks: Sequence[BlockText], page_hint: int | None = None) -> Resolved:
    by_id = {b.id: b for b in blocks}
    blk = by_id.get(anchor.block_id)
    if not anchor.exact:
        # Bookmarks / whole-block anchors: block id or nearest block on the page.
        if blk is not None:
            return Resolved(blk.id, 0, 0, "exact", blk.seq, blk.page)
        return _nearest_on_page(blocks, page_hint)

    # 1. Same block, same offsets, same text.
    if blk is not None and blk.text[anchor.start:anchor.end] == anchor.exact:
        return Resolved(blk.id, anchor.start, anchor.end, "exact", blk.seq, blk.page)

    # 2. Quote somewhere in the same block (text shifted, e.g. a hyphen fix).
    if blk is not None:
        hits = _find_all(blk.text, anchor.exact)
        if hits:
            pos = max(hits, key=lambda p: (_context_score(blk.text, p, anchor), -abs(p - anchor.start)))
            return Resolved(blk.id, pos, pos + len(anchor.exact), "quote_in_block", blk.seq, blk.page)

    # 3. Quote anywhere in the book, best context match, closest to the page hint.
    candidates: list[tuple[int, int, BlockText, int]] = []
    for b in blocks:
        for pos in _find_all(b.text, anchor.exact):
            dist = abs(b.page - page_hint) if page_hint is not None else 0
            candidates.append((_context_score(b.text, pos, anchor), -dist, b, pos))
    if candidates:
        candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
        _s, _d, b, pos = candidates[0]
        return Resolved(b.id, pos, pos + len(anchor.exact), "quote_in_book", b.seq, b.page)

    # 4. Fuzzy: the text was changed slightly (e.g. de-hyphenation, ligatures).
    fuzzy = _fuzzy(anchor, blocks, page_hint)
    if fuzzy is not None:
        return fuzzy

    return Resolved(anchor.block_id, anchor.start, anchor.end, "orphaned", 0, page_hint)


def _nearest_on_page(blocks: Sequence[BlockText], page: int | None) -> Resolved:
    if blocks and page is not None:
        best = min(blocks, key=lambda b: (abs(b.page - page), b.seq))
        return Resolved(best.id, 0, 0, "fuzzy", best.seq, best.page)
    return Resolved("", 0, 0, "orphaned", 0, page)


def _fuzzy(anchor: Anchor, blocks: Sequence[BlockText], page_hint: int | None) -> Resolved | None:
    from rapidfuzz import fuzz

    needle = anchor.exact
    if len(needle) < 8:
        return None
    pool = list(blocks)
    if page_hint is not None:
        near = [b for b in blocks if abs(b.page - page_hint) <= 3]
        pool = near or pool
    best: tuple[float, BlockText] | None = None
    for b in pool:
        if len(b.text) < len(needle) * 0.6:
            continue
        score = fuzz.partial_ratio(needle, b.text)
        if best is None or score > best[0]:
            best = (score, b)
    if best is None or best[0] < 85:
        return None
    b = best[1]
    al = fuzz.partial_ratio_alignment(needle, b.text)
    if al is None:
        return None
    return Resolved(b.id, al.dest_start, al.dest_end, "fuzzy", b.seq, b.page)
