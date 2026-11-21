import { describe, expect, it } from "vitest";
import { chaptersToEvict, growWindow, type ChapterWindow } from "./chapterWindow";

describe("growWindow", () => {
  it("grows freely while under the limit", () => {
    expect(growWindow([4, 4], 5, 4)).toEqual([4, 5]);
    expect(growWindow([4, 5], 3, 4)).toEqual([3, 5]);
  });

  it("drops the chapter above when reading down past the limit", () => {
    // Moved on into chapter 6 with 4..6 mounted: 7 comes in, 4 goes.
    expect(growWindow([4, 6], 7, 6)).toEqual([5, 7]);
    // Still in chapter 5, the window is already centred: 7 waits.
    expect(growWindow([4, 6], 7, 5)).toEqual([4, 6]);
  });

  it("drops the chapter below when scrolling back up past the limit", () => {
    expect(growWindow([4, 6], 3, 4)).toEqual([3, 5]);
  });

  it("refuses a chapter that would itself be the farthest", () => {
    const w: ChapterWindow = [4, 6];
    expect(growWindow(w, 7, 4)).toBe(w); // still reading the top chapter
    expect(growWindow(w, 3, 6)).toBe(w);
  });

  it("settles on the chapters around the current one, from either edge", () => {
    // Simulate both sentinels firing over and over while the reader stays in chapter 5.
    let w: ChapterWindow = [5, 5];
    for (let i = 0; i < 10; i++) {
      w = growWindow(w, w[1] + 1, 5);
      w = growWindow(w, w[0] - 1, 5);
    }
    expect(w).toEqual([4, 6]);
  });

  it("recentres a lopsided window after a jump", () => {
    // Jumped into chapter 5 while 5..7 happened to be mounted.
    expect(growWindow([5, 7], 4, 5)).toEqual([4, 6]);
  });

  it("ignores stale, non-adjacent requests", () => {
    const w: ChapterWindow = [10, 10];
    expect(growWindow(w, 3, 10)).toBe(w);
    expect(growWindow(w, 10, 10)).toBe(w);
  });

  it("clamps a current chapter outside the window", () => {
    expect(growWindow([4, 6], 7, 99)).toEqual([5, 7]);
    expect(growWindow([4, 6], 3, -1)).toEqual([3, 5]);
  });

  it("respects a custom limit", () => {
    expect(growWindow([0, 0], 1, 0, 1)).toEqual([0, 0]);
    expect(growWindow([0, 0], 1, 1, 1)).toEqual([1, 1]);
    expect(growWindow([0, 3], 4, 2, 5)).toEqual([0, 4]);
  });

  it("never exceeds the limit over a straight read-through", () => {
    let w: ChapterWindow = [0, 0];
    for (let cur = 0; cur < 50; cur++) {
      for (let k = 0; k < 3; k++) {
        w = growWindow(w, w[1] + 1, cur);
        w = growWindow(w, w[0] - 1, cur);
        expect(w[1] - w[0] + 1).toBeLessThanOrEqual(3);
        expect(cur).toBeGreaterThanOrEqual(w[0]);
        expect(cur).toBeLessThanOrEqual(w[1]);
      }
    }
    expect(w).toEqual([48, 50]);
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
