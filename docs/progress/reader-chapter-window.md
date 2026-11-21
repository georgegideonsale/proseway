# Reader: bounded chapter window

Branch `claude/reader-chapter-window-39d481`. Fixes the PROGRESS.md finding "The reader never
unloads chapters".

## What changed

- **At most 3 chapters are mounted.** `web/src/lib/chapterWindow.ts` holds the rule as a pure
  function. `growWindow(win, next, current)` adds the requested neighbour, then drops whichever
  end is farthest from `current`, the chapter at the top of the screen. If the new chapter
  would itself be the one dropped, the window stays as it was.
  - For any current chapter `c`, the only stable 3-chapter window is `[c-1, c+1]`. So the two
    sentinels firing over and over converge instead of loading and unloading in a loop.
  - Reading down, the next chapter loads when you enter the current last one. With
    `rootMargin: 1600px`, that's well before you reach its end.
- **`Reader.tsx`:**
  - `winRef` mirrors `win`, so loads that finish out of order build on the latest window.
  - Every window change goes through `applyWin`.
  - When the top of the window changes (a chapter added *or removed* above the screen), the
    existing anchor mechanism records the first visible block, and the layout effect puts it
    back where it was.
  - The IntersectionObserver is rebuilt when the current chapter changes. An observer reports
    only on transitions, so without this a refused request would never be retried while a
    sentinel stayed inside the margin.
- **Cached blocks are trimmed too.** Chapter data more than 2 chapters from the window is
  dropped from `chapters` (and from the `loading` promise cache).
  - A window chapter with no data is re-fetched by an effect. That also covers a jump racing a
    trim.
  - Progress and minutes-left are unchanged: they use manifest char counts plus the current
    chapter, which is always mounted.
- **Focus:** if keyboard focus is inside a chapter that's about to unmount, it moves to
  `#reading` (the `<main>`, `tabIndex=-1`) without scrolling.
- **Jumps** (Contents, search, notes, footnote "Go to note", "Back to p. N") and position
  restore work as before: a jump outside the window resets it to the target chapter, and it
  grows from there.
- **Pre-existing bug fixed (separate commit `c391e82`):** closing the Contents panel blanked the
  whole reader in current Chromium (159).
  - Cause: `TocPanel` used `useEffect(() => ref.current?.scrollIntoView(...))`, and
    `scrollIntoView()` now returns a Promise. React keeps the Promise as the effect's cleanup
    and calls it on unmount: "l is not a function".
  - On phones every Contents jump closes the panel, so every jump hit it.
  - One-line fix in `web/src/components/reader/Panels.tsx`, the only file outside `Reader.tsx`
    I touched. The task's TOC-jump requirement couldn't be met without it.
  - Worth checking elsewhere: any other expression-bodied effect that calls an API which may
    start returning a value.

## Tests

- `web/src/lib/chapterWindow.test.ts` (vitest, 12 tests) covers:
  - growth and trimming in both directions;
  - refusals and stale requests;
  - convergence when both edges fire repeatedly;
  - re-centring after a jump;
  - a 50-chapter read-through that never exceeds 3.
- `tests/pdfgen.py: make_long_book()` (appended at the end of the file) writes N chapters, each
  on a new page with a "Chapter N" heading. Every paragraph names its chapter and number.
  - `tests/make_e2e_fixture.py OUT long` uses it with 6 chapters × 2 pages.
  - `tests/test_long_fixture.py` checks that it converts into exactly 6 chapters with the
    expected headings.
- `web/e2e/chapters.spec.ts` (ports 18769/18770) has two tests:
  - **Reading through.** Imports the 6-chapter book and scrolls in 1,200 px steps to the end,
    then back to the start.
    - A MutationObserver records the most `section.chapter` elements ever mounted. It must
      stay ≤ 3, every chapter must have been seen, and `[3,4,5]` must be mounted at the end.
    - After each step, the first visible block must stay within 3 px while chapters load and
      unload.
    - At the top, "Chapter One" and its first paragraph are on screen, with `[0,1,2]` mounted.
  - **Jumps.** Contents → Chapter Six (not mounted), then "Back to p. N" (chapter one, by then
    unloaded), then a search hit in chapter five. All land on the text, still ≤ 3 mounted.

## Verified (Working)

- `pnpm --dir web build`, `pnpm --dir web test` (20 passed), `uv run pytest` (all passed),
  `uv run ruff check .`.
- Playwright `--project=desktop`: 9/9 passed in one run.
- Playwright `--project=phone`: 8 passed, 1 skipped (keyboard test, desktop-only by design).
- **Earlier failures were crashes, not assertions.** Some runs failed on this machine with
  0xC0000005 crashes: fixture spawn, Python server start, `Target crashed`, worker exit. Each
  passed on retry. None failed on an assertion.
- **The no-jump assertion is meaningful.** With the app's anchor compensation disabled, the
  read-through test fails while scrolling back up (the visible block's chapter gets unloaded).
  Scrolling down still passed without it, because Chromium's native scroll anchoring (CSS
  `overflow-anchor`) covers removals above the view. The manual anchor is what makes prepending
  safe, and it covers browsers without native anchoring.

## Untested / left

- **Not tested on a real phone, Safari or Firefox.** All runs were Chromium (desktop and
  Pixel 7 emulation). In particular, iOS momentum scrolling combined with `scrollBy`
  compensation is unverified.
- **Memory not measured.** There's no number for heap or DOM size before and after on a real
  1,000-page book. The window is bounded by construction and by the e2e count, but the saving
  itself wasn't benchmarked.
- **Footnote popups only find notes in cached chapters.** A footnote reference whose note sits
  in a chapter outside the cache (window ± 2) shows nothing on click. Before, it worked only if
  you had already scrolled through that chapter. Notes in the same or a neighbouring chapter (the
  common case) still work.
- **Very short chapters.** If a whole 3-chapter window fits on screen with you at the top of
  the first one, the chapter after it waits until you scroll into the middle one. You see the
  loading spinner briefly. It never jumps, and it's not stuck: it loads as soon as the current
  chapter changes.
- **Mid-chapter jumps.** A jump to a chapter already in the window keeps the window as it is,
  as before. Jumps elsewhere reset it to just the target, which then grows by one on each side.
