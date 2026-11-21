"""Generate small PDFs with known ground truth for pipeline tests (uses reportlab, dev-only)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

W, H = letter
BODY = ("Times-Roman", 11)
LEADING = 14


def wrap(text: str, font: str, size: float, width: float, hyphenate: dict[str, tuple[str, str]] | None = None) -> list[str]:
    """Greedy line wrap. `hyphenate` maps a word to (left, right) parts to force a hyphen break."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    i = 0
    while i < len(words):
        w = words[i]
        trial = (cur + " " + w).strip()
        if stringWidth(trial, font, size) <= width:
            cur = trial
            i += 1
            continue
        if hyphenate and w.strip(".,;") in hyphenate:
            left, right = hyphenate[w.strip(".,;")]
            trial2 = (cur + " " + left + "-").strip()
            if stringWidth(trial2, font, size) <= width:
                lines.append(trial2)
                cur = right + w[len(left) + len(right):]
                i += 1
                continue
        lines.append(cur)
        cur = ""
    if cur:
        lines.append(cur)
    return lines


class Doc:
    def __init__(self, path: Path, title: str = "Test Book", running_header: str = "A TEST BOOK"):
        self.c = canvas.Canvas(str(path), pagesize=letter)
        self.c.setTitle(title)
        self.c.setAuthor("Test Author")
        self.page = 1
        self.header = running_header
        self.y = H - 90

    def decorations(self) -> None:
        c = self.c
        c.setFont("Times-Italic", 9)
        c.drawCentredString(W / 2, H - 40, self.header)
        c.setFont("Times-Roman", 9)
        c.drawCentredString(W / 2, 36, str(self.page))

    def new_page(self) -> None:
        self.decorations()
        self.c.showPage()
        self.page += 1
        self.y = H - 90

    def heading(self, text: str, size: int = 18) -> None:
        self.c.setFont("Helvetica-Bold", size)
        self.y -= size
        self.c.drawString(72, self.y, text)
        self.y -= size

    def paragraph(self, text: str, x: float = 72, width: float = W - 144, indent: bool = True,
                  hyphenate: dict | None = None, sup_after: str | None = None, sup: str = "1") -> None:
        lines = wrap(text, *BODY, width - (18 if indent else 0), hyphenate)
        for k, ln in enumerate(lines):
            if self.y < 100:
                self.new_page()
            xx = x + (18 if indent and k == 0 else 0)
            self.c.setFont(*BODY)
            self.c.drawString(xx, self.y, ln)
            if sup_after and sup_after in ln:
                pre = ln[: ln.index(sup_after) + len(sup_after)]
                sx = xx + stringWidth(pre, *BODY)
                self.c.setFont("Times-Roman", 7)
                self.c.drawString(sx, self.y + 4, sup)
                sup_after = None
            self.y -= LEADING
        self.y -= 4

    def footnote(self, marker: str, text: str) -> None:
        c = self.c
        c.setFont("Times-Roman", 6)
        c.drawString(72, 80, marker)
        c.setFont("Times-Roman", 8.5)
        c.drawString(78, 78, text)

    def save(self) -> None:
        self.decorations()
        self.c.save()


NOVEL_PARAS = [
    "It was a bright cold day in the valley, and the river ran fast under the old stone bridge. "
    "Nobody in the village could remember a spring like it, and the elders said so to anyone who "
    "would stop long enough to listen to them talk about the weather and the harvest.",
    "Margaret walked down to the water every morning. She carried a basket of bread for the miller, "
    "who had been unwell since the winter, and she always stopped at the bridge to watch the "
    "extraordinary light that came off the surface before the mist lifted from the fields.",
    "The miller thanked her each time, though he rarely said more than a few words. His house smelled "
    "of flour and woodsmoke, and the great wheel turned outside the window with a steady, patient sound "
    "that seemed to her like the slow breathing of some enormous animal asleep beside the stream.",
]


def make_novel(path: Path, pages: int = 3) -> list[str]:
    """Single column, running header, page numbers, forced hyphen breaks. Returns paragraphs."""
    d = Doc(path)
    d.heading("Chapter One")
    paras = []
    hy = {"extraordinary": ("extra", "ordinary"), "breathing": ("breath", "ing"), "remember": ("re", "member")}
    k = 0
    while d.page <= pages:
        p = NOVEL_PARAS[k % len(NOVEL_PARAS)]
        d.paragraph(p, hyphenate=hy)
        paras.append(p)
        k += 1
        if k > 40:
            break
    d.save()
    return paras


def make_two_column(path: Path) -> tuple[list[str], list[str]]:
    d = Doc(path, title="Two Columns", running_header="JOURNAL OF TESTS")
    d.heading("A Study of Columns", 16)
    colw = (W - 144 - 24) / 2
    left = ["Left column paragraph number %d talks about the first half of the argument in plain words "
            "so that the reader can follow along without trouble." % i for i in range(1, 4)]
    right = ["Right column paragraph number %d continues the argument and should only be read after the "
             "whole left column has been finished." % i for i in range(1, 4)]
    top = d.y
    for p in left:
        d.paragraph(p, x=72, width=colw)
    d.y = top
    for p in right:
        d.paragraph(p, x=72 + colw + 24, width=colw)
    d.save()
    return left, right


def make_footnotes(path: Path) -> None:
    d = Doc(path, title="Notes", running_header="NOTES AND QUERIES")
    d.heading("On Footnotes")
    d.paragraph("The historian made a careful claim about the river trade in the twelfth century, "
                "which later scholars disputed at some length.", sup_after="century,")
    d.paragraph("A second paragraph follows the first and carries no note at all.")
    d.footnote("1", "See the discussion in the appendix for the sources behind this claim.")
    d.save()


def make_encrypted(path: Path) -> None:
    from reportlab.lib import pdfencrypt

    enc = pdfencrypt.StandardEncryption("secret", ownerPassword="owner", canPrint=1)
    c = canvas.Canvas(str(path), pagesize=letter, encrypt=enc)
    c.drawString(72, 700, "Secret text")
    c.save()
