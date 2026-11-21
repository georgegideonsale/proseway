import { describe, expect, it } from "vitest";
import { chaptersToEvict, growWindow, KEEP_PX, type ChapterWindow } from "./chapterWindow";

const far = () => true;
const near = () => false;

describe("growWindow", () => {
  it("grows freely while under the limit", () => {
    expect(growWindow([4, 4], 5, far)).toEqual([4, 5]);
    expect(growWindow([4, 5], 3, far)).toEqual([3, 5]);
  });

  it("drops far chapters from the opposite end past the limit", () => {
    expect(growWindow([4, 6], 7, far)).toEqual([5, 7]);
    expect(growWindow([4, 6], 3, far)).toEqual([3, 5]);
  });

  it("never refuses the requested chapter, even when nothing can be dropped", () => {
    expect(growWindow([0, 2], 3, near)).toEqual([0, 3]);
    expect(growWindow([3, 5], 2, near)).toEqual([2, 5]);
  });

  it("only drops chapters that are far, stopping at the first near one", () => {
    // 0 and 1 are far above the screen, 2 is not.
    expect(growWindow([0, 4], 5, (c) => c < 2)).toEqual([2, 5]);
  });

  it("ignores stale, non-adjacent requests", () => {
    const w: ChapterWindow = [10, 10];
    expect(growWindow(w, 3, far)).toBe(w);
    expect(growWindow(w, 10, far)).toBe(w);
  });

  it("respects a custom limit", () => {
    expect(growWindow([0, 0], 1, far, 1)).toEqual([1, 1]);
    expect(growWindow([0, 3], 4, far, 5)).toEqual([0, 4]);
  });
});

describe("chaptersToEvict", () => {
  it("keeps the window plus a margin", () => {
    expect(chaptersToEvict([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [4, 6]).sort((a, b) => a - b)).toEqual([0, 1, 9]);
  });

  it("evicts nothing when everything is near", () => {
    expect(chaptersToEvict(new Set([3, 4, 5]), [4, 4])).toEqual([]);
  });
});

/**
 * A model of the reader: chapters of given heights stacked in a column, a viewport, sentinels
 * that ask for the next chapter when an edge comes within MARGIN px, and the scroll anchor that
 * keeps the text still when chapters come and go above the screen.
 */
function simulate(heights: number[], opts: { viewport?: number; step?: number; start?: number } = {}) {
  const V = opts.viewport ?? 800;
  const STEP = opts.step ?? 600;
  const MARGIN = 1600;
  const last = heights.length - 1;
  const start = opts.start ?? 0;
  let win: ChapterWindow = [start, start];
  let y = 0; // top of the viewport, measured from the top of the window's first chapter
  let maxCount = 1;
  let maxSettle = 0;
  const span = (a: number, b: number) => heights.slice(a, b + 1).reduce((s, h) => s + h, 0);

  function settle() {
    for (let round = 0; ; round++) {
      if (round > 200) throw new Error(`window never settles at ${win} (y=${y})`);
      maxSettle = Math.max(maxSettle, round);
      const [lo, hi] = win;
      const total = span(lo, hi);
      // Positions relative to the viewport, measured from the window as it is before this
      // request (the layout doesn't change while growWindow decides).
      const top0 = lo;
      const isFar = (c: number) => {
        const top = span(top0, c - 1) - y;
        const bottom = top + heights[c];
        return bottom < -KEEP_PX || top > V + KEEP_PX;
      };
      let next: ChapterWindow | null = null;
      if (hi < last && total - (y + V) <= MARGIN) next = growWindow(win, hi + 1, isFar);
      else if (lo > 0 && y <= MARGIN) next = growWindow(win, lo - 1, isFar);
      if (!next || (next[0] === lo && next[1] === hi)) return;
      // Anchor: whatever was added or removed above keeps the text on screen where it was.
      if (next[0] < lo) y += span(next[0], lo - 1);
      if (next[0] > lo) y -= span(lo, next[0] - 1);
      win = next;
      maxCount = Math.max(maxCount, win[1] - win[0] + 1);
    }
  }

  settle();
  let steps = 0;
  // Read down to the end…
  while (!(win[1] === last && y + V >= span(win[0], win[1]))) {
    if (++steps > 100_000) throw new Error(`stalled at ${win} (y=${y})`);
    y = Math.min(y + STEP, Math.max(0, span(win[0], win[1]) - V));
    settle();
  }
  const atEnd = win;
  // …and back up to the start.
  while (!(win[0] === 0 && y <= 0)) {
    if (++steps > 200_000) throw new Error(`stalled going up at ${win} (y=${y})`);
    y = Math.max(0, y - STEP);
    settle();
  }
  return { maxCount, atEnd, atStart: win, maxSettle };
}

describe("reading through a book (simulated layout)", () => {
  it("keeps at most three long chapters mounted", () => {
    const r = simulate(Array(40).fill(9000));
    expect(r.maxCount).toBeLessThanOrEqual(3);
    expect(r.atEnd[1]).toBe(39);
    expect(r.atStart[0]).toBe(0);
  });

  it("doesn't stall behind short leading chapters (cover, title, copyright…)", () => {
    const r = simulate([60, 40, 80, 50, 9000, 9000, 9000, 9000]);
    expect(r.atEnd[1]).toBe(7);
    expect(r.atStart[0]).toBe(0);
  });

  it("handles a book made entirely of tiny chapters, bounded by distance", () => {
    const H = 120;
    const V = 800;
    const r = simulate(Array(200).fill(H), { viewport: V });
    expect(r.atEnd[1]).toBe(199);
    expect(r.atStart[0]).toBe(0);
    // Mounted text reaches at most KEEP_PX past each side of the screen, plus a partial chapter
    // at each end and the one just requested: far fewer than the 200 in the book.
    const bound = Math.ceil((V + 2 * KEEP_PX) / H) + 3;
    expect(r.maxCount).toBeLessThanOrEqual(bound);
    expect(r.maxCount).toBeGreaterThan(3); // tiny chapters do lift the count limit
  });

  it("drops several far chapters at once when a jump leaves many behind", () => {
    // 0..5 tiny but 6 huge: reading deep into 6, a request for 7 drops 0..4 in one go.
    const tinyThenHuge = (c: number) => c <= 4;
    expect(growWindow([0, 6], 7, tinyThenHuge)).toEqual([5, 7]);
  });

  it("handles a mix of short and long chapters, starting mid-book", () => {
    const heights = [300, 9000, 200, 200, 7000, 100, 12000, 400, 400, 400, 8000];
    const r = simulate(heights, { start: 6, step: 900 });
    expect(r.atEnd[1]).toBe(10);
    expect(r.atStart[0]).toBe(0);
  });

  it("works on a phone-sized screen with big steps", () => {
    const r = simulate(Array(12).fill(25000), { viewport: 839, step: 1200 });
    expect(r.maxCount).toBeLessThanOrEqual(3);
  });
});
