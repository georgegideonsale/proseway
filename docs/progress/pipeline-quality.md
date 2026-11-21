# Pipeline quality: figures, tables without rules, OCR pages

Branch `claude/pipeline-quality-50d649`, 2026-11-21. Addresses PROGRESS.md "Known issues" 1–3.

The rule throughout: the author's words are never rewritten or dropped. Only layout artefacts
(running heads, page numbers, scan watermarks) are removed. Text that moves out of the
reading flow (labels inside a figure) is kept on the figure block and is searchable.

## What changed

### 1. Text inside figures

- **Figure regions from vector drawings** (`extract.find_figures`). Paths and images are
  clustered into drawings. Small labels next to a drawing, such as axis ticks and legends,
  join it. Drawings are cut back at their caption, and neighbouring parts of one figure are
  merged when there's no body text between them. A drawing only becomes a figure when the
  text inside it reads as figure text: small type (under 0.8× the page's body size), or a
  scatter of short labels. A box around normal-size sentences (a shaded sidebar) or around
  code stays in the reading flow. So do aligned text with a few rules (a table) and anything
  that overlaps a ruled table pdfplumber found.
- **Figure text** (`data.figure_text` on `figure` blocks). Lines inside a figure (raster or
  vector) are taken out of the paragraphs and stored on the figure in reading order. Search
  indexes them, and a hit leads to the figure (one-line change in `convert._store`). A
  figure that couldn't be rendered still keeps its text (`data.src` is then null).
- **Form XObjects** (`pdfium_chars.page_objects`). This was a real bug. Objects inside
  embedded forms report bounds in the form's own space. LaTeX embeds most figures as forms,
  so Self-Instruct's Figure 2 images were placed *off the page*. We now walk the object tree
  ourselves, apply each form's matrix, intersect with clip paths, and skip invisible paths:
  unpainted clip paths, and the white background rectangles that matplotlib puts behind
  every chart.
- **Overlapping text runs** (`extract._untangle`). Labels drawn on top of each other
  interleave letter by letter when sorted by x ("SOeuetdp utatsks"). When glyphs in a
  segment overlap heavily, we split them back into runs in drawing order ("Seed tasks",
  "Output").
- pdfplumber "tables" that are mostly empty grids, such as the bars and gridlines of a chart
  (32 columns, almost every cell empty), are ignored (`extract.plausible_table`). Figure
  detection then gets them.

### 2. Tables without ruling lines

- `layout.find_text_tables` groups lines into visual rows and finds runs of multi-cell rows.
  It then derives column bands from where cells sit on most rows. A run becomes a `table`
  block (`data.rows`, same shape as ruled tables) only if all of these hold:
  - at least 3 multi-cell rows and at least 2 columns;
  - at least 80% of rows put each cell in a different column;
  - cells average ≤ 5 words, and no column's median is over 6 words;
  - for two columns, neither column is over 42% of the table width, and there are 4+ rows
    unless the cells are very short.
- What it rejects:
  - two-column prose;
  - lists whose numbers are set apart;
  - numbered equations;
  - display maths, where limits and sums stack into rows.
- On two-column pages it also looks inside each column. Every line inside a detected table's
  box becomes a cell, so no text is dropped.
- Lines inside a ruled table (pdfplumber) are excluded first, so a table never comes out
  twice.

### 3. OCR'd pages

- **Watermarks** (`layout.remove_watermarks`). "Digitized by Google", plus the Internet
  Archive and Microsoft stamps, are removed from the page margins.
  - A close fuzzy match (≥ 80) is always removed.
  - Once the book has shown the stamp on 3+ pages, looser OCR spellings ("Dguiea ygGoogle",
    "Diglied byGogle") and fragments ("zed by" + "Google") are removed too, but only near
    the stamp's usual position.
  - This runs *before* the book statistics, so the stamp's large type no longer becomes a
    heading size.
  - Why it survived before: the stamp is 12–13.5 pt on pages whose OCR body size is about
    9 pt, and running-head detection ignores anything over 1.3× body size.
- **Headings on OCR pages** (`Assembler.ocr_heading_ok`). An OCR line is a heading only if
  all of these hold:
  - it is at least 1.5× body size and at most 80 characters;
  - it is horizontal: wider than 1.5× its height, so rotated microfilm-target text with
    "sizes" of 70–133 pt is out;
  - it is mostly letters, so shelf marks like "959142-c 3" are out;
  - it doesn't end in `, ; -`;
  - it is set apart from the lines above and below.
- The text-table detector skips OCR pages, where boxes are too uneven to read as a grid.

### Found along the way

- **Narrow column gutters** (`extract._find_gutters`). Self-Instruct's gutter is about
  16 pt, under the 1.6 em (17.6 pt) cell-gap threshold. So on most pages the left and
  right column lines were *merged into one line*, and the paper was read across both
  columns. This was the main cause of its 0.68 layer order. We now find x positions that are
  blank on most rows that have real text on both sides, and split rows there.
- **Figures and tables in two-column pages** are now emitted in their own column. Before, a
  right-column table appeared in the middle of the left column's text.
- **Ligatures:** PDFium reports the "ff" of "officers" as two f's sharing one box. My first
  version of overprint de-duplication dropped one of them: 132 words in the first 120 pages
  of *Pride and Prejudice*. The benchmark caught it. De-duplication now only drops a copy
  drawn at another point in the content stream, and a unit test covers it. After the fix,
  extraction of those 120 pages is line-for-line identical to the old code.

## Review pass (merge gates)

A coordinator review asked for a second pass before merging. Status of each item: **Working**
means there is a test for it and the benchmark was checked; **Untested** means it isn't
covered by either.

| # | Item | Status |
|---|---|---|
| 1 | Benchmark Gibbon and University Physics 1 against main | Working (see the tables below) |
| 2 | Tighter guards and counters on the passes that delete words | Working |
| 3 | Body-size text in a drawing and framed prose stay in the flow | Working |
| 4 | Empty exercise tables and boxed formulas stay text | Working |
| 5 | A scan's own OCR text layer skips the grid passes | Working |
| 6 | Deterministic `FakeOcr` fixture | Working |
| 7 | `PIPELINE_VERSION` 1 → 2 | Working |

**2. Passes that delete words.** Both de-duplication passes now count what they drop, in
`stats.removed` as `overprint_glyphs` and `shadow_lines`. Each page's JSON carries a
`dropped` count, and `assemble` sums them.
- `_dedupe_overprint` only drops a glyph that has all of these, compared with the first
  copy:
  - the same text;
  - the same size (within 10%) and the same width;
  - a position within 1 pt;
  - overlap with it of at least half its width.

  The last condition came from the second review: Gibbon p260's squeezed OCR layer sets
  the "ff" of "difference" as two 0.86 pt boxes 0.86 pt apart. That is within 1 pt, so
  one f was dropped. See "Gibbon, traced" below.
- `_drop_shadow_lines` only drops a line when all of these hold:
  - it is within 20% of the other line's size;
  - its top is within 0.6 of a line height of the other's;
  - it starts within 2.5 em of where its text sits inside the other line (found with
    `fuzz.partial_ratio_alignment`).
- The 20% and the offsets come from Self-Instruct's Figure 6. Its legend is drawn as a
  pseudo-3D stack of about six copies at 8.5–10 pt, up to 6 pt apart vertically and 21 pt
  sideways. A 10% limit kept those copies, and the extra full-size lines made the chart
  fail the figure test.
- The position check is the one that protects real text. A short line is only dropped if
  it lies on top of the same words in the other line.
- The previous code dropped a standalone "Ibid." (11 pt) overlapping a 6 pt footnote line
  that begins "Ibid. vol. i. …", in both passes. Verified by running the new test against
  commit `c686c1e`.

**3. Text the figure finder must leave alone** (ported from the duplicate branch, then
adjusted against the corpus):
- **Body-size text in a vector drawing is not figure text** (`body_size_text`). If the
  median size of the text in a drawing is over 0.85× the body size, the drawing is a frame
  (a title-page ornament, a boxed formula, an exercise grid), so its text stays in the flow
  and no picture is added. Two kinds of chart are exceptions:
  - a dense drawing: 100+ shapes, 3+ per line, 5+ lines. This keeps Self-Instruct's
    sunburst, whose labels are 10.5 pt on an 11 pt body;
  - a chart whose labels are mostly numbers (40%+ of lines) and sit outside its shapes.
    Intro Stats p34's dice bar chart has 9.5 pt tick labels on a 9.5 pt body. An exercise
    grid puts its labels inside the drawn cells (`_in_cells`), so it is not an exception.
  - Text over 1.05× body size (a title) is never a label.
- **Framed prose** (`prose_in_frame`). Text counts as prose, at any size, when either holds:
  - 80%+ of its non-code characters are in lines of 6+ words;
  - 50%+ are, and the drawing is a plain frame of ≤ 12 shapes.

  The duplicate branch used the 50% rule with no shape limit. Here, that rejected
  Self-Instruct's Figures 2 and 6: both are all small type, and about 55% of their
  characters are in sentence-length example lines inside the diagram.
- **Caption continuations** (`_caption_continuations`) never join a drawing as labels. A
  continuation is a line right under a caption (or under the caption's previous line), at
  the same size, starting near its left edge. A blanket "6+ words is never a label" rule
  also pushed Self-Instruct's axis title "ROUGE-L Overlap with the Most Similar Seed
  Instruction" out of its chart, so that rule was dropped.

**4. Exercise tables and boxed formulas.** The body-size rule covers these. Intro Stats
p227 and p664, the empty "Smoking Level" tables, are 14–16 lines of 10 pt text inside
shaded cells, and p254's P(x) box is 3 lines in a 7-shape frame. All three are text in the
flow again, as on main, instead of figure images. A whole-book diff of figure decisions
against `c686c1e` shows only those three pages changed: Intro Stats `figure_text` went
from 54 words to 11, the labels of p34's dice chart. Self-Instruct keeps all 10 figures.

**5. Scan text layers.** A page whose images together cover 70%+ of it (clipped to the
page), with any text at all, is a scan with its own OCR layer (`_is_scan_layer`; page
JSON `scan_layer: true`). Since the second review, total coverage counts, so a scan tiled
into strips or cropped a little qualifies, and so does a sparse title page or plate. The
first version needed one image over 70% and 200+ characters. On a text-bearing scan page
(200+ characters), the strips are also dropped as the scan background, as a single page
image already was. On those pages extraction skips three things:
- the gutter finder;
- untangling of overlapping runs;
- shadow-line dropping.

Layout also skips text-table detection there, as it already did on pages we OCR ourselves.
Main had none of these passes, so such pages now behave exactly as on main, except that
overprint de-duplication still runs with its new guards. Tests:
- `test_scan_text_layer_is_read_as_plain_text` runs on both engines, with the page image
  whole and tiled into 3 strips. Its contents list is aligned in three columns and is not a
  table, and neither the image nor the strips become figures.
- `test_scan_layer_detection` covers strips, a cropped scan, a sparse page, no text, an
  ordinary figure, and an image mostly off the page.
- The strip cases fail on `93543c4`.

**6. `FakeOcr`.** Ported from the duplicate branch (`tests/pdfgen.py`: `fake_ocr_lines`,
`FakeOcr`, `make_image_scan`). `test_ocr_pages_lose_watermarks_and_noisy_headings` runs on
both engines, without the OCR add-on. It checks:
- the exact paragraphs, in order, with their page numbers;
- the only heading is "A PLAY IN ONE ACT";
- no running head and no stamp reading survives.

It found two real gaps, both now fixed:
- **Running heads.** An OCR running head guessed at 1.4× body size escaped
  running-element removal, which skips anything over 1.3×. OCR lines now get 1.6×, as on
  the duplicate branch.
- **Short scans.** A 4-page scan with only two clear stamp readings never established the
  stamp, so the looser misreadings stayed. A short scan now needs `min(3, pages // 4 + 1)`
  clear readings, which is unchanged for 8+ pages.

The real-engine test is renamed `test_ocr_scan_with_real_engine` and is still skipped
without RapidOCR.

**7.** `PIPELINE_VERSION` is now 2, so books converted earlier are flagged as stale.

### Benchmark after the review pass

Every book was run on its own (`--only <book>`), one after another. Main's code was run
from a `git archive` of `main` (2093049, whose pipeline is identical to `bff9f42`) via
`PYTHONPATH`. Main's numbers for the six books are the `before` run above.

| Book | Main: recall / order / ref sim | This branch: recall / order / ref sim | Blocks main → branch | Time main → branch |
|---|---|---|---:|---:|
| Gibbon vol. 1 (scan, own OCR layer) | 0.9616 / 0.7210 / 0.6455 | 0.9616 / 0.7210 / 0.6455 | 4,955 → 4,951 | 108.0 → 93.3 s |
| University Physics 1 | 0.9682 / 0.9539 / – | **0.9693 / 0.9569** / – | 17,319 → 16,998 | 319.3 → 332.5 s |
| *Pride and Prejudice* | 0.9506 / 0.9671 / 0.9683 | 0.9506 / 0.9671 / 0.9683 | 2,087 → 2,087 | 45.6 → 25.9 s |
| *Sleepy Hollow* | 0.9456 / 0.9637 / 0.9748 | 0.9477 / 0.9634 / 0.9734 | 78 → 79 | 3.6 → 3.1 s |
| *Self-Instruct* | 0.9401 / 0.6779 / 0.3679 | 0.9080¹ / **0.8635 / 0.5274** | 731 → 653 | 4.5 → 6.6 s |
| *Erdős discrepancy* | 0.9369 / 0.8649 / 0.7501 | 0.9363² / 0.8644 / 0.7502 | 855 → 858 | 3.1 → 3.5 s |
| *Introductory Statistics* | 0.9523 / 0.9667 / – | 0.9553 / 0.9693 / – | 17,961 → 18,242 | 106.1 → 103.6 s |
| *Trifles* (OCR) | – / – / 0.1365 (precision 0.8521) | – / – / 0.1366 (precision **0.8585**) | 284 → 234 | 228.3 → 140.0 s |

What the review-pass numbers show:
- **Gibbon** (re-run after the second review's fixes):
  - Every accuracy metric is identical to main: layer recall and order, and reference
    similarity, recall (0.9038) and precision (0.8905). The word count is identical too
    (272,366).
  - `overprint_glyphs: 4`. The blocks are traced below.
- **Physics:**
  - Layer recall and order both rose.
  - 55 text tables were found.
  - 16 fewer figures than at `c686c1e`, all of them body-size text in a drawing that is
    now text again: the constants tables on pp. 883–884, and answer-key and worked-example
    fragments on pp. 907–943.
  - Some of those regions also hold maths drawn as vector paths with no text layer. That
    maths is not shown, as on main. `c686c1e` showed those regions as pictures, at the cost
    of taking their words out of the reading flow.
- **The other six books:** they match the earlier "after" run to within 0.0005. Trifles'
  counters and word count are identical to it, so the 1.6× OCR running-head allowance
  changes nothing on the real scan.
- **Counters:**
  - Self-Instruct: `overprint_glyphs: 73`, `shadow_lines: 21`.
  - Sleepy Hollow: `overprint_glyphs: 45` (the fake-bold banner).
  - Intro Stats: 3 overprinted glyphs and 3 shadow lines.
  - Pride, Erdős and Physics: zero of both.
- **Times** are as noisy as before. The main Gibbon and Physics runs overlapped with my test
  runs; the branch runs had the machine to themselves.

### Gibbon, traced

I converted the book exactly as `convert.py` does (our OCR on the 12 image-only pages),
with main's code and with this branch's. I logged every glyph the overprint pass dropped
and diffed the two block lists.
- **Which path each page took.** 642 pages are scan-layer pages and 12 are pages we OCR
  ourselves. The list of pages that took neither path is empty. So the gutter, untangle,
  shadow and text-table passes ran on no Gibbon page. (Since `_is_scan_layer` counts any
  text, the image-only pages count as scan-layer as well as OCR.)
- **Overprint drops, first version (5 glyphs).** One was a real letter:
  - p260 dropped the second f of "difference". The two f boxes are x 78.59–79.45 and
    79.45–80.32, at the same top and 9 pt, so they sit side by side, not on top of each
    other. They were within the 1 pt tolerance, and the text came out as "diference".
  - The fix is the half-width overlap condition. After it, p260 is identical to main, and
    `test_dedupe_keeps_text_at_another_size` pins the case.
- **Overprint drops, now (4 glyphs, all p564).** The OCR layer holds "of Memphis" twice,
  on top of itself:
  - `o` and `f` copies have identical boxes (114.30–116.72 and 116.72–119.13, top 194.81,
    7 pt);
  - `M` is 125.28–128.80 over 125.28–128.40;
  - `m` is 132.32–135.83 over 131.51–134.63, a 66% overlap.
  - Main reads the passage "ooff MMeemmpphhiis"; the branch reads "of Meempphhiis". The
    remaining doubled letters overlap too little to be dropped.
- **The 4 missing blocks** are all on pages 2–3. These are image-only pages with a library
  bookplate, which our OCR reads as fragments: "5", "UBRARY", "-ANGEL", "写", "UNIVEI",
  "S", "UNIVERSY", "5S", "8T".
  - Main made headings of 8 of them.
  - This branch's OCR heading guard rejects them for being short, mostly not letters, or
    not clearly larger. As paragraphs, neighbouring fragments merge: "UBRARY -ANGEL 写",
    "UNIVEI S", "UNIVERSY 5S". That is 11 blocks on main and 7 here.
  - The only other block that differs is the p564 paragraph above (same block, fewer
    doubled letters).
- **The narrower overprint guard elsewhere.** Sleepy Hollow, Self-Instruct, *Pride and
  Prejudice* and Intro Stats were re-run after the change. Their word and block counts,
  metrics and counters are identical to the previous run (for example
  `overprint_glyphs: 45` and `73`).

**Not benchmarked:** the pdfplumber engine (only the tests run it), and any book outside
the eight above. The test corpus has nothing like a title page with a drawn ornament or a
framed note in footnote type; those are covered only by the synthetic tests.

**Nit, `pdfium_chars.MAX_GRAPHIC_OBJECTS`.** The object walk stops after 20,000 page
objects, and an image after that point is no longer seen, so it can't become a figure.
Main counted images with no cap. No test book reaches the cap; it bounds the work on
hostile or extremely dense pages.

## Benchmark

`uv run python scripts/benchmark.py --only self-instruct erdos pride sleepy intro-stats trifles`,
PDFium engine, same laptop. Trifles with the OCR add-on. Raw results:
`data/bench/before.json` / `after.json` (git-ignored).

Before (main, commit `bff9f42`):

| Book | Pages | Time | s/page | Peak RAM | Layer recall | Layer order | Ref similarity | Ref recall | Ref precision | Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *Pride and Prejudice* (novel) | 479 | 45.6 s | 0.095 | 71 MB | 0.9506 | 0.9671 | 0.9683 | 0.9510 | 0.9963 | 2,087 |
| *Sleepy Hollow* (novel, smoke test) | 43 | 3.6 s | 0.085 | 72 MB | 0.9456 | 0.9637 | 0.9748 | 0.9592 | 0.9925 | 78 |
| OpenStax *Introductory Statistics* | 913 | 106.1 s | 0.116 | 202 MB | 0.9523 | 0.9667 | – | – | – | 17,961 |
| arXiv *Self-Instruct* (two-column) | 23 | 4.5 s | 0.198 | 166 MB | 0.9401 | **0.6779** | **0.3679** | 0.9266 | 0.4229 | 731 |
| arXiv *Erdős discrepancy* (maths) | 27 | 3.1 s | 0.116 | 132 MB | 0.9369 | 0.8649 | 0.7501 | 0.9786 | 0.7362 | 855 |
| *Trifles* (image-only scan, OCR) | 37 | 228.3 s | 6.17 | 448 MB | – | – | 0.1365 | 0.0846 | 0.8521 | 284 |

After (this branch, commit `99e6367`):

| Book | Pages | Time | s/page | Peak RAM | Layer recall | Layer order | Ref similarity | Ref recall | Ref precision | Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *Pride and Prejudice* (novel) | 479 | 22.6 s | 0.047 | 80 MB | 0.9506 | 0.9671 | 0.9683 | 0.9510 | 0.9963 | 2,087 |
| *Sleepy Hollow* (novel, smoke test) | 43 | 2.2 s | 0.052 | 113 MB | 0.9477 | 0.9634 | 0.9734 | 0.9601 | 0.9905 | 79 |
| OpenStax *Introductory Statistics* | 913 | 90.7 s | 0.099 | 220 MB | 0.9551 | 0.9693 | – | – | – | 18,237 |
| arXiv *Self-Instruct* (two-column) | 23 | 4.9 s | 0.215 | 161 MB | 0.9085¹ | **0.8636** | **0.5270** | 0.9297 | 0.4658 | 653 |
| arXiv *Erdős discrepancy* (maths) | 27 | 3.0 s | 0.111 | 127 MB | 0.9363² | 0.8644 | 0.7502 | 0.9786 | 0.7364 | 858 |
| *Trifles* (image-only scan, OCR) | 37 | 138.3 s | 3.74 | 456 MB | – | – | 0.1366 | 0.0845 | **0.8585** | 234 |

¹ Self-Instruct's layer recall:
- The benchmark counts only reading-flow text. Figure labels now live in `data.figure_text`, so they count as missing.
- Counting `figure_text` too, layer recall is **0.9491**: higher than before, because de-garbled words now match. No words were lost.

² Erdős: every page has exactly the same multiset of characters as before. Overlapping stacked limits ("H<H∑0≤2H") now group into tokens differently, which moves the token metrics by 0.0005.

Timing:
- Times vary a lot on this machine. The baseline ran while another session was also converting books, and the final run had the machine mostly to itself.
- A like-for-like sample of 61 Intro Stats pages (every 15th) took **116 ms/page with the new code vs 142 ms/page with the old**. pdfplumber's ruled-table pass is unchanged at about 50 ms/page. The new code renders fewer bogus crops.
- The layout stage costs about 0.3 ms/page more.

Counters (`stats.removed`):
- Trifles: `watermarks: 32` (new).
- Intro Stats: `text_tables: 1`, the ISBN table.
- Self-Instruct: `text_tables: 4`.
- *Pride and Prejudice*: `running_lines`, `page_numbers` and the hyphen counts are identical to the baseline.

## Examples checked by eye

I ran conversions with `scripts/inspect_book.py` and read the blocks, plus the per-page
extraction diffed against the old code.

**Self-Instruct (arXiv 2212.10560):**
- **Page 1:**
  - Figure 1 (four example boxes in a typewriter font, right column) is now one `figure`
    block with the examples in `figure_text`.
  - Before, those examples were about 35 short paragraphs woven into the abstract, which
    itself was read across both columns.
  - The abstract and introduction now read column by column.
- **Page 2:**
  - Figure 2 (the overview diagram) is one figure.
  - Its images had been placed off the page, at x≈680–810 on a 595 pt page, by the
    Form XObject bug.
  - Overlapping labels are untangled ("Step 2: Classification", "175 seed tasks with…").
- **Page 5:**
  - Figure 3 (sunburst, 10.5 pt labels) is a figure.
  - Figure 4 is a chart, and Figure 5's three stacked charts became one figure.
  - The tick labels "3000 2000 1000 0 …" left the body text.
- **Page 6:** Table 3 has no vertical rules (booktabs). It is a `table` with 13 rows:
  `Model | # Params ROUGE-L`, `T5-LM | 11B | 25.7`, and so on. Before, it was 40 one-line
  paragraphs. "# Params" and "ROUGE-L" stay one header cell because they sit closer
  together than any gap threshold.
- **Page 7:**
  - Figure 6 (bar chart) used to be a "table" from pdfplumber with 32 columns of mostly empty
    cells and garbage like "ccoorrrerecct ta anndd".
  - It is now a figure.
  - Its legend, drawn six times as a shadow, reads once: "correct and satisfying
    response …".
- **Page 15** (hyperparameter table) and **pages 21–23** (example tables) are `table`
  blocks.
- **Leftovers:** some author-affiliation symbols are still tiny paragraphs. Figure text is
  still garbled where the PDF itself overlaps two strings character by character.

**Erdős discrepancy (maths):**
- No figures and no text tables.
- An earlier version of the table detector turned two display equations (stacked ∑ limits
  on pages 18–19) into tables. That's fixed, and a test covers it.

**Introductory Statistics (OpenStax):**
- **Correct:**
  - p34: the dice bar chart becomes a figure.
  - p42: worked example boxes (Example 1.18) stay prose.
  - p113: the "Solution 2.30" box stays prose.
  - p415: the REMINDER note stays prose.
  - p882: the NOTE box stays prose.
  - p4: the ISBN block is a 2-column table.
- **Changed in the review pass:** p227 and p664 are *empty* exercise tables (headers and
  row labels only, shaded cells), and p254 has a small boxed P(x) formula. At `c686c1e`
  they became figure images with their words only in `figure_text`. They are text in the
  flow again, as on main: 14–16 short paragraphs each, without a picture of the grid.
- **Fixed along the way:**
  - "Table 1.15 contains the total…" is a sentence, not a caption. It had been used to cut
    drawings.
  - The back-of-book index (pp. 911–912, three columns) was briefly detected as tables.

**Trifles (image-only scan, OCR):**
- Every "Digitized by Google" stamp is gone (32 lines), including:
  - "Dguiea ygGoogle", "Diglied byGogle" and "Digtize by Google";
  - the stamp read as two boxes ("zed by" + "Google").
- Headings went from 53 to 2 ("TRIFLES" on the title page and "Trifles" over the play).
  The old 53 included:
  - every stamp;
  - shelf marks ("822.8 G552tr 1916a", "959142-c 3");
  - body lines whose OCR size estimate came out at 11.5 pt;
  - the rotated microfilm-target text on the last page (estimated "sizes" of 70–133 pt).
- The Google Books notice on page 1 is real text in the PDF and is kept.

**Novels:**
- *Pride and Prejudice*: the first 120 pages extract line-for-line identically to the old
  code, and every benchmark metric is identical.
- *Sleepy Hollow*: only page 1 changed. The publisher banner was drawn as fake bold and came
  out as "DDoowwnnllooaadd ffrreeee eeBBooookkss". It now reads "Download free eBooks".
  Those words aren't in the Gutenberg reference, hence the −0.0014 in reference similarity.

## Tests added (`tests/test_pipeline.py`, PDFs from `tests/pdfgen.py`)

Each one fails on the old code, except the two guards marked † below, which must pass on
both.

| Test | Engines | What it pins down |
|---|---|---|
| `test_narrow_gutter_columns_are_not_read_across` | both | Justified two-column text with a 12 pt gutter reads left column, then right. |
| `test_text_inside_figures_belongs_to_the_figure` | both | Covers four things, listed below the table. |
| `test_table_without_rules_becomes_a_table` | both | A 4×4 space-aligned table becomes one `table` block with exact rows, between its paragraphs. A numbered list with the numbers set apart stays `list_item`s. |
| `test_two_column_prose_is_never_a_table` † | both | Justified two-column prose (24 and 12 pt gutters) produces no table. |
| `test_ocr_watermarks_and_heading_sizes` | n/a (layout) | OCR spellings and split pieces of the stamp go. Wobbly OCR sizes (8.5–11.5) make no heading; the isolated title does. Every body word stays. |
| `test_ocr_scan_end_to_end` | pdfium + RapidOCR | A generated image-only scan through the real OCR engine: no stamp, no running head, body lines present, no false headings. Skipped when the OCR add-on isn't installed. |
| `test_text_tables_and_display_maths` | n/a (unit) | A grid of numbers in a "STIX"-named font is a table. Stacked limits and sums of a display equation are not. Neither is a three-column index. |
| `test_ligature_letters_are_not_taken_for_overprint` | n/a (unit) | "officers" keeps both f's. A fake-bold copy drawn later is dropped. A label drawn three times as a shadow reads once. |
| `test_scan_text_layer_is_not_figure_text` † | n/a (unit) | Short title lines over a page-sized scan image stay text. |
| `test_dedupe_keeps_text_at_another_size` | n/a (unit) | Review pass. An 11 pt "Ibid." over a 6 pt footnote line that starts "Ibid." keeps both lines, through `lines_from_chars` and through `_drop_shadow_lines`. A same-size copy 1 pt off is still dropped and counted. |
| `test_title_in_an_ornament_stays_text` | n/a (unit) | Review pass. An 18 pt title inside a 42-shape ornament stays in the flow. |
| `test_framed_note_and_caption_lines_stay_in_the_flow` | n/a (unit) | Review pass. A framed note in 7 pt sentences and a caption's second line stay in the flow, while the diagram beside them is still a figure with its labels. |
| `test_scan_text_layer_is_read_as_plain_text` | both × (1 image, 3 strips) | Review pass. A scan with an invisible OCR layer: its contents list (aligned in three columns) is not a table, the page image or strips are not figures, every word comes through, and no shadow lines or text tables are counted. |
| `test_scan_layer_detection` | n/a (unit) | Second review. Total image coverage decides: strips, a cropped scan and a sparse page qualify; no text, an ordinary figure, or an image mostly off the page don't. |
| `test_ocr_pages_lose_watermarks_and_noisy_headings` | both | Review pass, ported `FakeOcr`. Exact paragraphs and pages; one heading; no running head and no stamp reading. |
| `test_ocr_scan_with_real_engine` | pdfium + RapidOCR | Renamed from `test_ocr_scan_end_to_end`; skipped without the add-on. |

Every review-pass test except the real-engine one fails on `c686c1e`. That was checked by
running them with `PYTHONPATH` pointing at an archive of that commit.

`test_text_inside_figures_belongs_to_the_figure` covers:
- a vector diagram with 7 pt labels, two of them overlapping, gets every label in `figure_text`;
- an annotated raster screenshot keeps its annotations;
- a shaded, outlined sidebar of body-size prose stays a paragraph;
- the caption follows its figure and is linked to it, and FTS search finds a label.

`uv run pytest`: 66 passed (56 before the review pass, 63 after the first review).
`uv run ruff check .`: clean.

## What didn't improve, and what's left

- **Tables whose cells sit closer than the cell-gap threshold** are not found. For example,
  "2000 231" in Intro Stats Table 1.15 merges into one line before table detection sees it.
  Fixing this needs column evidence across rows, before lines are built, similar to the
  gutter finder.
- **Multi-row table headers** ("Smoking / Level", "African / American") come out as two
  header rows. There is no header or row-span model yet, and the first row is shown as `<th>`.
- **Complex tables can become figures.** A shaded table that the detector doesn't recognise
  becomes a figure image with searchable text. That's faithful, but the text doesn't reflow.
- **Figure text order** is top-to-bottom, left-to-right. That's fine for search, but rough
  as alt text for diagrams.
- **The reader doesn't show `figure_text` yet.** The web reader's `<img alt>` and the EPUB
  export still use "Figure on page N". The data is there in `data.figure_text`; the fix is in
  `web/src/components/reader/BlockView.tsx` and `epub.py`, outside this branch's scope.
- **Caption false positives in layout.** `layout` still classes body text that starts
  "Table 1.15 contains …" as a caption when the page has a figure. That logic predates this
  branch; only the figure-trimming use was fixed.
- **OCR quality itself** is unchanged: small caps are misread and text is noisy. Upside-down
  stamps such as "'pisus sy uo sem I" still appear on a few Trifles pages.
- **The table detector is off on OCR pages**, both ours and scans with their own OCR
  layer, where boxes are too uneven to read as a grid. Tables in Gibbon's scan come out as
  lines of text, as on main.
- **Follow-ups from the second review** (logged, not fixed):
  - **Framed prose depends on the frame.** A narrow note in 7 pt type, or a note with a
    ~20-path icon, has short lines or more than 12 shapes. It can then fail
    `prose_in_frame` and land in `figure_text`. This needs a fixture.
  - **Centred two-line captions** aren't detected as caption continuations: the second
    line must start within 2 em of the caption's left edge.
  - **`stats.removed` isn't shown anywhere in the UI.** The per-page `dropped` counts live
    in the cached page JSON and are lost when "Convert again" re-extracts.
  - **The stamp rule for 1–3-page scans.** `min(3, pages // 4 + 1)` means one clear stamp
    reading establishes the stamp on a scan of under 4 pages. After that, looser matches
    near its position go too.
  - **A weak test.** `test_ocr_scan_with_real_engine` checks headings with `all(...)`,
    which also passes when there are no headings at all.
- **Vector-drawn maths beside body text** (OpenStax Physics answer keys and worked
  examples) is not shown. The surrounding words are in the flow, but maths drawn as paths
  with no text layer has no picture, as on main. A fix would crop just the path clusters
  that have no text over them.
- **pdfplumber engine:** the new tests pass on both engines. The benchmark was run on PDFium
  only, the default.
