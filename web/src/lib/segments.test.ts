import { describe, expect, it } from "vitest";
import { segment, snippetParts } from "./segments";
import { rangesFromSelection, snapToWords } from "./selection";

describe("segment", () => {
  it("always reassembles the exact block text", () => {
    const text = "The historian made a claim,1 which scholars disputed.";
    const segs = segment(
      text,
      [[26, 27, "fnref", "abc"]],
      [
        { id: "a", start: 4, end: 18, color: "yellow" },
        { id: "b", start: 10, end: 40, color: "blue" },
      ],
    );
    expect(segs.map((s) => s.text).join("")).toBe(text);
    const overlap = segs.find((s) => s.start === 10)!;
    expect(overlap.marks.map((m) => m.id)).toEqual(["a", "b"]);
    expect(segs.find((s) => s.start === 26)!.styles[0][2]).toBe("fnref");
  });

  it("ignores out-of-range spans and marks", () => {
    const segs = segment("short", [[2, 99, "i"]], [{ id: "x", start: -1, end: 3, color: "pink" }]);
    expect(segs).toHaveLength(1);
    expect(segs[0].marks).toHaveLength(0);
  });
});

describe("snippetParts", () => {
  it("splits FTS markers without interpreting HTML", () => {
    const parts = snippetParts("a <b>\u0002word\u0003 here");
    expect(parts).toEqual([
      { text: "a <b>", hit: false },
      { text: "word", hit: true },
      { text: " here", hit: false },
    ]);
  });
});

describe("snapToWords", () => {
  const t = "a grove of tall walnut-trees that shades one side";
  it("extends partial words at both ends", () => {
    const s = t.indexOf("rove");
    const e = t.indexOf("shades") + 3;
    expect(t.slice(...Object.values(snapToWords(t, s, e)) as [number, number])).toBe("grove of tall walnut-trees that shades");
  });
  it("keeps exact word selections unchanged", () => {
    const s = t.indexOf("tall");
    expect(snapToWords(t, s, s + 4)).toEqual({ start: s, end: s + 4 });
  });
});

describe("rangesFromSelection", () => {
  it("maps a DOM selection across two blocks to text offsets", () => {
    document.body.innerHTML = `
      <article id="a">
        <div class="pagemark"><span>12</span></div>
        <p data-block="b1"><span class="bt"><span>Hello </span><span><mark>brave</mark></span><span> world.</span></span></p>
        <p data-block="b2"><span class="bt"><span>Second paragraph here.</span></span></p>
      </article>`;
    const art = document.getElementById("a")!;
    const mark = art.querySelector("mark")!.firstChild!;
    const second = art.querySelector('[data-block="b2"] .bt span')!.firstChild!;
    const range = document.createRange();
    range.setStart(mark, 2); // "av" in "brave"
    range.setEnd(second, 6); // "Second"
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    expect(rangesFromSelection(sel, art)).toEqual([
      { blockId: "b1", start: 6, end: 18 }, // snapped to "brave world."
      { blockId: "b2", start: 0, end: 6 },
    ]);
  });
});
