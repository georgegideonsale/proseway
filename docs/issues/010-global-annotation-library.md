# Annotations across all books (global notebook)

**Labels:** enhancement, annotations, v2

## Problem
Once a library grows, readers cannot remember which book holds a note. readest#5080 ("Global Annotation Library", 9+) and readest#5398 (centralize notes and highlights) ask for one place to see everything. readest#1740 asks for tags on notes (7+). zotero#2391 asks to hide or filter annotations (5+, 23c).

## Proposed approach
- A "Notebook" view listing every highlight, note and bookmark across books, with filters for book, color, tag, date range and "has note", and full-text search through SQLite FTS5 over highlight and note text.
- Free-form tags on annotations, with autocomplete.
- Each item opens the book at its location. Back returns to the notebook with the filters kept.
- Bulk actions: export the selection as Markdown, change color, add a tag, delete (with undo).
- Annotations whose book was deleted ("kept" per the v1 rule) appear with a "book removed" badge and still export.

## Acceptance criteria
- [ ] Search across 20,000 annotations returns in under 200 ms.
- [ ] Filters combine (for example: yellow + tag "argument" + 2026).
- [ ] Exporting a filtered selection produces Markdown grouped by book and then by chapter.
- [ ] Works on the phone layout.

## Notes
- Do not move annotations out of the book's record. This view is a query over the existing store.
