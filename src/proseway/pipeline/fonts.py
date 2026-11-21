"""Font-name heuristics. PDF font names look like 'ABCDEF+Minion-BoldIt'."""

from __future__ import annotations

import re

_SUBSET = re.compile(r"^[A-Z]{6}\+")
_BOLD = re.compile(r"bold|black|heavy|semibold|demibold|[-,]bd\b|\bbd$|medi", re.I)
_ITALIC = re.compile(r"italic|oblique|[-,]it\b|ital|[a-z]it$|slanted|-sl\b", re.I)
_MONO = re.compile(
    r"mono|courier|consol|menlo|typewriter|cmtt|lmtt|inconsolata|sfmt|letter ?gothic|"
    r"lucidaconsole|fixedsys|\bcode\b|sourcecodepro|firacode|dejavusansmono",
    re.I,
)
_MATH = re.compile(
    r"cmmi|cmsy|cmex|msbm|msam|cmbsy|lmmath|math|symbol|stix|euclid|mtextra|rsfs|eufm|"
    r"txsy|txmi|pxsy|pxmi|esint|wasy",
    re.I,
)


def clean_font_name(name: str | None) -> str:
    if not name:
        return ""
    return _SUBSET.sub("", str(name))


def font_flags(name: str | None) -> tuple[bool, bool, bool, bool]:
    """Return (bold, italic, mono, math) for a font name."""
    n = clean_font_name(name)
    return (
        bool(_BOLD.search(n)),
        bool(_ITALIC.search(n)),
        bool(_MONO.search(n)),
        bool(_MATH.search(n)),
    )
