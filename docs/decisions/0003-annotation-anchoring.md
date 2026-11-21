# 3. Anchoring highlights with block ids plus quoted text

- Status: accepted
- Date: 2026-11-21

## Context

Losing highlights is the complaint we heard most about other readers. Common causes:

- annotations keyed to a file hash or page offset that no longer matches;
- annotations deleted along with the book;
- saves that happen late.

We will improve the converter over time, and re-converting a book must not break anyone's notes.

## Decision

- **Block ids:** a SHA-1 of the block's *normalised* text (case-folded, whitespace and punctuation removed), with a counter for duplicates. Small changes such as re-joined hyphens or different spacing keep the same id.
- **What each annotation stores:** the W3C Web Annotation selectors, namely the block id with character offsets (TextPositionSelector) and the exact quote with 32 characters of prefix and suffix (TextQuoteSelector). It also stores the source page.
- **Re-anchoring order:**
  1. Same block and offsets, same quote.
  2. The quote inside the same block.
  3. The quote anywhere in the book, best context match, closest to the original page.
  4. A fuzzy match within ±3 pages (`rapidfuzz`, needs 85 or above).
  5. Otherwise the annotation is kept and flagged **orphaned**. It shows in the notes panel and in exports, and is never deleted.
- **Re-conversion:** every re-conversion and every backup restore runs this.
- **Saving:** each highlight is saved with an immediate API call. The reading position saves after a short pause and on page hide.
- **Deleting a book:** its annotations are written to `detached-annotations/<sha256>.json`. They are reattached automatically if the same PDF is imported again.

## Consequences

- Tests cover each step, including a simulated pipeline change (`tests/test_anchoring.py`, `test_reconversion_keeps_highlights`).
- Highlights that span blocks are stored as one row per block, sharing a `group_id`.
