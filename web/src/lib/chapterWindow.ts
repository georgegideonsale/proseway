/** The reader keeps only a few chapters mounted; these pure helpers decide which. */

export type ChapterWindow = [number, number];

/** Most chapters mounted at once: the one being read plus its neighbours. */
export const MAX_MOUNTED = 3;

/** How many chapters beyond the window keep their downloaded blocks, so scrolling back is instant. */
export const CACHE_MARGIN = 2;

/**
 * The window after adding chapter `next` at one end, trimmed to `max` chapters by dropping
 * the end farthest from `current` (the chapter at the top of the screen).
 *
 * Returns the window unchanged when `next` isn't adjacent to it (a stale request after a jump),
 * or when `next` itself would be the chapter dropped. Given `current`, the window converges to
 * the chapters centred on it, so repeated requests from both edges settle instead of flapping.
 */
export function growWindow(win: ChapterWindow, next: number, current: number, max = MAX_MOUNTED): ChapterWindow {
  let [lo, hi] = win;
  if (next === hi + 1) hi = next;
  else if (next === lo - 1) lo = next;
  else return win;
  const dir = next > win[1] ? "down" : "up";
  const c = Math.min(Math.max(current, lo), hi);
  while (hi - lo + 1 > Math.max(1, max)) {
    const above = c - lo;
    const below = hi - c;
    // On a tie, drop the side we're moving away from.
    if (above > below || (above === below && dir === "down")) lo += 1;
    else hi -= 1;
  }
  if (lo === win[0] && hi === win[1]) return win;
  return [lo, hi];
}

/** Chapters whose cached blocks can be let go: farther than `margin` from the window. */
export function chaptersToEvict(cached: Iterable<number>, win: ChapterWindow, margin = CACHE_MARGIN): number[] {
  const out: number[] = [];
  for (const c of cached) if (c < win[0] - margin || c > win[1] + margin) out.push(c);
  return out;
}
