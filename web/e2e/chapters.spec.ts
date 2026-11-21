import { readFileSync } from "node:fs";
import { basename } from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { makeFixture, Server } from "./server";

// The reader keeps only a few chapters mounted. Reading straight through must never hold more
// than 3 full-length chapters, unloading above the screen must not move the text, front matter
// made of tiny chapters must not stall loading, and every way of jumping back must still land.

let server: Server;
let http: APIRequestContext;
const bookIds: Record<string, string> = {};
const LONG = "A Long Valley";
const SHORT = "A Short Start";

test.beforeAll(async ({ playwright }, info) => {
  test.setTimeout(150_000);
  server = new Server(info.project.name === "phone" ? 18770 : 18769);
  const files = [makeFixture("long"), makeFixture("short")];
  await server.start();
  http = await playwright.request.newContext({ baseURL: server.url, extraHTTPHeaders: { "X-Proseway": "1" } });
  for (const f of files) {
    const r = await http.post("/api/books", { multipart: { files: { name: basename(f), mimeType: "application/pdf", buffer: readFileSync(f) } } });
    expect(r.ok(), await r.text()).toBeTruthy();
  }
  await expect
    .poll(
      async () => {
        const { books } = (await (await http.get("/api/books")).json()) as { books: { id: string; title: string; status: string }[] };
        for (const b of books) if (b.status === "ready") bookIds[b.title] = b.id;
        return Object.keys(bookIds).sort();
      },
      { timeout: 120_000, intervals: [500] },
    )
    .toEqual([LONG, SHORT]);
});

test.afterAll(async () => {
  await http?.dispose();
  await server?.stop();
});

const MAX = 3;
const TOLERANCE = 3; // px the first visible line may move while chapters load and unload
const STEP = 1200; // px per scroll step: past a screenful, so chapters come and go quickly

/* ------------------------------------------------------------------ helpers */

async function blockId(title: string, chapter: number, startsWith: string): Promise<string> {
  const { blocks } = (await (await http.get(`/api/books/${bookIds[title]}/chapters/${chapter}`)).json()) as { blocks: { id: string; text: string }[] };
  const b = startsWith ? blocks.find((x) => x.text.startsWith(startsWith)) : blocks[0];
  if (!b) throw new Error(`no block "${startsWith}" in chapter ${chapter}`);
  return b.id;
}

/** Open a book at a given block (default: the very start), independent of earlier tests. */
async function openAt(page: Page, title: string, at?: { chapter: number; text: string }) {
  const id = await blockId(title, at?.chapter ?? 0, at?.text ?? "");
  const r = await http.put(`/api/books/${bookIds[title]}/position`, { data: { blockId: id, progress: 0 } });
  expect(r.ok()).toBeTruthy();
  await page.goto(`${server.url}/book/${bookIds[title]}`);
  await expect(page.locator(`#b-${id}`)).toBeInViewport();
  await settle(page);
  return id;
}

/**
 * Wait until the reader is idle: no chapter downloads in flight (aria-busy) and the mounted
 * window unchanged over three samples, each two animation frames apart (enough for an
 * IntersectionObserver callback and a React commit to land between samples).
 */
async function settle(page: Page) {
  let prev = "";
  let same = 0;
  for (let i = 0; i < 300; i++) {
    const s = await page.evaluate(
      () =>
        new Promise<string>((done) =>
          requestAnimationFrame(() =>
            requestAnimationFrame(() => {
              const m = document.getElementById("reading");
              const mountedNow = Array.from(document.querySelectorAll<HTMLElement>("section.chapter"), (x) => x.dataset.chapter).join(",");
              done(`${m?.getAttribute("aria-busy")}|${m?.dataset.window}|${mountedNow}`);
            }),
          ),
        ),
    );
    same = s === prev && s.startsWith("false|") ? same + 1 : 0;
    if (same >= 2) return;
    prev = s;
  }
  throw new Error(`reader never settled (last: ${prev})`);
}

/** Record, from inside the page, the most chapters ever mounted at once and every one seen. */
async function watchChapters(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __maxChapters: number; __seen: Set<string> };
    const sample = () => {
      const secs = document.querySelectorAll<HTMLElement>("section.chapter");
      w.__maxChapters = Math.max(w.__maxChapters ?? 0, secs.length);
      for (const s of secs) w.__seen.add(s.dataset.chapter!);
    };
    w.__seen = new Set();
    w.__maxChapters = 0;
    sample();
    new MutationObserver(sample).observe(document.querySelector("article")!, { childList: true });
  });
}

async function maxMounted(page: Page): Promise<number> {
  return page.evaluate(() => (window as unknown as { __maxChapters: number }).__maxChapters);
}

async function seenChapters(page: Page): Promise<number[]> {
  return page.evaluate(() => [...(window as unknown as { __seen: Set<string> }).__seen].map(Number).sort((a, b) => a - b));
}

async function mounted(page: Page): Promise<number[]> {
  return page.locator("section.chapter").evaluateAll((els) => els.map((e) => Number((e as HTMLElement).dataset.chapter)));
}

async function showToolbar(page: Page) {
  // Scrolling up a little brings the auto-hidden toolbar back, as it does for a reader.
  await page.evaluate(() => window.scrollBy(0, 60));
  await page.waitForTimeout(50);
  await page.evaluate(() => window.scrollBy(0, -200));
  await expect(page.locator(".reader.chrome-on")).toBeVisible();
  await page.waitForTimeout(450); // slide-in transition
  await settle(page);
}

async function closePanel(page: Page, name: string) {
  // Desktop keeps panels open beside the text; phones close them on a jump.
  const panel = page.getByRole("dialog", { name });
  if (await panel.isVisible()) await panel.getByRole("button", { name: `Close ${name.toLowerCase()}` }).click();
}

/**
 * Scroll by `dy`, note the first block on screen right away (before any chapter loads or
 * unloads in response), let the reader settle, then return how far that block moved.
 */
async function scrollAndMeasure(page: Page, dy: number): Promise<{ id: string; moved: number; atTop: boolean; atEnd: boolean }> {
  const before = await page.evaluate((dy) => {
    window.scrollBy(0, dy);
    for (const b of document.querySelectorAll<HTMLElement>("article [data-block]")) {
      const r = b.getBoundingClientRect();
      if (r.bottom > 120) return { id: b.id, top: r.top };
    }
    return null;
  }, dy);
  expect(before, "a block is on screen").not.toBeNull();
  await settle(page);
  return page.evaluate(({ id, top }) => {
    const el = document.getElementById(id);
    const end = document.querySelector(".book-end");
    return {
      id,
      moved: el ? Math.abs(el.getBoundingClientRect().top - top) : Infinity,
      atTop: window.scrollY <= 0 && !!document.querySelector('section.chapter[data-chapter="0"]'),
      atEnd: !!end && end.getBoundingClientRect().top < window.innerHeight,
    };
  }, before!);
}

async function readToEnd(page: Page) {
  for (let steps = 0; ; steps++) {
    const r = await scrollAndMeasure(page, STEP);
    expect(r.moved, `block ${r.id} stayed put scrolling down (step ${steps})`).toBeLessThanOrEqual(TOLERANCE);
    if (r.atEnd) return;
    expect(steps, "reached the end of the book").toBeLessThan(400);
  }
}

async function readBackToStart(page: Page) {
  for (let steps = 0; ; steps++) {
    const r = await scrollAndMeasure(page, -STEP);
    expect(r.moved, `block ${r.id} stayed put scrolling up (step ${steps})`).toBeLessThanOrEqual(TOLERANCE);
    if (r.atTop) return;
    expect(steps, "got back to the start").toBeLessThan(400);
  }
}

/* ------------------------------------------------------------------ tests */

test("reading through six chapters keeps at most three mounted, without moving the text", async ({ page }) => {
  test.setTimeout(240_000); // the phone column is long
  await openAt(page, LONG);
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeVisible();
  await watchChapters(page);

  await readToEnd(page);
  await expect(page.getByRole("heading", { name: "Chapter Six" })).toBeAttached();
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);
  expect(await seenChapters(page)).toEqual([0, 1, 2, 3, 4, 5]);
  expect(await mounted(page)).toEqual([3, 4, 5]); // chapter one is long gone

  // Back up to the start: earlier chapters come back, and the text on screen stays put.
  await readBackToStart(page);
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeInViewport();
  await expect(page.getByText("Paragraph 1 of chapter one.")).toBeVisible();
  expect(await mounted(page)).toEqual([0, 1, 2]);
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);
});

test("tiny front-matter chapters don't stall loading", async ({ page }) => {
  test.setTimeout(240_000);
  await openAt(page, SHORT);
  await watchChapters(page);
  // Four one-line chapters fit on one screen; the first real chapter must load without any
  // scrolling at all (it used to stay a spinner forever).
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeAttached();
  await expect(page.getByText("Paragraph 1 of chapter one.")).toBeAttached();

  await readToEnd(page);
  await expect(page.getByRole("heading", { name: "Chapter Four" })).toBeAttached();
  expect(await seenChapters(page)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
  // Once the chapters are long again, the window is back to three.
  expect((await mounted(page)).length).toBeLessThanOrEqual(MAX);

  await readBackToStart(page);
  await expect(page.getByRole("heading", { name: "Prelude One" })).toBeInViewport();
});

test("restoring a position mid-book loads the chapter before it without moving the text", async ({ page }) => {
  const id = await openAt(page, LONG, { chapter: 3, text: "Paragraph 5 of chapter four." });
  await watchChapters(page);
  const block = page.locator(`#b-${id}`);
  const top = (await block.boundingBox())!.y;
  // Restored at the top of the screen, just under the toolbar (88px), not merely somewhere.
  expect(top).toBeGreaterThan(40);
  expect(top).toBeLessThan(140);
  await settle(page);
  const now = await mounted(page);
  expect(now).toContain(2); // the chapter before loaded above…
  expect(now).toContain(3);
  expect(now.length).toBeLessThanOrEqual(MAX);
  expect(Math.abs((await block.boundingBox())!.y - top)).toBeLessThanOrEqual(TOLERANCE); // …without moving the text

  // Scroll up into chapter three.
  for (let steps = 0; !(await isInViewport(page, "Chapter Three")); steps++) {
    const r = await scrollAndMeasure(page, -STEP / 2);
    expect(r.moved, `block ${r.id} stayed put scrolling up (step ${steps})`).toBeLessThanOrEqual(TOLERANCE);
    expect(steps).toBeLessThan(100);
  }
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);
});

async function isInViewport(page: Page, heading: string): Promise<boolean> {
  const box = await page.getByRole("heading", { name: heading }).boundingBox();
  const vp = page.viewportSize()!;
  return !!box && box.y >= 0 && box.y < vp.height;
}

test("contents, back-to and search jumps into unloaded chapters land on the text", async ({ page }) => {
  await openAt(page, LONG);
  await watchChapters(page);
  expect(await mounted(page)).not.toContain(5);

  // Contents → the last chapter, which isn't mounted.
  await page.getByRole("button", { name: "Contents" }).click();
  await page.getByRole("dialog", { name: "Contents" }).getByRole("button", { name: /Chapter Six/ }).click();
  await expect(page.getByRole("heading", { name: "Chapter Six" })).toBeInViewport();
  await closePanel(page, "Contents");
  await settle(page);
  expect(await mounted(page)).not.toContain(0);

  // "Back to p. N" returns to chapter one, which the jump unloaded.
  await page.getByRole("button", { name: /Back to p\./ }).click();
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeInViewport();
  await settle(page);
  expect(await mounted(page)).toContain(0);
  expect(await mounted(page)).not.toContain(5);

  // Search reaches into an unloaded chapter too.
  await showToolbar(page);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search this book" }).fill("Paragraph 3 of chapter five");
  await page.locator(".result").first().click();
  await expect(page.getByText("Paragraph 3 of chapter five.").first()).toBeInViewport();
  await settle(page);
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);
});

test("notes jump into an unloaded chapter, and highlights survive their chapter remounting", async ({ page }) => {
  const book = bookIds[LONG];
  const mk = async (chapter: number, text: string, note: string) => {
    const r = await http.post(`/api/books/${book}/annotations`, {
      data: { kind: "highlight", blockId: await blockId(LONG, chapter, text), start: 0, end: text.length, color: "green", note },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    return ((await r.json()) as { annotation: { id: string } }).annotation.id;
  };
  const early = await mk(0, "Paragraph 2 of chapter one", "early note");
  const late = await mk(5, "Paragraph 2 of chapter six", "late note");

  await openAt(page, LONG);
  await watchChapters(page);
  await expect(page.locator(`mark[data-ann="${early}"]`).first()).toBeAttached();
  expect(await mounted(page)).not.toContain(5);

  // Notes panel → the highlight in chapter six, which isn't mounted.
  await page.getByRole("button", { name: "Notes and highlights" }).click();
  await page.getByRole("dialog", { name: "Notes" }).locator(".note-quote", { hasText: "chapter six" }).click();
  await expect(page.locator(`mark[data-ann="${late}"]`).first()).toBeInViewport();
  await closePanel(page, "Notes");
  await settle(page);
  expect(await mounted(page)).not.toContain(0);

  // Back to chapter one: it remounts, and its highlight is drawn again.
  await page.getByRole("button", { name: /Back to p\./ }).click();
  await expect(page.locator(`mark[data-ann="${early}"]`).first()).toBeInViewport();
  await expect(page.locator(`mark[data-ann="${early}"]`).first()).toHaveText("Paragraph 2 of chapter one");
  await settle(page);
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);

  for (const id of [early, late]) await http.delete(`/api/annotations/${id}`);
});
