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
                  hyphenate: dict | None = None, sup_after: str | None = None, sup: str = "1",
                  justify: bool = False) -> None:
        lines = wrap(text, *BODY, width - (18 if indent else 0), hyphenate)
        for k, ln in enumerate(lines):
            if self.y < 100:
                self.new_page()
            xx = x + (18 if indent and k == 0 else 0)
            self.c.setFont(*BODY)
            words = ln.split()
            if justify and k < len(lines) - 1 and len(words) > 1:
                # Spread the words so the line ends exactly at the column edge, as typeset books do.
                avail = x + width - xx
                spare = (avail - sum(stringWidth(w, *BODY) for w in words)) / (len(words) - 1)
                wx = xx
                for w in words:
                    self.c.drawString(wx, self.y, w)
                    wx += stringWidth(w, *BODY) + spare
            else:
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


def make_two_column(path: Path, gutter: float = 24, justify: bool = False) -> tuple[list[str], list[str]]:
    d = Doc(path, title="Two Columns", running_header="JOURNAL OF TESTS")
    d.heading("A Study of Columns", 16)
    colw = (W - 144 - gutter) / 2
    left = ["Left column paragraph number %d talks about the first half of the argument in plain words "
            "so that the reader can follow along without trouble." % i for i in range(1, 4)]
    right = ["Right column paragraph number %d continues the argument and should only be read after the "
             "whole left column has been finished." % i for i in range(1, 4)]
    top = d.y
    for p in left:
        d.paragraph(p, x=72, width=colw, justify=justify)
    d.y = top
    for p in right:
        d.paragraph(p, x=72 + colw + gutter, width=colw, justify=justify)
    d.save()
    return left, right


FIGURE_LABELS = ["Task Pool", "Generate", "Filter", "Classify", "Seed tasks", "Output"]


def make_figure_page(path: Path) -> tuple[list[str], str]:
    """A diagram drawn with vector shapes and small labels (some overlapping, like the
    Self-Instruct paper's Figure 1), its caption, an annotated raster screenshot, and a shaded
    sidebar of normal prose that must stay in the reading flow. Returns (paragraphs, caption)."""
    from reportlab.lib.utils import ImageReader

    d = Doc(path, title="Figures", running_header="")
    d.heading("Drawings")
    paras = [
        "The pipeline begins with a small pool of tasks written by hand, and grows that pool "
        "by asking the model to propose new ones, which are then checked before they are kept.",
        "Each round adds a few hundred tasks to the pool, and the whole process repeats until "
        "the pool is large enough to train on without further help from people.",
        "A screenshot of the review tool follows, with its own annotations drawn on top of it.",
        "The sidebar above is ordinary text in a shaded box, and readers should see it as text.",
    ]
    d.paragraph(paras[0])
    c = d.c
    # The diagram: boxes, arrows and 7 pt labels; two labels deliberately overlap.
    top = d.y - 10
    c.setStrokeColorRGB(0.2, 0.2, 0.5)
    c.setFillColorRGB(0.85, 0.9, 1.0)
    boxes = [(90, top - 60), (230, top - 60), (370, top - 60), (230, top - 150)]
    for bx, by in boxes:
        c.roundRect(bx, by, 110, 45, 6, stroke=1, fill=1)
    c.line(200, top - 38, 230, top - 38)
    c.line(340, top - 38, 370, top - 38)
    c.line(285, top - 60, 285, top - 105)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 7)
    for (bx, by), label in zip(boxes, FIGURE_LABELS[:4], strict=True):
        c.drawString(bx + 8, by + 25, label)
    c.drawString(98, top - 50, FIGURE_LABELS[4])
    c.drawString(101, top - 52, FIGURE_LABELS[5])  # overlaps the label above it
    d.y = top - 175
    c.setFont("Times-Roman", 9)
    caption = "Figure 1: An overview of how the task pool grows."
    c.drawString(72, d.y, caption)
    d.y -= 24
    d.paragraph(paras[1])
    # A shaded sidebar with body-size prose: a box, but not a figure.
    side_top = d.y + 4
    c.setFillColorRGB(0.92, 0.92, 0.92)
    c.rect(66, side_top - 50, W - 132, 52, stroke=0, fill=1)
    c.setStrokeColorRGB(0.5, 0.5, 0.5)
    c.rect(64, side_top - 52, W - 128, 56, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)
    sidebar = ("Note that the pool never shrinks: tasks that fail the checks are simply not added, "
               "and every task that was added once stays in the pool for later rounds.")
    d.paragraph(sidebar, indent=False)
    d.y -= 12
    d.paragraph(paras[2])
    # An annotated screenshot: a raster image with small text drawn over it.
    img_top = d.y - 6
    c.drawImage(ImageReader(_screenshot_image()), 150, img_top - 120, width=300, height=120)
    c.setFont("Helvetica", 6.5)
    c.drawString(160, img_top - 30, "Click Approve to keep")
    c.drawString(330, img_top - 100, "Rejected tasks")
    d.y = img_top - 140
    d.paragraph(paras[3])
    d.save()
    return paras[:2] + [sidebar] + paras[2:], caption


def _screenshot_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 240), (235, 240, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 580, 60), fill=(60, 90, 160))
    for k in range(4):
        draw.rectangle((40, 90 + k * 35, 400, 110 + k * 35), fill=(200, 205, 215))
    return img


TABLE_ROWS = [
    ["Model", "Params", "Score", "Notes"],
    ["Alpha", "11B", "25.7", "baseline"],
    ["Beta", "175B", "33.1", "tuned"],
    ["Gamma", "175B", "39.9", "ours"],
]


def make_borderless_table(path: Path) -> tuple[list[str], list[list[str]], list[str]]:
    """A table set with spaces only (no rules), a numbered list with the numbers set apart,
    and body text around them. Returns (paragraphs, table rows, list items)."""
    d = Doc(path, title="Tables", running_header="")
    d.heading("Results")
    paras = [
        "We compare three models of different sizes on the same set of tasks, and report the "
        "score of each one together with a short note about how it was trained.",
        "The largest model scores highest, although the gap to the tuned model is small.",
        "The steps we followed were the same for every model, in this order.",
    ]
    d.paragraph(paras[0])
    c = d.c
    cols = [90, 230, 330, 420]
    d.y -= 6
    for k, row in enumerate(TABLE_ROWS):
        c.setFont("Helvetica-Bold" if k == 0 else "Helvetica", 9)
        for x, cell in zip(cols, row, strict=True):
            c.drawString(x, d.y, cell)
        d.y -= 14
    d.y -= 10
    d.paragraph(paras[1])
    d.paragraph(paras[2])
    items = [
        "Collect the seed tasks and write one example for each of them by hand.",
        "Ask the model for new tasks and keep only the ones that pass every check.",
        "Train on the final pool and evaluate on tasks that were never seen before.",
    ]
    c.setFont(*BODY)
    for n, item in enumerate(items, 1):
        c.drawString(90, d.y, f"{n}.")
        c.drawString(122, d.y, item)  # a wide gap, so number and text are separate cells
        d.y -= LEADING
    d.save()
    return paras, TABLE_ROWS, items


def make_footnotes(path: Path) -> None:
    d = Doc(path, title="Notes", running_header="NOTES AND QUERIES")
    d.heading("On Footnotes")
    d.paragraph("The historian made a careful claim about the river trade in the twelfth century, "
                "which later scholars disputed at some length.", sup_after="century,")
    d.paragraph("A second paragraph follows the first and carries no note at all.")
    d.footnote("1", "See the discussion in the appendix for the sources behind this claim.")
    d.save()


SCAN_LINES = [
    "The kitchen was cold and the table was not cleared.",
    "Nobody had touched the bread since the morning before.",
    "The sheriff looked at the stove and then at the door.",
    "His wife stood by the window and said nothing at all.",
    "Outside the wind kept on at the fence and the barn.",
    "They waited a long time before anyone spoke again.",
]


def make_scanned(path: Path, pages: int = 3) -> list[str]:
    """An image-only 'scan': each page is a picture of text, with a running head, a page
    number and a 'Digitized by Google' stamp, like Google Books scans. Page 1 has a title.
    Returns the body lines (the same on every page)."""
    import io

    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader

    c = canvas.Canvas(str(path), pagesize=letter)
    dpi = 150
    for n in range(1, pages + 1):
        img = Image.new("L", (int(W / 72 * dpi), int(H / 72 * dpi)), 250)
        draw = ImageDraw.Draw(img)
        small = ImageFont.load_default(size=22)
        body = ImageFont.load_default(size=30)
        draw.text((img.width // 2 - 90, 90), "THE COLD HOUSE", font=small, fill=30)
        y = 200
        if n == 1:
            draw.text((260, y), "The Cold House", font=ImageFont.load_default(size=64), fill=20)
            y += 140
        for line in SCAN_LINES:
            draw.text((200, y), line, font=body, fill=25)
            y += 58
        draw.text((img.width // 2 - 10, img.height - 230), str(n), font=small, fill=30)
        # The stamp is set larger than the text, as on real Google scans.
        draw.text((img.width // 2 - 170, img.height - 150), "Digitized by Google", font=ImageFont.load_default(size=40), fill=120)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), 0, 0, width=W, height=H)
        c.showPage()
    c.save()
    return SCAN_LINES


def make_encrypted(path: Path) -> None:
    from reportlab.lib import pdfencrypt

    enc = pdfencrypt.StandardEncryption("secret", ownerPassword="owner", canPrint=1)
    c = canvas.Canvas(str(path), pagesize=letter, encrypt=enc)
    c.drawString(72, 700, "Secret text")
    c.save()


# ---------------------------------------------------------------------------
# OCR fixtures (pipeline-quality): a deterministic stand-in for the OCR engine, and a scan
# that carries its own OCR text layer. Self-contained: nothing above depends on them.
# ---------------------------------------------------------------------------

OCR_SPEECHES = [
    "MRS. HALE: I wish you had seen Minnie Foster when she wore a white dress with blue ribbons and "
    "stood up there in the choir and sang.",
    "MRS. PETERS: Well, I must get those things from the front room closet. She said she wanted an "
    "apron, and a shawl to put around her.",
    "COUNTY ATTORNEY: Nothing here but kitchen things, and not much of anything to tell us what "
    "happened in this house that night.",
]
# How OCR read the stamp on four pages of a real scan (one of them as two boxes).
WATERMARK_READINGS = [["Digize byGoogle"], ["Dguiea ygGoogle"], ["zed by", "Google"], ["Diglied byGogle"]]


def make_image_scan(path: Path, pages: int = 3) -> None:
    """Image-only pages: a scan without a text layer."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    c = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(pages):
        img = Image.new("L", (306, 396), 240)
        c.drawImage(ImageReader(img), 0, 0, width=W, height=H)
        c.showPage()
    c.save()


def fake_ocr_lines(index: int) -> list[dict]:
    """What a RapidOCR pass over a page of an old play returns: a running head and page
    number at the top, a watermark at the bottom, and type sizes that swing by 25% from
    line to line because they are guessed from box heights."""
    noisy = [8.5, 9.0, 8.5, 11.5, 8.0, 8.5, 10.5, 9.0]  # one body size, as OCR guesses it
    out: list[dict] = []

    def line(t: str, x0: float, top: float, x1: float, sz: float) -> None:
        out.append({"t": t, "x0": x0, "x1": x1, "top": top, "bot": top + sz * 1.35, "sz": sz,
                    "font": "OCR", "b": False, "i": False, "m": False, "mt": 0.0, "sp": [], "conf": 0.97})

    line("TRIFLES", 270, 40, 340, 12.0)  # running head, guessed at 1.4x the body size
    line(str(index + 21), 520, 40, 534, 10.5)
    # (The fixture repeats its speeches on every page; starting below the header zone keeps
    # the first one from looking like a repeated running head.)
    y = 140.0
    if index == 0:
        line("A PLAY IN ONE ACT", 220, y, 390, 20.0)  # a real title: twice the size, on its own
        y += 50
    for s in OCR_SPEECHES:
        words = s.split()
        rows = [" ".join(words[k:k + 9]) for k in range(0, len(words), 9)]
        for r, text in enumerate(rows):
            line(text, 90 if r == 0 else 72, y, 540, noisy[(r + index) % len(noisy)])
            y += 15
        y += 10
    x = 400.0
    for piece in WATERMARK_READINGS[index % len(WATERMARK_READINGS)]:
        line(piece, x, 740, x + 6 * len(piece), 10.5)
        x += 6 * len(piece) + 20
    return out


class FakeOcr:
    """Stands in for RapidOCR so the OCR path is tested without the optional models."""

    def page_lines(self, pdfium_doc, index: int, page_w: float, page_h: float) -> list[dict]:
        return fake_ocr_lines(index)


SCAN_LAYER_BODY = [
    "The emperor was obliged to acknowledge that the legions on the frontier were no longer",
    "to be trusted, and that the provinces which they had defended so long were now open",
    "to the incursions of the barbarians, who crossed the river whenever the ice allowed.",
    "His ministers advised him to purchase a peace which he had no means of enforcing, and",
    "the senate, which had lost the habit of resistance, approved whatever was proposed.",
]
# A contents list on the same scan: short entries that line up like the cells of a table.
SCAN_LAYER_CONTENTS = [["CHAP. I.", "The Extent of the Empire", "1"],
                       ["CHAP. II.", "The Union and Prosperity", "27"],
                       ["CHAP. III.", "The Constitution", "64"],
                       ["CHAP. IV.", "The Cruelty of Commodus", "98"]]
SCAN_LAYER_NOTE = "Ibid. vol. i. p. 245, and the authorities collected there."


def make_scan_with_text_layer(path: Path, pages: int = 2, strips: int = 1) -> None:
    """A scanned book page with the scanner's own OCR text layer: the page image (whole, or
    tiled into `strips` horizontal bands, as some scanners store it) and invisible text over
    it. The layer has a contents list aligned in columns and a footnote."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    c = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(pages):
        band = H / strips
        for k in range(strips):
            img = Image.new("L", (306, max(1, int(396 / strips))), 235)
            c.drawImage(ImageReader(img), 0, k * band, width=W, height=band)
        t = c.beginText()
        t.setTextRenderMode(3)  # invisible, like an OCR layer
        y = H - 220  # below the zone where a lone number reads as a page number
        for row in SCAN_LAYER_CONTENTS:
            for x, cell in zip((90, 170, 460), row, strict=True):
                t.setFont("Times-Roman", 11)
                t.setTextOrigin(x, y)
                t.textOut(cell)
            y -= 16
        y -= 20
        for line in SCAN_LAYER_BODY:
            t.setFont("Times-Roman", 11)
            t.setTextOrigin(72, y)
            t.textOut(line)
            y -= 15
        y -= 20
        t.setFont("Times-Roman", 8)
        t.setTextOrigin(72, y)
        t.textOut(SCAN_LAYER_NOTE)
        c.drawText(t)
        c.showPage()
    c.save()


def _photo(seed: int, size: tuple[int, int]):
    """A picture with real content (a gradient and stripes), not a flat tone."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, (200 - 30 * seed, 160, 120 + 40 * seed))
    d = ImageDraw.Draw(img)
    for k in range(0, size[0], 12):
        d.line([(k, 0), (k + size[1] // 2, size[1])], fill=(40 * seed, 90, 160), width=3)
    return img


PHOTO_PAGE_TEXT = [
    "The two photographs on this page show the harbour before and after the storm of that",
    "winter, taken from the same window of the customs house by the same photographer, who",
    "waited three days for the light to match. Readers will notice the missing pier and the",
    "boats drawn up on the shingle where the road used to run along the edge of the water.",
]


def make_photo_page(path: Path) -> list[str]:
    """A born-digital page: two large photographs (about 40% of the page each) and a few
    lines of visible body text. Both photographs are figures."""
    from reportlab.lib.utils import ImageReader

    c = canvas.Canvas(str(path), pagesize=letter)
    # 576 x 330 pt each: 39% of the page apiece, 78% together, 20 pt apart.
    c.drawImage(ImageReader(_photo(1, (400, 250))), 18, 370, width=576, height=330)
    c.drawImage(ImageReader(_photo(2, (400, 250))), 18, 20, width=576, height=330)
    c.setFont(*BODY)
    y = H - 30
    for line in PHOTO_PAGE_TEXT:  # in the band above the first photograph
        c.drawString(40, y, line)
        y -= 14
    c.showPage()
    c.save()
    return PHOTO_PAGE_TEXT


def make_two_column_over_background(path: Path, gutter: float = 12.0) -> tuple[list[str], list[str]]:
    """A designed page: a full-bleed background photograph under justified two-column text
    with a narrow gutter. The text is visible, so this is not a scan."""
    from reportlab.lib.utils import ImageReader

    d = Doc(path, title="Two Columns Over A Photo", running_header="")
    d.c.drawImage(ImageReader(_photo(0, (300, 400))), 0, 0, width=W, height=H)
    d.heading("A Study of Columns", 16)
    colw = (W - 144 - gutter) / 2
    left = ["Left column paragraph number %d talks about the first half of the argument in plain words "
            "so that the reader can follow along without trouble." % i for i in range(1, 4)]
    right = ["Right column paragraph number %d continues the argument and should only be read after the "
             "whole left column has been finished." % i for i in range(1, 4)]
    top = d.y
    for p in left:
        d.paragraph(p, x=72, width=colw, justify=True)
    d.y = top
    for p in right:
        d.paragraph(p, x=72 + colw + gutter, width=colw, justify=True)
    d.save()
    return left, right
