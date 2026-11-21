# Reading UX study (inspiration only)

Date: 2026-11-21.

Sources:
- Readwise Reader documentation (public);
- Readest's web app, its library view only (it opened in the user's own browser profile, so I didn't open books there to avoid touching their account);
- the feature research in `../features.md`;
- my own knowledge of Kindle, Apple Books, KOReader and Foliate.

No screenshots of other products are stored in the repo. We take ideas only. No branding, icons or distinctive layouts are copied.

## What the best readers get right, and what Proseway does about it

| Observation | Where seen | What Proseway does |
|---|---|---|
| Highlighting should take one step. Reader turns any selection straight into a highlight ("auto-highlighting"). | Readwise Reader | A selection shows a small colour bar right at the selection. One click or tap picks the colour, and keys 1–5 work too. We kept an explicit step so people can still copy text. |
| A keyboard-first reading flow: focus a paragraph, press H to highlight, N to add a note. | Readwise Reader | `H` highlights the paragraph at the top of the screen when nothing is selected. `N`, `T`, `/`, `A` and `B` open notes, contents, search, appearance and bookmarks. |
| Annotations sit in the margin on wide screens. | Readwise Reader, Zotero | The notes panel docks beside the text on screens wider than 1100 px and the text column shifts left, so both stay visible. |
| Highlight boundaries snap to whole words. | Kindle, Apple Books | The selection is snapped to word boundaries before saving. |
| Time left in the chapter is a calm progress signal. | Kindle | The status bar shows the page in the original PDF, the minutes left in the chapter, and the percentage. |
| A way back after following a link or search hit. | Zotero (most-upvoted request), Apple Books | A floating "Back to p. 47" chip appears after any jump. |
| Typography controls: a few good choices rather than endless sliders. | Apple Books, KOReader | Five typefaces, a size stepper, three line spacings, three line lengths, and optional justification with hyphenation. |
| Themes that respect the time of day: paper, sepia, dark, true black. | Apple Books, Kindle | Paper, Sepia, Dusk and Night, plus "match system". |
| The chrome gets out of the way while reading. | All of them | The top bar hides on scroll down and comes back on scroll up or a tap. |
| Library covers as real objects, with reading progress shown at a glance. | Apple Books, Readest | Covers stand on a shared baseline. Reading progress hangs as a crimson ribbon from the cover. |

## Not done tonight
- Dragging highlight handles to adjust a highlight's boundaries (Readwise). Drafted as a v2 item.
- Paginated (page-turn) mode. Proseway scrolls for now. See `ROADMAP.md`.
