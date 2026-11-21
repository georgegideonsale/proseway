# EPUB import

**Labels:** enhancement, import, v2

## Problem
Readers keep EPUBs and PDFs together and do not want two apps. Converter users ask for EPUB input too: docling#515 (EPUB backend, 18+) and docling#1329 (EPUB and TXT, 9+). readest#774 asks to import Markdown files as books (7+).

## Proposed approach
- Parse EPUB 2 and 3 (OPF manifest, spine, NCX or nav) into Proseway's internal document model, so EPUBs get the same reader, highlights, search, TTS and export as converted PDFs.
- Keep the publisher's semantic HTML. Sanitize it by stripping scripts, keep CSS only as hints, and let the user's typography settings win, with an option to "use publisher fonts".
- Map EPUB footnotes (`epub:type="noteref"` / `footnote`, aside elements) to Proseway's footnote popups.
- Keep the original `.epub` file. Anchor annotations by text quote plus spine position, the same scheme as PDFs.
- Stretch goal: also accept Markdown and plain TXT, splitting chapters on headings.
- DRM-protected files are detected and refused with a clear message.

## Acceptance criteria
- [ ] A test set of 20 public-domain EPUBs (Standard Ebooks, Project Gutenberg) imports with the correct TOC, images and footnotes.
- [ ] Importing a 5 MB EPUB takes under 10 s on a mid-range laptop.
- [ ] Malformed EPUBs (bad XHTML, a missing nav) still import with a warning instead of failing.
- [ ] Re-importing the same EPUB file keeps its existing annotations.

## Notes
- No EPUB export is planned here, but the internal model should not rule it out.
