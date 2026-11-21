# Reader: bounded chapter window

Branch `claude/reader-chapter-window-39d481`. Fixes the PROGRESS.md finding "The reader never
unloads chapters". Round 2 addresses the coordinator's review (see the end of this note).

## What changed

### The window rule (`web/src/lib/chapterWindow.ts`, pure, unit-tested)

`growWindow(win, next, isFar)` is called when a sentinel asks for the next chapter at one edge.

- **The request is never refused.** The reader is within the sentinel's 1600px margin of that
  edge, so the chapter is needed.
- **Chapters are dropped only from the *opposite* end,** while more than 3 are mounted *and* that
  end chapter lies entirely more than `KEEP_PX` (2400px) off screen.
  - `KEEP_PX` is larger than the sentinel margin on purpose: after a trim, the sentinel on the
    trimmed side is out of range, so it can't ask for the chapter straight back.
- **Full-length chapters:** exactly 3 are mounted (the one you're in and its neighbours).
- **Tiny chapters** (cover, title page, copyright…): the count goes above 3 until there's enough
  text to fill the screen and the margins. Loading never stalls behind them.
  - Round 1's count-only rule ("drop the end farthest from the current chapter, or refuse") could
    stall forever there. The reader couldn't scroll far enough to change the current chapter, so
    the next one was never allowed in.

### `Reader.tsx`

- **Window state.** `winRef` mirrors `win`, so out-of-order loads build on the latest window.
  All window changes go through `applyWin`.
- **No jumps when chapters change above the screen.** When the top edge changes (a chapter added
  *or* removed above), the existing anchor mechanism records the first visible block, and the
  layout effect puts it back.
- **Cached blocks are bounded too.** Chapter data more than 2 chapters from the window is dropped.
  - The `loading` cache is trimmed outside the `setChapters` updater.
  - A fetch that finishes after its chapter was dropped no longer re-adds it.
  - A window chapter with no data is fetched again by an effect.
- **Jumps hold their target in place (`holdInPlace`).** This fixes a bug that is **also on
  `main`**: on a phone, restoring a saved position deep in a chapter landed about four paragraphs
  late.
  - Cause: blocks use `content-visibility: auto` with a 4.5em size estimate. As the blocks around
    the target render at full height, Chrome's native scroll anchoring scrolls the page by itself
    (observed: 608 → 2371px with no script calls). It appears to anchor to something below the
    target, probably a page marker.
  - The hold re-measures every frame and corrects until the target has been still for 5 frames
    (at most 1s).
  - It lets go at once on wheel, touch, pointer or key input. It also lets go when the page
    scrolls while the target's position *in the document* stays the same: that means someone else
    scrolled (scrollbar, assistive tech, a script), not layout.
  - Applies to every jump: restore, Contents, search, notes, footnotes, Back-to.
  - Near the start or end of the book, being at the scroll limit counts as in place, so the hold
    doesn't run its full second there.
- **Overlapping jumps.** Each jump takes a sequence number; when two overlap, only the latest one
  moves the page.
- **Loading states.**
  - `<main id="reading">` carries `aria-busy` only while a jump is loading or being positioned.
    Chapter loads in the background while you read don't set it, so screen readers don't hold back
    the text. Those loads are exposed as `data-loading` (a test hook).
  - A polite `role="status"` live region says "Loading page N…", then "Moved to page N." for
    jumps, and "Looking up the note…" for far footnotes. It's cleared before each message, so a
    repeated message is read again.
- **Footnotes and endnotes.** A note whose chapter isn't cached is fetched with the new
  `GET /api/books/{id}/blocks/{block_id}`, which returns the block and its chapter.
  - One request per note. Hits and misses are both remembered, and concurrent clicks share one
    request.
  - A dangling reference costs a single 404, once.
  - If the reference unmounted while the note was loading, no popup opens.
  - Round 1 showed nothing for these notes; round 2 scanned chapters one by one.
- **Server.** The new endpoint sits right after `chapter()` in `src/proseway/server.py`, which the
  HTTPS branch doesn't change. It uses the existing `blocks_by_id` index.
- **Focus.**
  - If focus is inside a chapter that's about to unmount, it moves to `#reading`.
  - When the footnote popup closes and its reference has unmounted, focus goes to `#reading`
    instead of `<body>`.
- **Test hook.** `data-window="lo-hi"` on `<main>` exposes the current window, so tests can wait
  on state.

### Contents panel (separate commit `c391e82`)

Fixes a bug that is **also on `main`**: closing Contents blanked the reader in Chromium 159.
`scrollIntoView()` now returns a Promise, which `TocPanel`'s expression-bodied effect handed to
React as its cleanup.

## Tests

- **`web/src/lib/chapterWindow.test.ts` (vitest, 14 tests).**
  - Unit cases for the rule, including dropping several far chapters in one request.
  - A layout simulator: chapter heights, a viewport, both sentinels with their 1600px margin,
    and the anchor. It reads books to the end and back and asserts the window never stalls and
    always settles. Like the real code, it measures every chapter from the window as it was
    before the request, so it can trim more than one chapter at once.
  - Simulated books: 40 long chapters (≤ 3 mounted), tiny front matter, 200 tiny chapters (at
    most `(viewport + 2 × KEEP_PX) / height + 3` mounted, i.e. 50; a rule that never trims would
    mount 200), a mix starting mid-book, and phone sizes.
- **`tests/test_block_lookup.py`:** the endpoint returns the block and its chapter, and a 404 for
  an unknown block or book.
- **`tests/pdfgen.py`** gains `make_long_book()` and `make_short_start_book()` (4 one-line
  "Prelude" chapters, then 4 full chapters), both appended at the end of the file.
  - `tests/test_long_fixture.py` checks that both convert into the expected chapters.
  - `tests/make_e2e_fixture.py OUT long|short` writes them for the browser tests.
- **`web/e2e/chapters.spec.ts` (ports 18769/18770; 6 tests).**
  - Books are imported through the API in `beforeAll`. Each test sets its own reading position,
    so no test depends on another's.
  - Fixed sleeps are gone: `settle()` waits until `aria-busy` is false, `data-loading` is 0, and
    the mounted window is unchanged over three samples, each two animation frames apart.
  - The tests:
    1. **Reading straight through** six chapters and back: never more than 3 `section.chapter`
       elements (a MutationObserver records every state), and the first visible block moves
       ≤ 3px at every step.
    2. **Tiny front matter:** the first real chapter loads with no scrolling at all; reading to
       the end and back works; 3 chapters are mounted at the end.
    3. **Restoring a position mid-book** (chapter four, paragraph 5): it lands 40–140px from the
       top, the chapter before loads above without moving it, and scrolling up into it stays
       still.
    4. **Contents, Back-to and search jumps** into unloaded chapters.
    5. **Notes-panel jump** into an unloaded chapter. A highlight in chapter one is drawn again
       after its chapter remounts.
    6. **Footnotes:** a note in unloaded chapter six costs exactly one `blocks` request and no
       chapter downloads. A dangling reference costs one 404, and repeat clicks on either make
       no further requests.
- **Checking that the tests can fail.** Each was run once against a broken build:
  - With the anchor compensation disabled, test 1 fails while scrolling up.
  - With the round-1 refusal reintroduced, test 2 fails ("Chapter One" never loads).
  - Without the hold, test 3 fails on the phone (and on `main`).

## Verified (Working)

- `pnpm --dir web build`, `pnpm --dir web test` (22 passed), `uv run pytest` (all passed),
  `uv run ruff check .`.
- **Round 3, final code:**
  - `chapters.spec.ts`: 6/6 on desktop, 6/6 on phone.
  - `reading.spec.ts` and `a11y.spec.ts`, run from temporary port-shifted copies to avoid
    another session's servers on 18765–18768 (copies not committed): desktop 3/3 and 4/4; phone
    6 passed + 1 skipped (desktop-only keyboard test).
  - The reading spec needed one retry after a `spawn EPERM` crash.
- **Round 2:** `chapters.spec.ts` 15/15 on desktop with `--repeat-each=3`.
- **Stale bundles.** A `vite build` that had crashed and been retried once reported success but
  left the previous bundle in place. If e2e results look stale, check the timestamp of
  `src/proseway/static/assets/*.js`.

## Untested / left

- **Chromium only.** No real phone, Safari or Firefox. iOS momentum scrolling combined with the
  `scrollBy` compensation and the hold is unverified.
- **Memory not measured.** The window is bounded by construction and by the e2e count, but heap
  and DOM size before and after weren't benchmarked on a real 1,000-page book.
- **Hold edge case.** If someone else scrolls in the same frame that layout moves the target,
  that frame is treated as layout and corrected. The hold only runs for at most 1s after a jump.

## Round 2: coordinator review (2026-11-21)

1. **Blocker: stall with short leading chapters.** Fixed with the new rule above. Covered by the
   simulator tests and e2e test 2.
2. **Footnotes in far chapters.** Fixed with the on-demand lookup.
3. **Accessible loading states.** `aria-busy` on `<main>` plus the polite live region.
4. **Tests.** Added restore-mid-book, Notes jump, highlight after remount and short chapters.
   Specs are independent, and fixed waits are replaced by `settle()`. Writing the restore test
   turned up the phone restore bug on `main`, fixed by the hold.
5. **Nits.**
   - Fixed: the `loading` trim outside the updater; late fetches not re-adding evicted chapters;
     footnote focus falling to `<body>`; the `server.ts` comment.

**Full-suite run notes.** `reading.spec.ts` and `a11y.spec.ts` hard-code ports 18765–18768.
While another session ran its own e2e suite, its server answered on 18765, and one of my runs
talked to that server: a library that already had a book in it. So full-suite failures on this
machine can come from port collisions as well as the known 0xC0000005 crashes.

## Round 3: coordinator review (2026-11-21)

- **N1 (footnote lookup).** New `GET /api/books/{id}/blocks/{block_id}` endpoint. On the client:
  one request per note, misses remembered, concurrent clicks share one request. Tested by pytest
  and e2e test 6.
- **N2 (`aria-busy`).** Now set only for jumps (loading and positioning). Background loads are
  exposed as `data-loading`.
- **N6 (simulator).** `isFar` measures from the window as it was before the request, so the
  simulator trims several chapters at once. The tiny-chapter bound is now tight (≤ 50 of 200)
  and can fail. Added a unit test for a multi-chapter trim.
- **Old nit 7 (overlapping jumps).** Jumps carry a sequence number; stale results are ignored.
- **Optional nits.**
  - The hold accepts the scroll limit as in place.
  - The live region re-announces identical text.
  - No footnote popup opens if the reference unmounted during the lookup.
- **`web/e2e/server.ts`** isn't touched this round.
