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
- **Deliberate trade-off:** p227 and p664 are *empty* exercise tables (headers and row
  labels only, shaded cells). They become figure images with their labels as
  `figure_text`. Before, they were 14 one-word paragraphs.
- **Not ideal:** p254's small P(x) box becomes a figure.
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

`test_text_inside_figures_belongs_to_the_figure` covers:
- a vector diagram with 7 pt labels, two of them overlapping, gets every label in `figure_text`;
- an annotated raster screenshot keeps its annotations;
- a shaded, outlined sidebar of body-size prose stays a paragraph;
- the caption follows its figure and is linked to it, and FTS search finds a label.

`uv run pytest`: 56 passed. `uv run ruff check .`: clean.

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
- **The table detector is off on OCR pages**, where boxes are too uneven to read as a grid.
- **pdfplumber engine:** the new tests pass on both engines. The benchmark was run on PDFium
  only, the default.
