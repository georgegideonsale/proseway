# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Secure phone sharing (HTTPS), on by default:**
  - a name-constrained local certificate authority for each LAN address, which can only vouch for that one IP;
  - a plain-HTTP setup page with the certificate and iPhone and Android instructions;
  - `proseway --new-phone-certificate` to replace it.
  - Plain HTTP stays available as an explicit choice.
- **EPUB language:** `dc:language` and `xml:lang` come from the PDF's declared language, or `und` when it has none.
- **Bounded chapter window in the reader:** only chapters near your reading position stay mounted, so memory stays bounded on long books.
- **Note lookup:** footnotes and endnotes in unloaded chapters cost one request, to the new `GET /api/books/{id}/blocks/{block_id}`.
- **Reader announcements:** a polite live region announces jumps and note lookups. `aria-busy` is set while a jump is in progress.

### Changed
- **Pairing cookies:** separate for each scheme. `__Host-pw_device` over HTTPS, with its own token hash, so a token issued over HTTP doesn't work over HTTPS.
- **Unpairing a phone:** it now clears that phone's offline copies (`Clear-Site-Data`, and the service worker drops its caches on a 401). Book images are fetched network-first.
- **Sharing dialog:** focus moves to each step's heading, and labels are visually hidden instead of using `aria-label` on code elements.
- **e2e tests:** each test server gets its own OS-assigned port.

### Fixed
- **Request size limits** now apply to bodies as they stream in, including chunked uploads without `Content-Length`.
- **Contents panel:** closing it no longer blanks the reader in current Chromium.
- **Saved position on phones:** restoring it no longer lands a few paragraphs late. A jump's target is held in place against layout shifts.
- **Rapid jumps:** when you make several in a row, the last one wins.

### Security
- **CA:** never silently replaced; a damaged or expiring CA is reported as an error. Keys are owner-only on POSIX and Windows.
- **TLS:** ciphers are pinned to ECDHE with AES-GCM or ChaCha20.
- **Setup page:** reads small request bodies before answering, so clients get a clean 405 or 413.

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

[Unreleased]: https://github.com/georgegideonsale/proseway/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/georgegideonsale/proseway/releases/tag/v0.1.0
