# Roadmap

What's planned after 0.1.0, roughly in order of value to readers. Each item has a draft issue in [`docs/issues/`](docs/issues/) with the problem, a proposed approach, and acceptance criteria.

## Next (0.2)

- **HTTPS for phone sharing.** A local certificate the phone can trust. This unlocks an installable app on the phone (PWA) with offline reading.
- **Side-by-side original page.** Show the original PDF page next to any paragraph, to check the conversion or look at a complex figure. (`004-side-by-side-original-page.md`)
- **Conversion correction tools.** Mark a paragraph as a header to remove, merge two paragraphs, or fix a heading level. Corrections survive re-conversion. (`011-conversion-correction-tools.md`)
- **Adjustable highlight boundaries.** Drag the ends of an existing highlight.
- **Paginated reading mode.** Page turns as an alternative to scrolling.
- **EPUB import.** (`007-epub-import.md`)

## Later

- **Dictionary lookup** with offline dictionaries. (`001-dictionary-lookup.md`)
- **Flashcards from highlights** with spaced repetition. (`002-flashcards-spaced-repetition.md`)
- **Text-to-speech** using the system's voices. (`003-text-to-speech.md`)
- **Annotation sync** between devices on the same network. (`006-lan-annotation-sync.md`)
- **A notebook of all highlights** across books. (`010-global-annotation-library.md`)
- **Export templates** (Obsidian, Logseq). (`012-export-templates-obsidian.md`)
- **Watch folder** for automatic import. (`013-watch-folder.md`)
- **Reading statistics.** (`009-reading-statistics.md`)
- **OPDS catalogue** for e-reader apps. (`008-opds-catalog.md`)
- **Better OCR quality** for old scans, and an optional high-accuracy layout engine (Docling), offered as separate downloads. (`014-ocr-scanned-pdfs.md`)
- **Optional local AI** (explain a passage, summarise my highlights) through Ollama. Off by default, and nothing leaves the computer. (`005-local-ai-ollama.md`)

## Not planned

- Cloud accounts, sync through our servers, or telemetry.
- DRM removal or downloading books.
