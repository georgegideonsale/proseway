# Progress report: Proseway v0.1.0

Overnight build, 2026-11-21. Private repository: https://github.com/georgegideonsale/proseway

Statuses in this file:
- **Working**: I ran it and saw it work, and say how.
- **Untested**: built but not exercised end to end.

## Since v0.1.0 (on main, unreleased)

v0.2 work is done on separate branches, one per task. Each one is reviewed (code review, plus the full test suite on its own worktree) and merged only after you approve it. The worker's detailed notes for each branch are in `docs/progress/`.

### Merged: HTTPS phone sharing and server hardening (`claude/https-sharing-4902f2`, details in `docs/progress/https-sharing.md`)

**What it adds:**
- **Secure phone sharing (HTTPS) is the default.** Proseway makes one local certificate authority (CA) for each LAN address the computer has.
  - The CA is name-constrained: it can only vouch for that one IP, with no DNS names, email addresses or URIs.
  - It signs a server certificate for that address only.
  - A separate plain-HTTP setup page, on port+1, serves the CA and step-by-step instructions for iPhone and Android.
  - Plain HTTP stays available as an explicit, remembered choice.
- **Pairing cookies are separate for each scheme.** Over HTTPS the cookie is `__Host-pw_device`, with its own token hash, so a token issued over plain HTTP is refused over HTTPS, and the other way round.
- **Cleanup when a phone is unpaired:**
  - The "not paired" 401 sends `Clear-Site-Data`.
  - The service worker and the page delete their caches on a 401.
  - Book images are fetched network-first.
- **CA safety:**
  - A CA is never silently replaced; a damaged or expiring one is an error that points to `proseway --new-phone-certificate`.
  - Keys get owner-only permissions on POSIX, and a protected access list (you plus SYSTEM) on Windows.
  - TLS ciphers are pinned to ECDHE with AES-GCM or ChaCha20.
- **Size limits are now enforced on request bodies while they stream in**, including chunked uploads without `Content-Length`. This closes the v0.1 open issue.
- **The EPUB language** (`dc:language` and `xml:lang`) comes from the PDF's `/Lang`, read with pdfminer. It is `und` if the PDF has none; Proseway never guesses from the text.
- **Sharing dialog accessibility:** focus moves to the heading of each step, the fingerprint and code have visually hidden labels, and the hint is read once.
- **Test harness:** each e2e server gets its own OS-assigned port, so test runs in different worktrees can't drive each other's servers. Before this fix, they could and did.

**Working (verified by running it):**
- **pytest:** 75 passed, 1 skipped (a POSIX-permissions test, skipped on Windows), on the branch and again on main after the merge. The tests run against a real uvicorn TLS listener and check:
  - OpenSSL and cryptography both reject certificates forged with the CA key for another IP (router, public address) or with an extra email, URI or DNS name;
  - the exact `__Host-` cookie attributes;
  - scheme separation;
  - wrong Host (421), missing CSRF header, foreign Origin, and phone-only 403s over TLS;
  - only ECDHE AEAD suites are accepted;
  - the Windows access list is read back;
  - body limits on declared and chunked bodies;
  - export never touches pdfium.
- **Lint and unit tests:** ruff clean; vitest 11 passed.
- **Playwright on main after the merge:** desktop 9/9; phone 8 passed and 1 skipped (a desktop-only test, skipped by design).
- **On this machine,** Chromium and Python launches crash intermittently (0xC0000005) under memory pressure. Several runs had to be repeated for that reason; none of the repeats failed an assertion.

**Untested (needs a real phone):**
- installing the CA on iOS and Android, and each platform enforcing the name constraints;
- installing the app on the phone and reading offline;
- whether unpairing really clears a phone's offline data (iOS Safari's support for `Clear-Site-Data` is unverified);
- how each platform displays the fingerprint;
- the Windows Firewall prompt for the setup port.

**Open:**
- If the computer's address changes, phones have to trust a new CA. Each CA works for one address only.
- The plain-HTTP setup page is trust-on-first-use. If someone on the network tampers with it, the attacker's CA would have no constraints. SECURITY.md says so and recommends sending the certificate straight from the computer.

### Still in review

- **Reader: bounded chapter window** (`claude/reader-chapter-window-39d481`).
- **Pipeline: figures, tables without ruling lines, OCR headers** (`claude/pipeline-quality-50d649`). An independently built alternative, kept as `keep/pipeline-quality-7fe68e`, was reviewed and not chosen.

## Summary

Proseway is a local Python server with a React reader. It converts a book PDF into a reflowable edition, keeps the original page number on every block, and lets you highlight, annotate and bookmark. You can read on a phone over your home Wi-Fi after pairing, or export an EPUB. Your notes can be exported as Markdown or as a JSON backup that can be restored. It has no accounts, no cloud and no telemetry.

## What's done, and how I checked it

### Working (verified by running it)

| Area | How it was verified |
|---|---|
| **The core flow:** import, convert with progress, read, highlight, note, bookmark, restart the app, everything still there, export Markdown | Playwright end-to-end test (`web/e2e/reading.spec.ts`), at desktop size and on Pixel 7 phone emulation. It kills and restarts the real server process mid-test. All passed. Also done by hand in the in-app browser. |
| **Saved reading position** | Reopening a book returns to where you were, checked by hand after a restart. Saving uses a debounced save plus a `keepalive` save when the page is hidden. |
| **Highlights:** five colours, notes, word-snapping, groups across paragraphs, undo on delete | End-to-end test plus vitest unit tests for selection-to-offset mapping and word snapping. |
| **Search, contents, notes and appearance panels**, and keyboard shortcuts (T, /, N, A, B, H, Esc) | End-to-end tests for search jumps and Escape behaviour. The panels were checked by hand at 1280×800 and 375×812. |
| **Themes and fonts** (Paper, Sepia, Dusk, Night; Literata, Source Serif, Atkinson, OpenDyslexic, system serif), persisted per device | End-to-end test (Night plus OpenDyslexic survive a reload). Screenshots in `docs/screenshots/`. |
| **Annotations survive re-conversion** (block id, then quote, then fuzzy, then kept as orphaned) | `tests/test_anchoring.py` (7 tests) and `test_reconversion_keeps_highlights`. |
| **Deleting a book keeps its notes**, and re-importing brings them back | `test_delete_keeps_notes_and_reimport_restores_them` |
| **JSON backup and restore**, including restoring before the PDF is imported, and idempotent restore | `test_backup_and_restore_into_a_fresh_library` |
| **EPUB 3 export** (valid zip structure, well-formed XHTML, navigation) | `test_epub_export_is_valid`. **Not** checked with epubcheck or a real e-reader app. |
| **Phone sharing over the LAN, tested on this machine's real Wi-Fi address (10.0.0.105)** | With sharing off, the LAN address refuses connections. An unpaired request gets 401. A wrong Host header gets 421. A wrong code gets 403. Pairing works and sets an HttpOnly, SameSite=Strict cookie. A paired device can read but gets 403 on delete and on sharing control. A used code gets 403. Turning sharing off closes the port. The pairing page's layout and wrong-code message were checked at 375 px. |
| **Password-protected, corrupt and non-PDF files** get friendly errors | `tests/test_pipeline.py` |
| **Cancel and resume:** resume only re-extracts the missing pages | `test_resume_skips_finished_pages` |
| **Large books** | A 959-page OpenStax textbook converted in a background process in 3.8 minutes, peak 387 MB, with the UI responsive. The reader loads chapter by chapter and uses `content-visibility` for long chapters. |
| **Optional OCR** for scanned books (RapidOCR) | The 37-page image-only *Trifles* scan was converted to text, at about 3.5 s per page. Quality is moderate (see below). |
| **Clean install from the wheel** (fresh virtualenv, empty uv cache) | `proseway --version`, served the web app, imported and converted a book. |
| **Clean install from a fresh git clone** with `uv tool install <clone>` (isolated tool and cache directories) | The build hook built the web app with pnpm. The installed app served the UI. |
| **Lint and tests** | `ruff check .` clean. 43 pytest tests passed. 8 vitest tests passed. 13 Playwright tests passed (7 desktop, 6 phone; 1 desktop-only test skipped on phone). These include 8 axe-core accessibility audits (WCAG 2.2 A/AA, serious and critical findings) of the library, reader and notes panel in the Paper and Night themes. |
| **Accessibility audit** | axe-core found two real problems, both now fixed: the phone-sized "Read on your phone" button had no accessible name, and Dusk's yellow highlight was 4.09:1. A contrast table computed from the tokens is in ADR 0006. |

### Untested, or only partly tested
- **Pairing a real phone:** the pairing *code* was tested over the real LAN address through the API, and the pairing page was checked in a phone-sized browser. I didn't type a live pairing code into the browser UI. It's a credential on a non-localhost address, and my safety rules don't allow that. I also didn't scan the QR code with an actual phone.
- **Installing from the GitHub URL** (`uv tool install git+https://github.com/...`): the repo is private, so that URL needs your credentials. The same install from a local clone works.
- **macOS and Linux:** I only used the app by hand on Windows 11. **GitHub Actions CI is green** on ubuntu (Python 3.10 and 3.12), windows and macos: lint, type-check, web build, unit tests and the 43 API/pipeline tests. On ubuntu it also runs the Playwright and accessibility tests and builds the wheel with a smoke test. I haven't used the app by hand on macOS or Linux.
- **Service worker / offline PWA:** it registers on `localhost` in production builds, but I didn't test offline reading.
- **EPUB files in real readers:** not opened in Apple Books, KOReader or similar.
- **Screen readers:** ARIA roles, labels, focus management and keyboard paths are implemented. I didn't run NVDA or VoiceOver.

## Accuracy and performance per test book

Measured with `scripts/benchmark.py` on an i7-1165G7 laptop (4 cores, 7.6 GB RAM, no GPU), Windows 11, PDFium engine (the default). All books are public domain or openly licensed and are downloaded by `scripts/fetch_test_books.py`; none are committed.

| Book (category) | Pages | Time | s/page | Peak RAM | Layer recall | Layer order | Ref similarity | Ref recall | Ref precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *Pride and Prejudice*, Planet eBook PDF (novel) | 479 | 16.6 s | 0.035 | 78 MB | 0.951 | 0.967 | **0.968** | 0.951 | 0.996 |
| *The Legend of Sleepy Hollow* (smoke test) | 43 | 1.7 s | 0.041 | 186 MB | 0.946 | 0.964 | **0.975** | 0.959 | 0.993 |
| OpenStax *University Physics 1* (large textbook, figures, tables) | 959 | 210 s | 0.219 | 400 MB | 0.968 | 0.954 | – | – | – |
| OpenStax *Introductory Statistics* (textbook) | 913 | 82.5 s | 0.090 | 234 MB | 0.952 | 0.967 | – | – | – |
| arXiv 2212.10560 *Self-Instruct* (two-column paper) | 23 | 4.2 s | 0.182 | 184 MB | 0.940 | 0.678 | 0.368 | 0.927 | 0.423 |
| arXiv 1509.05363 *Erdős discrepancy* (maths) | 27 | 4.0 s | 0.147 | 151 MB | 0.937 | 0.865 | 0.750 | 0.979 | 0.736 |
| Gibbon, *Decline and Fall* vol. 1, 1850 scan with OCR layer (footnotes) | 652 | 53.5 s | 0.082 | 411 MB | 0.962 | 0.721 | 0.646 | 0.904 | 0.891 |
| *Trifles*, image-only scan, **with OCR add-on** | 37 | 138 s | 3.73 | 485 MB | – | – | 0.137 | 0.085 | **0.852** |

Engine comparison: pdfplumber, the fallback engine, gives the same accuracy on the novels and is 3.6–4× slower. On *Pride and Prejudice* it took 65.9 s against 16.6 s. On the maths paper PDFium's reading order is better: 0.865 against 0.799. The full table, including the pdfplumber runs, is in `bench-results/benchmark.md` after running `scripts/benchmark.py`. That folder is git-ignored.

Peak RAM is the converting process (resident set). The reader UI stays responsive during conversion, because conversion runs in a separate process.

How to read the columns:
- **Layer recall:** the share of the PDF's own text-layer words that appear in our output. Running headers and page numbers are removed on purpose, so about 0.95–0.98 is the ceiling for books with a header on every page.
- **Layer order:** the similarity of word order to the PDF's text layer. The text layer's own order isn't ground truth for two-column papers or scans.
- **Ref similarity / recall / precision:** compared against an independent text (Project Gutenberg plain text, or the arXiv LaTeX source with markup stripped).
  - Edition differences lower these. The Planet eBook *Pride and Prejudice* follows an older Gutenberg edition.
  - The *Trifles* reference is a four-play collection, while the scan is one play. So recall is low by construction, and **precision** (how many OCR'd words are real words from the play) is the meaningful number.

What I saw reading the output by eye:
- **Novels** (*Pride and Prejudice*, *Sleepy Hollow*): read cleanly.
  - Running headers, footers and page numbers are gone.
  - Drop caps are rejoined ("It is a truth universally acknowledged").
  - Line-break hyphens are joined (1,834 joined, 61 real hyphens kept).
- **Two-column papers:** the columns are read in the right order, and the abstract and body read correctly.
  - Text drawn *inside* figures (the Self-Instruct paper's Figure 1 has overlapping text boxes) comes out garbled.
  - Some author-affiliation symbols end up as tiny paragraphs.
- **Maths:** inline maths becomes plain text with symbols, which is searchable but not typeset. Display equations become cropped images, with their text kept for search.
- **Gibbon (1850 scan with an OCR text layer):** the page-sized scan images are now ignored, and running heads with OCR noise are removed by fuzzy matching. The scan's own OCR text layer is noisy and sometimes interleaves lines, so the output inherits that. Footnotes are detected when their marker is recognisable.
- **Image-only scan (*Trifles*) with OCR:** readable but noisy. Small caps are misread ("SuSaN GLaSrELL"), and the "Digitized by Google" watermark survives on some pages.

## Independent review

A separate reviewer agent, which hadn't seen the build process, reviewed the code, the security of phone sharing, the docs and the install steps. It found **no critical issues and no remote exploit**, and called the local-server and sharing security solid: Host checks, CSRF header, LAN allowlist, device tokens, path traversal, SQL, XSS, CSP.

### Fixed (each with a regression test where it made sense)

- **High: highlight offsets in blocks with characters outside the Basic Multilingual Plane.** The browser counted UTF-16 units while the server counted code points, so highlights near maths letters like 𝑥 were shifted. Offsets are now converted at the boundary. Vitest covers both directions.
- **Watchdog skipped pages silently.** It skipped up to 3 good pages after a stall. Now progress is written per page, only the stuck page is skipped, and the reader shows "Page N couldn't be converted" where it was.
- **Stop during worker start-up** turned into an error, and Resume right after Stop did nothing. Both fixed.
- **Restore:**
  - fields are now validated (types, colours, group ids, timestamps);
  - the whole restore runs in one transaction;
  - it never moves another book's annotation;
  - the middleware and handler size limits now agree.
- **Pairing:**
  - odd input such as non-ASCII codes no longer returns 500 (bytes comparison);
  - per-device failure limits plus a global cap, so one device can't lock everyone out;
  - the LAN listener marks its own requests, so LAN detection no longer depends on comparing addresses;
  - an invalid `minutes` value is rejected cleanly.
- **Hostile page sizes:** renders are capped at 40 megapixels (cover, crops and OCR).
- **EPUB:** XML-invalid characters are stripped everywhere, and page-break ids are unique.
- **Reading position** is now re-anchored after "Convert again".
- **Concurrent duplicate import** no longer returns 500.
- **Escape key:** it closes a footnote popup first, and while you edit a note it cancels the edit instead of closing the Notes panel.
- **Accessibility:**
  - no nested buttons in the "Back to" chip;
  - the footnote popup takes and returns focus;
  - the Notes tabs have tabpanel semantics and arrow keys;
  - single-key shortcuts can be turned off (WCAG 2.1.4).
- **Docs:** removed the unused `https` extra, corrected the PDF-header wording, and corrected the watchdog docstring.
- **Licences:**
  - `THIRD_PARTY_NOTICES.txt`, with every bundled font and library licence, is generated at build time and shipped;
  - NOTICE is updated;
  - stale rows in `licenses.md` are fixed.

### Not fixed tonight (logged here)

- **The reader never unloads chapters.** Reading straight through a 1,000-page book keeps every chapter mounted. `content-visibility` keeps rendering cheap, but memory grows on phones. Next step: a window of about 3 chapters.
- ~~**Uploads without `Content-Length` skip the early size check.**~~ Fixed since v0.1.0: limits are enforced on bodies while they stream in.
- ~~**EPUB `dc:language`** is always `en`.~~ Fixed since v0.1.0: it comes from the PDF's `/Lang`, or is `und`.
- **Fonts:** whether Fontsource's range-split font files count as "modified" under the OFL for the two fonts with Reserved Font Names (Source Serif 4, OpenDyslexic) is unsettled. See `docs/research/licenses.md`.

## Known issues

1. **Figures with text inside them** (diagrams, annotated screenshots) can produce garbled lines, because the text boxes overlap. We should treat text inside figure areas as part of the figure.
2. **Tables without ruling lines** aren't detected as tables. Their cells come out as short paragraphs.
3. **OCR quality** on old scans is moderate. The OCR'd heading sizes are estimates, so some OCR lines are classed as headings.
4. **The table of contents** comes from the PDF outline when there is one, and otherwise from the detected headings. Books with neither get "Pages X–Y" chunks.
5. **Phone sharing over HTTPS** is now the default (since v0.1.0, see above), with plain HTTP as an explicit fallback. It hasn't been tried with a real phone yet.
6. **GitHub private vulnerability reporting** can only be enabled once the repo is public. SECURITY.md already points to it. Enable it with `gh api -X PUT repos/georgegideonsale/proseway/private-vulnerability-reporting` after publishing.
7. **The GitHub username** shown by `gh auth status` was `george-gideon-S`, but the account's actual login is `georgegideonsale`, so the repo and all links use `georgegideonsale`.

## Problems on this machine, and what I did instead

- **Native crashes (0xC0000005, exit code 5, `spawn EPERM`):** some process launches crashed or failed intermittently. This hit the browser pane's dev-server launcher, Playwright's Chromium launched directly from `node`, `filter-branch`'s forks, and creating virtualenvs outside the project folder. Workarounds that worked:
  - starting the server with `Start-Process`;
  - running Playwright through `pnpm exec`;
  - doing the history rewrite with `fast-export`/`fast-import`;
  - running clean-install tests inside the git-ignored `data/` folder.
- **gutenberg.org was down (HTTP 503):** reference texts came from the official mirror, gutenberg.pglaf.org.
- **Claude Design:** not used. The design was done with the vetted `frontend-design` and `accessibility` skills, my own token system (`docs/decisions/0006-design-system.md`), and visual review of screenshots at phone and desktop sizes in light and dark themes.
- **Claude in Chrome:** used briefly for the reading-UX study. It was your own browser profile, signed in to Readest, so I didn't open books there to avoid touching your account. I used public documentation pages instead (`docs/research/ux/reading-ux-notes.md`).
- **Git history was rewritten once, before the first push,** to remove your Windows username from a research note. Nothing was lost; commit hashes changed.

## Skills used

Six vetted skills are pinned in `.claude/skills/`, each with an `UPSTREAM` file: frontend-design, webapp-testing, accessibility, test-driven-development, systematic-debugging, verification-before-completion. Details and the vetting notes are in `docs/research/skills.md`.

## Key decisions (ADRs in `docs/decisions/`)

- **0001:** a local Python server plus a web reader, installed with one command.
- **0002:**
  - PDFium (pypdfium2) for characters, with our own layout heuristics.
  - pdfplumber only for tables.
  - OCR as an option (RapidOCR).
  - AGPL and GPL extractors (PyMuPDF, marker, MinerU) excluded on licence grounds.
- **0003:** anchoring by block id plus quoted text, W3C style. Never deletes an annotation.
- **0004:** SQLite (WAL plus FTS5), and a converter worker process with a watchdog.
- **0005:** phone sharing that is off by default, opt-in, paired and revocable, with EPUB as the offline route.
- **0006:** the design system (bookbinding motif) and the measured WCAG AA contrast table.

## Recommended next steps

1. Review the repo, then make it public:
   - enable private vulnerability reporting;
   - push the `v0.1.0` tag, which triggers the release job that attaches the wheel;
   - optionally publish to PyPI so the install becomes `uv tool install proseway`.
2. HTTPS for phone sharing is built (see "Since v0.1.0"). Next: try it with a real iPhone and Android phone, covering certificate install, name-constraint enforcement, and installing the app for offline reading.
3. Pipeline: treat text inside figure regions as part of the figure; detect tables without ruling lines; adapt header detection for OCR'd pages.
4. A side-by-side "original page" view, to check conversions and look at complex figures.
5. Test with screen readers (NVDA, VoiceOver), and open the EPUB export in KOReader and Apple Books.
