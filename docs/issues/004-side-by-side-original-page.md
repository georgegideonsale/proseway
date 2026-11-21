# Side-by-side original PDF page view

**Labels:** enhancement, reader, conversion, v2

## Problem
Converters get things wrong: dropped lines, invented OCR text, tables and math garbled (marker#1081, marker#988, docling#1640, docling#2976). When the reflowed text looks wrong, the reader needs to see the source page to trust or correct it. This is also how people check citations and page numbers.

## Proposed approach
- Each converted block keeps provenance: source page number and bounding box. Store this at import time.
- On desktop, a split view shows the reflowed text on the left and the rendered PDF page on the right, rendered locally with PDF.js or a server-side raster. The two sides stay in sync: scrolling the text moves the page, and the current block is outlined on the page.
- On the phone, "Show original page" opens a full-screen page image with pinch zoom, centered on the block.
- A tap on a figure, table or equation offers "view original", which crops the source region.
- From the original page, "Report problem on this page" feeds the correction tools in issue 011.

## Acceptance criteria
- [ ] For any paragraph, the original page opens in under 500 ms on desktop.
- [ ] The highlighted bounding box matches the block on the source page for at least 95% of blocks in the test corpus.
- [ ] Works for scanned PDFs too, showing the image only.
- [ ] Highlights made in the reflowed text show their source page number in exports.

## Notes
- Keep the original PDF in the library store. Do not delete it after conversion.
- Do not render pages on the phone. Serve pre-rendered tiles or images from the desktop over LAN, with caching.
