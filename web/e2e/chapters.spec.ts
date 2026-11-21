import { expect, test, type Page } from "@playwright/test";
import { makeFixture, Server } from "./server";

// The reader keeps at most 3 chapters mounted. Reading straight through a six-chapter book
// must never hold more, unloading above the screen must not move the text, and scrolling or
// jumping back must bring the earlier chapters back.

let server: Server;
let fixture: string;

test.beforeAll(async ({}, info) => {
  server = new Server(info.project.name === "phone" ? 18770 : 18769);
  fixture = makeFixture("long");
  await server.start();
});

test.afterAll(async () => {
  await server?.stop();
});

const MAX = 3;
const TOLERANCE = 3; // px the first visible line may move while chapters load and unload
const STEP = 1200; // px per scroll step: past a screenful, so chapters come and go quickly

/** Open the long book, importing it first if this server's library doesn't have it yet. */
async function openBook(page: Page) {
  await page.goto(server.url);
  const card = page.getByRole("link", { name: "A Long Valley" });
  await expect(card.or(page.getByRole("heading", { name: "Bring a book you want to read properly" })).first()).toBeVisible();
  if (!(await card.count())) await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(fixture);
  await expect(card.first()).toBeVisible({ timeout: 60_000 });
  await card.first().click();
  await expect(page.locator("section.chapter").first()).toBeVisible();
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
    sample();
    new MutationObserver(sample).observe(document.querySelector("article")!, { childList: true });
  });
}

async function showToolbar(page: Page) {
  // Scrolling up a little brings the auto-hidden toolbar back, as it does for a reader.
  await page.evaluate(() => window.scrollBy(0, 60));
  await page.waitForTimeout(50);
  await page.evaluate(() => window.scrollBy(0, -200));
  await expect(page.locator(".reader.chrome-on")).toBeVisible();
  await page.waitForTimeout(450); // slide-in transition
}

async function maxMounted(page: Page): Promise<number> {
  return page.evaluate(() => (window as unknown as { __maxChapters: number }).__maxChapters);
}

async function mounted(page: Page): Promise<number[]> {
  return page.locator("section.chapter").evaluateAll((els) => els.map((e) => Number((e as HTMLElement).dataset.chapter)));
}

/**
 * Scroll by `dy`, note the first block on screen right away (before any chapter loads or
 * unloads in response), let the reader react, then return how far that block moved.
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
  await page.waitForTimeout(350);
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

test("reading through six chapters keeps at most three mounted, without moving the text", async ({ page }) => {
  test.setTimeout(240_000); // the phone column is long
  await openBook(page);
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeVisible();
  await page.waitForTimeout(600); // the first neighbours load
  await watchChapters(page);

  // Read straight down to the end of the book.
  let steps = 0;
  for (;;) {
    const r = await scrollAndMeasure(page, STEP);
    expect(r.moved, `block ${r.id} stayed put scrolling down (step ${steps})`).toBeLessThanOrEqual(TOLERANCE);
    if (r.atEnd) break;
    expect(++steps, "reached the end of the book").toBeLessThan(400);
  }
  await expect(page.getByRole("heading", { name: "Chapter Six" })).toBeAttached();
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);
  const seen = await page.evaluate(() => [...(window as unknown as { __seen: Set<string> }).__seen].map(Number).sort());
  expect(seen).toEqual([0, 1, 2, 3, 4, 5]);
  expect(await mounted(page)).toEqual([3, 4, 5]); // chapter one is long gone

  // Scroll back up to the start: earlier chapters come back, and the text on screen stays put.
  steps = 0;
  for (;;) {
    const r = await scrollAndMeasure(page, -STEP);
    expect(r.moved, `block ${r.id} stayed put scrolling up (step ${steps})`).toBeLessThanOrEqual(TOLERANCE);
    if (r.atTop) break;
    expect(++steps, "got back to the start").toBeLessThan(400);
  }
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeInViewport();
  await expect(page.getByText("Paragraph 1 of chapter one.")).toBeVisible();
  expect(await mounted(page)).toEqual([0, 1, 2]);
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);
});

test("jumps into unloaded chapters and back still land on the text", async ({ page }) => {
  await openBook(page);
  // The saved position (the start, where the last test ended) is restored.
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeInViewport();
  await page.waitForTimeout(600);
  await watchChapters(page);
  expect(await mounted(page)).not.toContain(5);

  // Contents → the last chapter, which isn't mounted.
  await page.getByRole("button", { name: "Contents" }).click();
  await page.getByRole("dialog", { name: "Contents" }).getByRole("button", { name: /Chapter Six/ }).click();
  await expect(page.getByRole("heading", { name: "Chapter Six" })).toBeInViewport();
  const toc = page.getByRole("dialog", { name: "Contents" });
  if (await toc.isVisible()) await toc.getByRole("button", { name: /close/i }).first().click(); // desktop keeps it open beside the text
  await page.waitForTimeout(600);
  expect(await mounted(page)).not.toContain(0);

  // "Back to p. N" returns to chapter one, which was unloaded by the jump.
  await page.getByRole("button", { name: /Back to p\./ }).click();
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeInViewport();
  await page.waitForTimeout(600);
  expect(await mounted(page)).toContain(0);
  expect(await mounted(page)).not.toContain(5);

  // Search reaches into an unloaded chapter too.
  await showToolbar(page);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search this book" }).fill("Paragraph 3 of chapter five");
  await page.locator(".result").first().click();
  await expect(page.getByText("Paragraph 3 of chapter five.").first()).toBeInViewport();
  expect(await maxMounted(page)).toBeLessThanOrEqual(MAX);
});
