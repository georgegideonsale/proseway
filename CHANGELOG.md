# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-21

First release.

### Added
- **PDF conversion**, faithful and reflowable:
  - removes running headers, footers and page numbers, and rejoins words split across lines;
  - reads two-column pages in the right order;
  - detects headings, lists, footnotes (linked from where they're cited, and opening in place), tables, figures with captions, equations (kept as images, with their text for search) and code;
  - records the source page of every block.
- **Engines and OCR:** a fast PDFium engine, with pdfplumber for tables. Optional OCR for scanned pages (RapidOCR).
- **Background conversion:** per-page progress, cancel and resume, and a watchdog for stuck pages.
- **Library:** covers, reading progress, bulk import by drag and drop, rename, convert again, and remove (notes are kept).
- **Reader:**
  - four themes, five typefaces (including OpenDyslexic), and size, spacing and line-length controls;
  - table of contents, full-text search, page numbers in the margin, time left in chapter, and a "Back to" button after jumps;
  - keyboard shortcuts.
- **Annotations:** highlights in five colours, notes, bookmarks, and copy with page reference. Anchored by block id and quoted text, so they survive re-conversion.
- **Export:** Markdown export of notes, JSON backup and restore of all notes, and EPUB 3 export.
- **Phone reading:** over the home network, with QR or code pairing, revocable devices and an automatic switch-off.
- **Security:** Host-header and CSRF protection, a strict Content Security Policy, and local-only management endpoints.

[Unreleased]: https://github.com/george-gideon-S/proseway/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/george-gideon-S/proseway/releases/tag/v0.1.0
