# Proseway feature research

What readers ask for and complain about in comparable open-source readers and PDF converters, and what that means for Proseway's scope.

## Method

- **Date:** 2026-11-21. Reaction counts are GitHub 👍 counts on that date ("N+"), plus comment counts ("Nc"). They will drift.
- **GitHub issues** were pulled with the REST search API (`search/issues`, `sort=reactions-+1`, `order=desc`), 40 results per repo for the overall top list, then 7–8 results per targeted keyword query.
  - Repos: `readest/readest`, `johnfactotum/foliate`, `koreader/koreader`, `zotero/zotero`, `docling-project/docling` (the old `DS4SD/docling` redirects here), `datalab-to/marker` (the old `VikParuchuri/marker` redirects here).
  - Keyword queries: `highlight export`, `annotations lost`, `footnote`, `sync progress`, `slow large`, `reading position lost`, `PDF text selection`, `time left chapter`, `export markdown`, `hyphen`, `formula`, `table`, `header footer`, `reading order`, `two column`, `reflow pdf`.
  - The bodies of the most relevant issues were read to confirm what they actually ask for.
- **Not covered:** GitHub Discussions, which the issue search API does not return. Readest and KOReader both use Discussions, so some requests are missing here.
- **calibre** tracks bugs on Launchpad, not GitHub, and its feature talk happens on the MobileRead forums. I used MobileRead threads found by web search instead of mining Launchpad.
- **Zotero reader** feedback came from forums.zotero.org threads as well as GitHub.
- **Commercial apps** (Kindle, Apple Books, Readwise Reader, KOReader features) were surveyed by web search. The sources are listed in that section.

Bias to keep in mind: GitHub voters are mostly technical desktop and e-ink users. Many top requests are about packaging (Flatpak, F-Droid, Windows builds) or devices, and those are left out below unless they bear on Proseway.

---

## Top recurring requests and complaints

### 1. Reflowable reading of PDFs is the most-voted gap in open readers
PDFs are painful to read on phones, and reflow is exactly what people want.
- [foliate#139](https://github.com/johnfactotum/foliate/issues/139) "Add pdf and djvu support": **131+**, 48c. This is the most-voted issue in Foliate.
- [readest#556](https://github.com/readest/readest/issues/556) "PDF reflow on mobile devices": 6+, 12c. The reporter says converting PDFs to EPUB first "is a hassle".
- [Zotero forums: Android feature request, reflowing text](https://forums.zotero.org/discussion/125394/android-feature-request-reflowing-text).
- [koreader#5492](https://github.com/koreader/koreader/issues/5492) reflow of PDFs with side images is broken, and [koreader#10345](https://github.com/koreader/koreader/issues/10345) asks for wider reflowed text.

### 2. Users fear losing annotations and keep asking for more control over them
- [koreader#3911](https://github.com/koreader/koreader/issues/3911) "Highlights get lost all the time: please make exporting and document saving 'live'". Crashes lose unsaved highlights.
- [readest#3431](https://github.com/readest/readest/issues/3431) progress is lost when a book is re-imported after a metadata edit, because it is keyed to the file hash.
- [readest#5080](https://github.com/readest/readest/issues/5080) "Global Annotation Library": 9+. The reporter says deleting a book also deletes its notes, which they regard as "part of my personal knowledge rather than the book itself".
- [readest#5398](https://github.com/readest/readest/issues/5398) asks for notes and highlights in one central place (4+). [readest#715](https://github.com/readest/readest/issues/715) asks to import annotations (3+, 9c).

### 3. Highlight export, especially to Markdown with a format the user controls
- [readest#1734](https://github.com/readest/readest/issues/1734) asks for a customizable highlight export format with template placeholders (2+, 13c). [readest#991](https://github.com/readest/readest/issues/991) asks the same for notes.
- [readest#7061](https://github.com/readest/readest/issues/7061) built-in Obsidian / Markdown sync. [koreader#10333](https://github.com/koreader/koreader/issues/10333) export to Readwise (5+).
- [zotero#2280](https://github.com/zotero/zotero/issues/2280) copy/export notes from the PDF reader. [zotero#2343](https://github.com/zotero/zotero/issues/2343) Markdown escaping in exported notes is too aggressive (25c).
- [foliate#849](https://github.com/johnfactotum/foliate/issues/849) import and export highlights from calibre.
- Apple Books users have complained since iOS 16 that bulk highlight export was removed: [Apple Community thread](https://discussions.apple.com/thread/254205334), [another](https://discussions.apple.com/thread/255117680).
- calibre: MobileRead threads show years of requests for viewer highlight export. calibre now exports plain text and JSON, and the JSON carries the location data needed for links back into the book ([MobileRead](https://www.mobileread.com/forums/showthread.php?p=4012629)).

### 4. Annotation sync between devices without a vendor cloud
- [koreader#4587](https://github.com/koreader/koreader/issues/4587) sync highlights across separate devices: 14+, 18c. Progress sync works, but highlights do not follow.
- [readest#356](https://github.com/readest/readest/issues/356) back up books over WebDAV: **35+**, 59c. [readest#192](https://github.com/readest/readest/issues/192) self-host the sync API: 19+. [readest#2795](https://github.com/readest/readest/issues/2795) end-to-end encryption for synced notes: 9+.
- [readest#5033](https://github.com/readest/readest/issues/5033) complains that third-party sync was put behind a subscription (6+). Users care who holds their data.
- [foliate#584](https://github.com/johnfactotum/foliate/issues/584) progress sync with KOReader (5+). [foliate#739](https://github.com/johnfactotum/foliate/issues/739) relative paths so libraries can sync between computers (7+).

### 5. Library management: bulk import, folders and watch folders
- [foliate#1196](https://github.com/johnfactotum/foliate/issues/1196) add multiple books at once: 14+. [foliate#1320](https://github.com/johnfactotum/foliate/issues/1320) watch folders: 14+. [foliate#1623](https://github.com/johnfactotum/foliate/issues/1623) and [#730](https://github.com/johnfactotum/foliate/issues/730) also ask for bulk import.
- [readest#179](https://github.com/readest/readest/issues/179) import a directory recursively: 10+. [readest#1925](https://github.com/readest/readest/issues/1925) read from a folder without importing: 7+, 15c.
- [koreader#8472](https://github.com/koreader/koreader/issues/8472) flat library view: 76+, **196c**. [foliate#1205](https://github.com/johnfactotum/foliate/issues/1205) bulk delete (6+). [foliate#69](https://github.com/johnfactotum/foliate/issues/69) recently opened list (9+).

### 6. Dark mode and sticky default settings
- [zotero#1683](https://github.com/zotero/zotero/issues/1683) dark mode: **91+**. This is Zotero's most-voted issue. [zotero#4949](https://github.com/zotero/zotero/issues/4949) asks for light and dark themes for the reader content itself.
- [foliate#1158](https://github.com/johnfactotum/foliate/issues/1158) set the current zoom as the default for all books (8+). [zotero#2648](https://github.com/zotero/zotero/issues/2648) default reader view settings (7+). [zotero#4439](https://github.com/zotero/zotero/issues/4439) remember the last annotation color (10+).
- [readest#1642](https://github.com/readest/readest/issues/1642) sync custom themes and layout settings across devices: 11+.

### 7. Navigation: going back after a jump, and progress readouts
- [zotero#3436](https://github.com/zotero/zotero/issues/3436) mouse back/forward buttons in the PDF view: 27+. [readest#5986](https://github.com/readest/readest/issues/5986) temporary navigation history to return after in-book jumps.
- [readest#673](https://github.com/readest/readest/issues/673) customize the status bar and progress bar (4+). [readest#7262](https://github.com/readest/readest/issues/7262) choose what appears in each header/footer corner. [readest#7123](https://github.com/readest/readest/issues/7123) page numbers should match the real layout. [readest#5563](https://github.com/readest/readest/issues/5563) exclude back matter from progress.
- [readest#1745](https://github.com/readest/readest/issues/1745) continuous scrolling: 11+. [foliate#1396](https://github.com/johnfactotum/foliate/issues/1396) single-page mode (22+). [readest#555](https://github.com/readest/readest/issues/555) / [foliate#188](https://github.com/johnfactotum/foliate/issues/188) page-turn animations (6+ each).

### 8. Dictionary, vocabulary and flashcards
- [readest#789](https://github.com/readest/readest/issues/789) vocabulary builder: 15+. [readest#170](https://github.com/readest/readest/issues/170) multiple dictionary providers: 14+, 21c.
- [foliate#758](https://github.com/johnfactotum/foliate/issues/758) Anki export from a definition (5+). [foliate#791](https://github.com/johnfactotum/foliate/issues/791) custom dictionary (5+). [foliate#323](https://github.com/johnfactotum/foliate/issues/323) GoldenDict integration (5+).
- KOReader's vocabulary builder does spaced-repetition review of looked-up words, and users cite it as a reason to stay ([wiki](https://git.blob42.xyz/Archives/koreader/wiki/Vocabulary-builder)).

### 9. Text-to-speech
- [readest#258](https://github.com/readest/readest/issues/258) custom TTS engine: 13+, **70c**. [koreader#545](https://github.com/koreader/koreader/issues/545) TTS (8+, 41c). [readest#3924](https://github.com/readest/readest/issues/3924) Storyteller read-along support (8+).
- [readest#4235](https://github.com/readest/readest/issues/4235) TTS auto page turn fails and loses the reading position.

### 10. Images, figures and zoom
- [readest#662](https://github.com/readest/readest/issues/662) image gallery mode: 11+. [readest#1276](https://github.com/readest/readest/issues/1276) zoom for PDF and CBZ: 8+. [koreader#5524](https://github.com/koreader/koreader/issues/5524) free zoom (9+).
- In converted books, small figures and tables need a tap-to-enlarge view.

### 11. Conversion quality (docling, marker)
These are complaints about the kind of pipeline Proseway's importer will run.
- **Headers and footers leak into the text:** [docling#1272](https://github.com/docling-project/docling/issues/1272) (8+), [marker#433](https://github.com/datalab-to/marker/issues/433), [marker#557](https://github.com/datalab-to/marker/issues/557), [marker#193](https://github.com/datalab-to/marker/issues/193). The opposite error also happens: [docling#3693](https://github.com/docling-project/docling/issues/3693) "Obvious non-repeating header removed".
- **Reading order in multi-column layouts:** [docling#1203](https://github.com/docling-project/docling/issues/1203) (7+), [docling#1380](https://github.com/docling-project/docling/issues/1380) (7+), [marker#50](https://github.com/datalab-to/marker/issues/50) (13c).
- **Heading hierarchy and table of contents:** [docling#287](https://github.com/docling-project/docling/issues/287) identify the table of contents (29+, 45c). [docling#652](https://github.com/docling-project/docling/issues/652) all Markdown header levels are the same (14+). [docling#1023](https://github.com/docling-project/docling/issues/1023) only H2 is produced (28c). [docling#529](https://github.com/docling-project/docling/issues/529) heading extraction (17+). [docling#5002](https://github.com/docling-project/docling/issues/5002) proposes using the PDF outline to demote headings it does not list.
- **Footnotes and superscripts:** [docling#433](https://github.com/docling-project/docling/issues/433), [docling#3128](https://github.com/docling-project/docling/issues/3128) (14c), [marker#274](https://github.com/datalab-to/marker/issues/274) broken superscripts for footnote and reference markers.
- **Hyphenation at line ends:** [docling#5492](https://github.com/docling-project/docling/issues/5492), [docling#3881](https://github.com/docling-project/docling/issues/3881), [docling#5156](https://github.com/docling-project/docling/issues/5156) (a hyphen comes out as U+0002), [docling#1127](https://github.com/docling-project/docling/issues/1127), [marker#1024](https://github.com/datalab-to/marker/issues/1024).
- **Tables:** [docling#2976](https://github.com/docling-project/docling/issues/2976) a table that continues across pages is split in two. [marker#956](https://github.com/datalab-to/marker/issues/956) colspan errors. [marker#827](https://github.com/datalab-to/marker/issues/827) (16c).
- **Math:** [docling#1640](https://github.com/docling-project/docling/issues/1640) incorrect formulas. [docling#871](https://github.com/docling-project/docling/issues/871) GPU RAM needed for formula detection.
- **Silent drops and invented text:** [marker#1081](https://github.com/datalab-to/marker/issues/1081) OCR invents text on a bleed-through page and silently drops a title and a paragraph. [marker#988](https://github.com/datalab-to/marker/issues/988) lines dropped. [marker#166](https://github.com/datalab-to/marker/issues/166) a chapter is skipped. [marker#860](https://github.com/datalab-to/marker/issues/860) hyperlinks are lost.
- **Large files, speed and memory:** [docling#1283](https://github.com/docling-project/docling/issues/1283) gets stuck on very large PDFs (19+). [docling#1304](https://github.com/docling-project/docling/issues/1304) unusable on long PDFs. [docling#3671](https://github.com/docling-project/docling/issues/3671) silent failures with `bad_alloc`. [marker#583](https://github.com/datalab-to/marker/issues/583) memory leak (11+). [marker#487](https://github.com/datalab-to/marker/issues/487) gets stuck (12c). [marker#919](https://github.com/datalab-to/marker/issues/919) extremely slow on an RTX 3090 (21+). [marker#960](https://github.com/datalab-to/marker/issues/960) 20x slower on Mac (20+).
- **Install weight and fragility:** [docling#2535](https://github.com/docling-project/docling/issues/2535) docling-slim package (**43+**, docling's most-voted issue). [marker#942](https://github.com/datalab-to/marker/issues/942) fails to install on Python 3.14 (17+). [docling#651](https://github.com/docling-project/docling/issues/651) asks whether models must be downloaded from Hugging Face.
- **Ebook input:** [docling#515](https://github.com/docling-project/docling/issues/515) EPUB backend (18+). [docling#1329](https://github.com/docling-project/docling/issues/1329) EPUB and TXT (9+).

### 12. Performance with big libraries and big books
- [readest#3714](https://github.com/readest/readest/issues/3714): after 2,815 books, imports took about 10 s each and page turns inside a single book became laggy.
- [readest#7584](https://github.com/readest/readest/issues/7584) EPUB search still takes 30+ s on repeat searches. [readest#6291](https://github.com/readest/readest/issues/6291) local backup is extremely slow for large libraries. [koreader#13184](https://github.com/koreader/koreader/issues/13184) cancel opening a book (9+).

### 13. Selection and annotation UX on touch screens
- [readest#1553](https://github.com/readest/readest/issues/1553) odd selection behavior at paragraph starts on Android (8+). [readest#5599](https://github.com/readest/readest/issues/5599) misaligned PDF text selection. [readest#4218](https://github.com/readest/readest/issues/4218) the iOS context menu blocks the annotation tools.
- [readest#7361](https://github.com/readest/readest/issues/7361) dismissing the highlight popup by tapping outside it turns the page by accident.
- [readest#1740](https://github.com/readest/readest/issues/1740) tags/categories for notes (7+). [zotero#2391](https://github.com/zotero/zotero/issues/2391) hide some or all annotations (5+, 23c). [zotero#3351](https://github.com/zotero/zotero/issues/3351) pick a highlight color with number keys.

### 14. Statistics, OPDS and AI (smaller but persistent)
- **Statistics:** [readest#589](https://github.com/readest/readest/issues/589) KOReader statistics sync (12+). [koreader#4865](https://github.com/koreader/koreader/issues/4865) average words per minute (8+). [koreader#14466](https://github.com/koreader/koreader/issues/14466) word counts. Third-party dashboards such as [KoInsight](https://github.com/dev107/KoInsight) exist only to visualize KOReader's statistics.
- **OPDS:** [readest#2970](https://github.com/readest/readest/issues/2970) OPDS-PS (8+). [koreader#10635](https://github.com/koreader/koreader/issues/10635) download several books from OPDS (11+). [koreader#10551](https://github.com/koreader/koreader/issues/10551) covers in OPDS (7+). [foliate#994](https://github.com/johnfactotum/foliate/issues/994).
- **AI:** [readest#1741](https://github.com/readest/readest/issues/1741) a chatbot that knows the book's context (9+). [readest#2260](https://github.com/readest/readest/issues/2260) an MCP server. [marker#683](https://github.com/datalab-to/marker/issues/683) Ollama support for LLM-assisted conversion. The demand is real but small next to the basics.

---

## What people like in commercial and established readers

| App | Feature | Notes for Proseway |
|---|---|---|
| Kindle | **X-Ray** (characters, terms, places in the book) | Users like it for recalling forgotten names ([MakeUseOf](https://www.makeuseof.com/how-to-use-kindle-x-ray/), [Wikipedia](https://en.wikipedia.org/wiki/X-Ray_(Amazon))). A local version could come from an index of names and terms, or from optional Ollama. |
| Kindle | **Time left in chapter / book**, based on the reader's measured speed | Users tap to cycle location, page, time left in chapter and time left in book ([aboutamazon](https://www.aboutamazon.com/md/news/devices/the-6-best-kindle-features-of-all-time-according-to-a-kindle-superfan)). Cheap to build: local words-per-minute times remaining words. |
| Kindle | **Popular Highlights** | Opinion is split, and many readers turn it off ([Android Authority](https://www.androidauthority.com/kindle-popular-highlights-3634804), [TNW](https://thenextweb.com/news/how-to-turn-off-popular-highlights-amazon-kindle)). It needs a crowd, so it does not fit Proseway. Skip it. |
| Kindle | Instant dictionary and Wikipedia lookup, plus a vocabulary builder | The baseline expectation for word lookup ([ebookfriendly](https://ebookfriendly.com/kindle-ipad-iphone-unique-features)). |
| Apple Books | Polished themes, scroll or page view, smooth page turns | Users like the look, but say highlight export is the weak point: one-at-a-time sharing, and notes are dropped on export ([thread](https://discussions.apple.com/thread/254205334)). Proseway should do better than this cheaply. |
| Readwise Reader | **Ghostreader** (ask questions, define terms, simplify passages) | Built on a cloud LLM ([readwise.io/read](https://readwise.io/read)). Proseway's version would run locally on Ollama, be optional, and be off by default. |
| Readwise Reader | Highlights flow into Obsidian, Notion and similar tools | Sync to Obsidian is the most-used path ([awesome-readwise](https://github.com/Scarvy/awesome-readwise)). Plain Markdown export to a chosen folder covers most of this. |
| KOReader | Detailed reading statistics, a vocabulary builder with spaced repetition, deep typography and hyphenation control, many page-turn and gesture options | The statistics plugin and vocabulary builder are often cited as reasons to use KOReader ([guide](https://boredom-at-work.com/best-koreader-plugins/), [language learning](https://cameracode.coffee/koreader-language-learning)). |
| calibre viewer | Highlights stored in the database and optionally in the EPUB file, with export to plain text and JSON that carries location data | Location-linked export is worth copying ([MobileRead](https://www.mobileread.com/forums/showthread.php?p=4591615)). |

---

## Prioritized feature list

### v1: must ship

Required by the brief:
1. **Library:** grid and list views, sort by title, author, recently read and date added, and a "continue reading" row.
2. **Import with progress:** per-page progress for each book (stage, page n of N, elapsed time), a cancel button, a queue for several files, and a clear failure state that names the failing page.
3. **Reader:** paginated and scroll modes, a two-column option on wide screens, and figures and tables that can be tapped to view full-size.
4. **Themes:** light, sepia and dark, with a dark theme that also applies to the book content.
5. **Font and spacing controls:** typeface, size, line height, margins, paragraph spacing, justification and hyphenation on/off. Settings are global by default, with an optional per-book override.
6. **Table of contents:** taken from the PDF outline when one exists, otherwise from detected headings.
7. **Search** within a book (fast on a 1,000-page book) and across the library by title and author.
8. **Multi-color highlights** (at least 4 colors). The app remembers the last color used, and number keys 1–4 pick a color on desktop.
9. **Notes** attached to highlights, plus free-standing notes.
10. **Bookmarks.**
11. **Saved reading position**, saved continuously, and shared between desktop and phone because both read from the same local server.
12. **Export of highlights and notes as Markdown:** per book, including chapter, color, note, date, and a page reference to the original PDF.
13. **JSON backup and restore** of the library metadata, annotations, positions and settings, with an option to include the book files.

Added because the evidence says they are essential and cheap:
14. **Stable book identity and annotation anchoring that survives re-import and re-conversion.** Key books by a hash of the source PDF plus a user-editable identifier, not by the converted output. Anchor annotations by text quote (exact text plus prefix and suffix) and by source page, so a converter upgrade does not orphan them. Evidence: koreader#3911, readest#3431.
15. **Write annotations immediately.** Each highlight or note is committed to the store when it is created, not batched or saved on close. Evidence: koreader#3911.
16. **Annotations outlive book deletion.** Deleting a book asks whether to keep its annotations. Kept annotations stay exportable. Evidence: readest#5080.
17. **Bulk import:** multi-select, drag in a folder, and recursive folder import. Evidence: foliate#1196 (14+), readest#179 (10+).
18. **Per-book annotation list:** filter by color, search the text, and jump to the location.
19. **Back after a jump:** a "back to where I was" control after following a TOC entry, a search result, a link or a footnote. Evidence: zotero#3436 (27+), readest#5986.
20. **Footnotes as popups**, with footnote markers linked to the footnote text in the converted book. Evidence: docling#433, marker#274, readest#480.
21. **Progress readout:** percent read, pages left in the chapter and time left in the chapter or book based on local reading speed, with a choice of what to show. Evidence: readest#673, #7262, and the Kindle feature.
22. **Conversion basics done well**, because these are the top converter complaints: remove repeated headers and footers, fix multi-column reading order, rejoin words hyphenated at line ends, build heading levels from the PDF outline, and merge tables split across pages. Each page gets a confidence flag, and low-confidence pages are listed after import so they are not silently wrong.
23. **Touch selection that works:** drag handles, no accidental page turn when dismissing the highlight popup, and a custom selection menu that does not fight the OS menu. Evidence: readest#7361, #1553, #4218.

### v2
- Dictionary lookup with offline dictionaries ([001](../issues/001-dictionary-lookup.md))
- Text-to-speech with local voices ([003](../issues/003-text-to-speech.md))
- Side-by-side view of the original PDF page ([004](../issues/004-side-by-side-original-page.md))
- Cross-device annotation sync over LAN, including offline reading on the phone ([006](../issues/006-lan-annotation-sync.md))
- EPUB import ([007](../issues/007-epub-import.md))
- Reading statistics ([009](../issues/009-reading-statistics.md))
- A library of annotations across all books ([010](../issues/010-global-annotation-library.md))
- Tools for fixing conversion errors: mark a header, fix reading order, re-convert one page ([011](../issues/011-conversion-correction-tools.md))
- Custom export templates and an Obsidian folder target ([012](../issues/012-export-templates-obsidian.md))
- Watch folder for automatic import ([013](../issues/013-watch-folder.md))

### Later
- Flashcards from highlights with spaced repetition ([002](../issues/002-flashcards-spaced-repetition.md))
- Optional local AI through Ollama: explain, define in context, summarize a chapter, an X-Ray-style character and term list ([005](../issues/005-local-ai-ollama.md))
- OPDS catalog for browsing and serving books ([008](../issues/008-opds-catalog.md))
- OCR for scanned PDFs ([014](../issues/014-ocr-scanned-pdfs.md))
- Custom fonts (readest#979), page-turn animations, handwriting annotations (koreader#2633 at 96+ is driven by e-ink and stylus users, and is low value for Proseway)

---

## Pitfalls to avoid

1. **Tying annotations or progress to the converted output or the file hash.** Re-importing or upgrading the converter must not orphan highlights (readest#3431). Anchor by text quote and source page, and run a re-anchoring pass after re-conversion. Report any annotations that could not be placed. Never drop them silently.
2. **Saving annotations late.** Batched or on-close saves lose work when the app crashes (koreader#3911). Commit each change to SQLite with WAL right away.
3. **Deleting notes along with the book** (readest#5080). Ask first, and keep orphaned annotations exportable.
4. **Silent conversion failures.** Converters drop paragraphs, skip chapters or invent OCR text (marker#1081, #988, #166). Compare extracted character counts per page against the PDF text layer, flag the differences, and let the reader open the original page.
5. **Unbounded memory and time on big PDFs** (docling#1283, #1304, #3671; marker#583, #487). Convert page by page in a separate worker process, write results to disk as it goes, cap memory, support resume after a crash, and keep cancel working.
6. **Heavy, fragile installs** (docling#2535 at 43+ is the top docling request; marker#942). Ship a pipeline that does not require a GPU or big ML models for born-digital PDFs. Make heavy models an optional download, and never fetch them silently.
7. **Performance regressions nobody notices** (marker#960, #919). Keep a benchmark of a few large public-domain PDFs in CI that tracks pages per second and peak memory.
8. **A library size that slows the reader** (readest#3714). Open a book with one indexed query. Never load the whole library to render a page. Lazy-load covers.
9. **Slow in-book search** (readest#7584). Build a full-text index (SQLite FTS5) at import time, not at search time.
10. **Header and footer heuristics that cut real content** (docling#3693). Remove only text that repeats across many pages and sits at the same position, and let the user restore it.
11. **Flat heading levels and a broken TOC** (docling#652, #1023). Prefer the PDF outline when present, and fall back to font-size clustering.
12. **Export that loses context or over-escapes Markdown** (zotero#2343; Apple Books drops notes on export). Include the note, chapter, page and color, and escape only what Markdown needs.
13. **Putting sync or backup behind a server or a paywall** (readest#5033, #192). Keep backup and LAN sync local-first, file-based and documented.
14. **Touch UX that fights the platform** (readest#7361, #4218). Test selection and highlighting on real Android and iOS browsers, since the phone uses the browser over Wi-Fi.
15. **AI features that send text off the machine.** Any AI is optional, off by default, Ollama on localhost only, and the UI shows when it is in use.

---

## Issue drafts

The drafts for v2 and later items are in `docs/issues/`, files `001` to `014`.
