# Proseway test corpus

The manifest is `scripts/test_books.json`. A download script fetches the PDFs, and none are committed to the repo. Every `pdf_url` was checked on 2026-11-21 with `curl -sIL` (HTTP 200, `application/pdf`, size noted) and a ranged read (`-r 0-1023`) to confirm the `%PDF` magic bytes. Smaller files were also opened with `pdfinfo`/`pdftotext` to confirm their layout and whether they have a text layer. The lead adds the sha256 values.

## Operational caveats

- **gutenberg.org was down for maintenance (HTTP 503, Retry-After 6h) when this was checked.** Each Gutenberg reference lists the canonical `gutenberg.org/cache/epub/N/pgN.txt` URL plus a `mirror_url` on `gutenberg.pglaf.org`, and all mirror URLs returned 200 `text/plain`. The script should fall back to the mirror.
- archive.org downloads 302-redirect to a datanode, and arXiv `e-print` URLs 301-redirect to `/src/<id>`. Use `curl -L`.
- arXiv URLs are pinned to a version (`v2`, `v6`) so the sha256 stays stable.
- Gutenberg text files carry a PG header and footer. Strip everything outside the `*** START` and `*** END` markers before scoring.

## Items

| id | category | pages | MB | license | reference |
|---|---|---|---|---|---|
| pride-prejudice | plain novel | 479 | 1.6 | PD (Planet eBook typesetting) | Gutenberg #1342 |
| openstax-univ-physics-1 | textbook (large) | ~1000 | 81.5 | CC BY-NC-SA 4.0 | none (web HTML exists) |
| openstax-intro-stats | textbook (smaller) | ~900 | 26.6 | CC BY 4.0 | none (web HTML exists) |
| arxiv-self-instruct | two-column paper | 23 | 4.3 | CC BY 4.0 | arXiv source |
| arxiv-erdos-discrepancy | math-heavy | 27 | 0.44 | CC BY 4.0 | arXiv source |
| gibbon-decline-fall-v1 | footnote-heavy | 656 | 38.5 | PD (1850) | Gutenberg #731 |
| trifles-scan-imageonly | scanned, no text layer | 37 | 0.64 | PD (1916) | Gutenberg #10623 (excerpt) |
| sleepy-hollow-smoke | smoke test | 43 | 0.32 | PD (Planet eBook typesetting) | Gutenberg #41 |

### 1. Plain novel: Pride and Prejudice (Planet eBook PDF)
- **Why:** A born-digital (InDesign) single-column novel with a running header and footer on every page, so it tests header/footer removal and paragraph reflow across page breaks.
- **Sources tried:** Gutenberg publishes no PDF for #1342 or any other mainstream novel. The Wikisource exporter (ws-export) timed out, and it regenerates the file on each request, so the sha256 would not stay stable. Archive.org copies are mostly in-copyright lending-library editions.
- **License:** The text is public domain. Planet eBook offers the PDF as a free download. Typographic layout is not copyrightable in the US, but the PDF carries Planet eBook branding.
- **Edition caveat:** The PDF follows the *old* Gutenberg #1342 transcription (`backtick' quotes, CAPS for emphasis, "Chapter 1"). The current #1342 is a different transcription (1894 George Allen edition, curly quotes, `_italics_`, "Chapter I."). The words agree, but case, punctuation and emphasis markup do not. Score case-folded and with punctuation normalized, with `_` markers stripped. Gutenberg #42671 is an alternate reference.

### 2. Textbooks: OpenStax
- **University Physics Vol. 1:** About 1,000 pages and 81 MB, with figures, tables, worked examples, equations, sidebars and problem sets. **The OpenStax CMS now lists it as CC BY-NC-SA 4.0**, as it does most "2e" and recent books. That is fine for internal testing that redistributes nothing.
- **Introductory Statistics (1st ed.):** **CC BY 4.0**, about 900 pages, 27 MB, and heavy on tables. This is the smaller one and also the license-clean one.
- Biology 2e is 401 MB and NC-SA, so it was skipped as too large. The CMS API at `https://openstax.org/apps/cms/api/v2/pages/?type=books.Book&fields=title,high_resolution_pdf_url,license_name&limit=250` lists the current PDF URLs and licenses if these asset links change.
- **Reference:** None. The OpenStax web HTML edition (URL in the manifest) could be used for heading and figure-caption checks.
- Page counts are approximate because the PDFs use compressed object streams. Check them with `pdfinfo` after download.

### 3. Two-column paper: Self-Instruct (arXiv 2212.10560v2)
- **Why:** An ACL 2023 camera-ready in A4 two-column layout (checked on page 3 with `pdftotext -layout`). It has a full-width figure, tables and footnotes, so it tests column order and float handling.
- **License:** CC BY 4.0, per the arXiv abs page. Many well-known two-column papers (BART, DPR, XLM-R, SimCSE) are only under arXiv's non-exclusive license, so they were skipped. Sentence-BERT (1908.10084, EMNLP, two-column) is a CC BY-SA alternative.
- **Reference:** The LaTeX tarball (8.1 MB). Turn it into reference text with pandoc or detex, and expect differences around macros, tables and bibliography.

### 4. Math-heavy: The Erdős discrepancy problem (arXiv 1509.05363v6, Tao)
- **Why:** Dense inline and display math with theorem and proof environments, in a short (27-page) single-column paper.
- **License:** CC BY 4.0. Other CC BY math papers: 2311.05762 (Marton's conjecture) and 2012.04125 (Sendov's conjecture).
- **Reference:** The LaTeX source (54 KB). Compare math as LaTeX, or normalize it, rather than as extracted glyphs.
- **Optional extra if needed:** Gutenberg publishes LaTeX-built PDFs of math books together with their `.tex` source, for example #17384 Hilbert's *Foundations of Geometry* (`https://www.gutenberg.org/files/17384/17384-pdf.pdf`) and #33283 *Calculus Made Easy*. These give an exact-match reference, but as TeX, not .txt.

### 5. Footnote-heavy: Gibbon, *Decline and Fall*, Vol. 1 (Milman edition, Boston 1850, IA `historydeclinefa01gibb`)
- **Why:** Several footnotes per page, plus bracketed editor notes by Milman, Guizot and Wenck. Gutenberg #731 has about 1,681 footnotes.
- **Edition match:** Good. Both are the Milman-notes edition, Vol. 1 = Chapters I–XV, and both open with the same editor's preface. In #731 the footnotes are inline `N (return) [ ... ]` blocks rather than at the page foot, so match notes by number and content, not by position.
- **Caveats:** The text layer is IA's hidden OCR, which is noisy ("Koivian", "CHAPTEK"). This item tests footnote detection and placement on imperfect OCR, not born-digital text. The final pages are library due-date slips. The file is 38.5 MB, which is acceptable but the biggest after the OpenStax books.

### 6. Scanned, no text layer: *Trifles* (Glaspell, 1916; IA `trifles00glasgoog`)
- **Why:** This is the original Google Books PDF ("Image Container PDF"). `pdftotext` returns nothing for pages 2–37, so it is truly image-only, and at 0.64 MB it is tiny. Most IA "Text PDF" files carry a hidden OCR layer, so the original Google uploads (`*goog` identifiers) are the reliable source of no-text scans.
- **Caveats:** Page 1 is Google's text-layer boilerplate page ("This is a digital copy of a book..."), so ignore it in tests and scoring. Google's cover page asks for non-commercial and non-automated use. That is a request, not a copyright restriction (the work is public domain), but keep usage internal.
- **Reference:** Gutenberg #10623, Glaspell's *Plays* (1920). Trifles is roughly lines 35–740. It is a different printing, so expect minor variants. IA's OCR'd derivative `trifles00glasgoog_text.pdf` is a useful twin to compare against.

### Smoke test: *The Legend of Sleepy Hollow* (Planet eBook)
- 0.32 MB, born-digital, plain prose, reference Gutenberg #41.
- **Deviation:** It is 43 pages, above the <30 target, but the trim size is small (about 20 letter-size pages of text). No born-digital public-domain PDF under 30 pages with a matching Gutenberg text turned up: Gutenberg has no PDFs of short works, and Planet eBook has no very short titles. If the page limit is strict, the 23-page Self-Instruct paper or the 27-page Erdős paper are the shortest items in the corpus, but they are not prose.
