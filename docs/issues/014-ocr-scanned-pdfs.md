# OCR for scanned PDFs

**Labels:** enhancement, conversion, later

## Problem
Many older books are scans with no text layer. Without OCR they cannot be reflowed at all. OCR is also where converters fail worst: marker#1081 shows OCR inventing text from bleed-through, and docling#1343 reports an EasyOCR memory leak. OCR model choice is a hot topic (docling#2497 DeepSeek-OCR, 36+; docling#2495 PaddleOCR-VL, 20+), and so is install weight (docling#2535 docling-slim, 43+).

## Proposed approach
- Detect pages with no usable text layer during import and offer OCR for those pages only.
- Default engine: **Tesseract** (small, CPU-only, many languages, installed on demand). Optional heavier engines (for example docling's OCR backends or a VLM OCR) are a separate download with their size shown beforehand.
- Language picked from the book's metadata or by the user. Run OCR page by page in a worker, with progress, cancel and resume.
- Keep the per-word confidence. Low-confidence words are underlined faintly (optional), and the page is listed in the conversion report (issue 011).
- Side-by-side view (issue 004) is essential for checking OCR output.
- Guard against invented text: compare the OCR line count and layout with the detected text regions, and flag pages where the output repeats or loops.

## Acceptance criteria
- [ ] A 300-page scanned book converts with Tesseract on a 4-core laptop CPU in under 30 minutes, with peak memory under 2 GB.
- [ ] Cancelling and resuming continues from the last finished page.
- [ ] No OCR model is downloaded without an explicit user action that shows the size.
- [ ] On the test corpus, pages with repetition loops are flagged 100% of the time.

## Notes
- Fully offline once the models are installed. Language packs are downloaded only on request.
