# Tools for fixing conversion errors

**Labels:** enhancement, conversion, v2

## Problem
No converter is right on every book. The top complaints about docling and marker are headers and footers in the text (docling#1272, marker#433, marker#557), or real headers removed (docling#3693); multi-column reading order (docling#1203, #1380, marker#50); flat heading levels (docling#652, 14+; docling#1023); and dropped lines or invented text (marker#1081, marker#988). A reader who hits one bad page today has no fix except re-running the whole book with different flags.

## Proposed approach
- After import, a **conversion report** lists pages with low confidence: a character-count mismatch with the PDF text layer, OCR used, an unusual number of columns, a table detected.
- **Per-book rules**, applied without a full re-conversion:
  - "Treat this line as header/footer": choose the text or region on the original page (issue 004). The rule applies to similar lines on all pages, with a preview of what will be removed.
  - "Restore removed text" for a page.
  - Heading level adjustments: promote or demote a heading, and apply the same change to every heading of that style.
  - Join or split paragraphs, and fix a mis-split hyphenated word with "apply everywhere".
- **Re-convert pages:** re-run selected pages with different settings (force OCR, a column count, the table model on or off) and show a diff before accepting.
- Corrections are stored as a rule list next to the book, so they survive converter upgrades and can be exported for sharing (with the user's consent).
- Annotations are re-anchored after any correction (text quote plus source page), and any annotation that could not be re-anchored is reported.

## Acceptance criteria
- [ ] Marking a running header on one page removes it from every page where it repeats, with a preview count before applying.
- [ ] Re-converting 3 pages of a 600-page book takes less than 10% of a full conversion.
- [ ] No existing highlight is lost after a correction. Any that move are listed.
- [ ] All corrections can be undone.

## Notes
- This is the main way Proseway can beat "just run marker": a quick fix for the one bad page.
