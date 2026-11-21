# Progress log

This file is updated as work happens. Statuses mean:

- **Working**: I ran it and saw it work.
- **Untested**: built but not yet exercised end to end.

## Current state (2026-11-21, overnight session)

### Working
- **Vertical slice**, tested by hand in the in-app browser against a real book (*The Legend of Sleepy Hollow*):
  1. Import through the API, then conversion in a background process, with page progress shown in the library.
  2. Open in the reader, then select text and get the highlight toolbar.
  3. Save a green highlight.
  4. Kill and restart the server, then reload: the highlight is still there and the reader reopens at the saved position.
- Pipeline on the synthetic PDFs (`tests/pdfgen.py`):
  - running header and page numbers removed;
  - two-column page read left column first;
  - footnote marker linked to its footnote;
  - line-break hyphens joined.
- Pipeline on *Pride and Prejudice* (479 pages, 60 s, peak 85 MB):
  - removed 478 running lines and 214 page numbers;
  - fixed the drop caps;
  - joined 1,834 line-break hyphens and kept 61 real ones.

### Untested so far
- Phone sharing over LAN, EPUB export, backup and restore through the UI, search and notes panel through the UI, OCR.

## Decisions
See `docs/decisions/`.

## Notes and problems hit
- **Name:** I chose "Proseway" after checking PyPI, GitHub and the web. Nothing with that name came up.
- **Preview launcher crash:** the browser pane's dev-server launcher crashed the Python server with 0xC0000005 before any output. Started directly with `Start-Process`, the same command runs fine. So I start it that way for browser checks. It looks specific to this machine's launcher, not to the app.
- **Silent exit code 5:** some background shell commands on this machine exit with code 5 and no output, including `npm view` loops and piped background jobs. Re-running in the foreground, or without pipes, worked.
- **gutenberg.org was down (HTTP 503):** the reference texts came from the official mirror, gutenberg.pglaf.org.
