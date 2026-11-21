import { expect, test, type Page } from "@playwright/test";
import { makeFixture, Server } from "./server";

// One server per project; each test file gets its own library.
let server: Server;
let fixture: string;

test.beforeAll(async ({}, info) => {
  server = new Server(info.project.name === "phone" ? 18766 : 18765);
  fixture = makeFixture();
  await server.start();
});

test.afterAll(async () => {
  await server?.stop();
});

async function selectWords(page: Page, blockText: string, from: string, to: string) {
  // Build a real DOM selection over the given words and release the pointer, like a reader would.
  await page.evaluate(
    ({ blockText, from, to }) => {
      const blocks = Array.from(document.querySelectorAll<HTMLElement>("[data-block] .bt"));
      const bt = blocks.find((b) => b.textContent!.includes(blockText))!;
      const text = bt.textContent!;
      const start = text.indexOf(from);
      const end = text.indexOf(to) + to.length;
      const walker = document.createTreeWalker(bt, NodeFilter.SHOW_TEXT);
      let pos = 0;
      const range = document.createRange();
      let node: Node | null;
      while ((node = walker.nextNode())) {
        const len = node.textContent!.length;
        if (start >= pos && start <= pos + len) range.setStart(node, start - pos);
        if (end >= pos && end <= pos + len) {
          range.setEnd(node, end - pos);
          break;
        }
        pos += len;
      }
      const sel = window.getSelection()!;
      sel.removeAllRanges();
      sel.addRange(range);
      bt.scrollIntoView({ block: "center" });
      bt.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
    },
    { blockText, from, to },
  );
}

async function showToolbar(page: Page) {
  // Scrolling up a little brings the auto-hidden toolbar back, as it does for a reader.
  await page.evaluate(() => window.scrollBy(0, 60));
  await page.waitForTimeout(50);
  await page.evaluate(() => window.scrollBy(0, -200));
  await expect(page.locator(".reader.chrome-on")).toBeVisible();
  await page.waitForTimeout(450); // slide-in transition
}

test("import, read, highlight, note, bookmark, restart, everything is still there", async ({ page, request }) => {
  await page.goto(server.url);
  await expect(page.getByRole("heading", { name: "Bring a book you want to read properly" })).toBeVisible();

  // Import through the real file input.
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(fixture);
  const card = page.getByRole("link", { name: "Test Book" }).or(page.getByRole("link", { name: "Chapter One" }));
  await expect(card.first()).toBeVisible({ timeout: 45_000 });
  await card.first().click();

  // Reader shows the converted text, with header and page numbers gone.
  await expect(page.getByRole("heading", { name: "Chapter One" })).toBeVisible();
  await expect(page.getByText("Margaret walked down to the water").first()).toBeVisible();
  await expect(page.locator("article")).not.toContainText("A TEST BOOK");

  // Highlight a phrase in green (selection ends mid-word and snaps to the whole word).
  await selectWords(page, "Margaret walked down", "Margaret", "basket of bre");
  const toolbar = page.getByRole("toolbar", { name: "Highlight selection" });
  await expect(toolbar).toBeVisible();
  await toolbar.getByRole("button", { name: "Green highlight" }).click();
  const mark = page.locator("mark.hl-green").first();
  await expect(mark).toBeVisible();
  await expect(page.locator("mark.hl-green")).toHaveText(["Margaret walked down to the water every morning. She carried a basket of bread"]);

  // Add a note to it.
  await mark.click();
  const edit = page.getByRole("toolbar", { name: "Edit highlight" });
  await edit.getByRole("button", { name: "Add note" }).click();
  await page.getByPlaceholder("Write a note…").fill("Daily ritual: bread for the miller.");
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.locator("mark.hl-green.has-note").first()).toBeVisible();

  // Bookmark the current place.
  await showToolbar(page);
  await page.getByRole("button", { name: "Bookmark this place" }).click();
  await expect(page.getByRole("button", { name: "Remove bookmark here" })).toBeVisible();

  // Search finds a word and jumps to it.
  await showToolbar(page);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search this book" }).fill("woodsmoke");
  await page.locator(".result").first().click();
  await expect(page.getByRole("button", { name: /Back to p\./ })).toBeVisible();

  // Close the app completely and start it again.
  await page.waitForTimeout(1600); // let the reading position save
  await server.stop();
  await server.start();
  await page.reload();

  await expect(page.locator("mark.hl-green.has-note").first()).toBeVisible({ timeout: 15_000 });
  await showToolbar(page);
  await page.getByRole("button", { name: "Notes and highlights" }).click();
  const notes = page.getByRole("dialog", { name: "Notes" });
  await expect(notes).toContainText("Daily ritual: bread for the miller.");
  await notes.getByRole("tab", { name: /Bookmarks/ }).click();
  await expect(notes.locator(".bookmark-row")).toHaveCount(1);

  // Export notes as Markdown.
  const bookId = page.url().split("/book/")[1];
  const md = await (await request.get(`${server.url}/api/books/${bookId}/export.md`)).text();
  expect(md).toContain("> Margaret walked down to the water every morning. She carried a basket of bread");
  expect(md).toContain("Daily ritual: bread for the miller.");
  expect(md).toContain("## Bookmarks");
});

test("appearance settings apply and persist on this device", async ({ page }) => {
  await page.goto(server.url);
  await page.locator(".book a").first().click();
  await expect(page.locator("article")).toBeVisible();
  await showToolbar(page);
  await page.getByRole("button", { name: "Appearance" }).click();
  await page.getByText("Night", { exact: true }).click();
  await page.getByText("OpenDyslexic", { exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  const family = await page.locator("article").evaluate((el) => getComputedStyle(el).fontFamily);
  expect(family).toContain("OpenDyslexic");
});

test("keyboard: open panels, close them with Escape without leaving the book", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "keyboard shortcuts are a desktop feature");
  await page.goto(server.url);
  await page.locator(".book a").first().click();
  await expect(page.locator("article")).toBeVisible();
  await page.keyboard.press("t");
  await expect(page.getByRole("dialog", { name: "Contents" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Contents" })).toHaveCount(0);
  await expect(page).toHaveURL(/\/book\//);
});
