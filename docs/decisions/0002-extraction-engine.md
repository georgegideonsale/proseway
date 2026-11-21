# 2. PDFium for characters, our own layout analysis, pdfplumber for tables

- Status: accepted
- Date: 2026-11-21

## Context

We need structured, faithful text: reading order, headings, footnotes, tables, figures, and the page number of every block. It has to be fast on an ordinary laptop with no GPU and licence-compatible with Apache-2.0. `docs/research/extraction-options.md` compares the options and `docs/research/licenses.md` records the licences.

Rejected on licence grounds:

- **PyMuPDF / pymupdf4llm:** AGPL.
- **marker / surya:** GPL code, and model weights that restrict commercial use.
- **MinerU:** AGPL components.
- **Nougat:** non-commercial weights.

The ML layout engines (Docling) are accurate but pull in PyTorch (about 1–2 GB) and run at a few seconds per page on CPU. That's too heavy for the default install.

## Decision

- **Stage 1 (per page):** read characters with **PDFium** through `pypdfium2` (Apache-2.0/BSD-3). This gives position, font name, size and angle. We fall back to **pdfplumber** (MIT) only for table detection on pages that have enough ruling lines. `PROSEWAY_ENGINE=plumber` switches all extraction to pdfplumber, for comparison.
- **Stage 2 (whole book):** our own heuristics, in `pipeline/layout.py`. They detect repeated headers and footers within a window of nearby pages, find page numbers by pattern and position, order two columns, rejoin line-break hyphens using the book's own vocabulary, find headings from font-size ranks, find footnotes (small text at the bottom plus superscript markers), and pick out lists, code (monospace fonts), equations (math fonts) and captions.
- **OCR:** optional, with **RapidOCR** (Apache-2.0 code and models, ONNX, no PyTorch) as the `ocr` extra. Without it, scanned pages are kept as page images and the reader explains how to enable OCR.
- **Docling:** stays a documented future option for a "high accuracy" mode (see `ROADMAP.md`).

## Measurements

From `scripts/benchmark.py`, on an i7-1165G7 laptop. Full table in `PROGRESS.md`.

- *Pride and Prejudice* (479 pages): PDFium 16 s against pdfplumber 65 s. Both score 0.968 similarity to the Gutenberg text.
- *Erdős discrepancy* (arXiv, maths): PDFium's reading order is better (0.86 against 0.80 layer-order similarity).

## Consequences

- Fast and light: about 5 MB of native code and no models in the default install.
- Heuristics will miss on unusual layouts. Each stage records what it removed (`stats.removed`), so problems can be diagnosed.
- Every converted book keeps its per-page checkpoints, so we can improve the pipeline and re-convert without losing annotations (ADR 0003).
