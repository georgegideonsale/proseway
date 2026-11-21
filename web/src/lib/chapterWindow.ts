/** The reader keeps only a few chapters mounted; these pure helpers decide which. */

export type ChapterWindow = [number, number];

/** Chapters mounted at once, once they're long enough that the extra ones are off screen. */
export const MAX_MOUNTED = 3;

/**
 * A chapter is only let go when it lies entirely this many px beyond the screen. It must be
 * more than the sentinels' rootMargin (1600px), so the sentinel on the trimmed side ends up out
 * of range and doesn't ask for the chapter straight back.
 */
export const KEEP_PX = 2400;

/** How many chapters beyond the window keep their downloaded blocks, so scrolling back is instant. */
export const CACHE_MARGIN = 2;

/**
 * The window after adding chapter `next` at one end.
 *
 * A request from a sentinel is never refused: the reader is within reach of that edge, so the
 * chapter is needed. To stay small, chapters are then dropped from the *opposite* end while more
 * than `max` are mounted and that end chapter is entirely far off screen (`isFar`). Short
 * chapters (a cover, a title page) therefore never stall loading; they just let the count exceed
 * `max` until there's enough text to fill the screen and the margins.
 *
 * Returns the window unchanged when `next` isn't adjacent to it (a stale request after a jump
 * or another load got there first).
 */
export function growWindow(win: ChapterWindow, next: number, isFar: (chapter: number) => boolean, max = MAX_MOUNTED): ChapterWindow {
  let [lo, hi] = win;
  if (next === hi + 1) {
    hi = next;
    while (hi - lo + 1 > max && isFar(lo)) lo += 1;
  } else if (next === lo - 1) {
    lo = next;
    while (hi - lo + 1 > max && isFar(hi)) hi -= 1;
  } else {
    return win;
  }
  return [lo, hi];
}

/** Chapters whose cached blocks can be let go: farther than `margin` from the window. */
export function chaptersToEvict(cached: Iterable<number>, win: ChapterWindow, margin = CACHE_MARGIN): number[] {
  const out: number[] = [];
  for (const c of cached) if (c < win[0] - margin || c > win[1] + margin) out.push(c);
  return out;
}
