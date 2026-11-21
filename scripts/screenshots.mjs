// Capture the README screenshots from a running Proseway (default http://127.0.0.1:8765).
//   node scripts/screenshots.mjs [baseUrl]
// Uses the Playwright install from web/node_modules.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(root, "web", "package.json"));
const { chromium, devices } = require("@playwright/test");
const base = process.argv[2] ?? "http://127.0.0.1:8765";
const out = join(root, "docs", "screenshots");
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();

async function shoot(name, { theme = "paper", phone = false }, fn) {
  const ctx = await browser.newContext(
    phone
      ? { ...devices["Pixel 7"], colorScheme: theme === "night" ? "dark" : "light" }
      : { viewport: { width: 1360, height: 860 }, deviceScaleFactor: 2, colorScheme: theme === "night" ? "dark" : "light" },
  );
  await ctx.addInitScript((t) => {
    localStorage.setItem("proseway.prefs.v1", JSON.stringify({ theme: t, font: "literata", size: 19, leading: 1.62, measure: "medium", justify: false }));
  }, theme);
  const page = await ctx.newPage();
  await fn(page);
  await page.waitForTimeout(700);
  await page.screenshot({ path: join(out, `${name}.png`) });
  await ctx.close();
  console.log("saved", name);
}

async function openBook(page, title) {
  await page.goto(base);
  await page.getByRole("link", { name: title }).first().click();
  await page.locator("article").waitFor();
  await page.waitForTimeout(600);
}

async function chrome(page) {
  await page.evaluate(() => window.scrollBy(0, 40));
  await page.waitForTimeout(60);
  await page.evaluate(() => window.scrollBy(0, -120));
  await page.waitForTimeout(450);
}

await shoot("library-desktop", { theme: "paper" }, async (p) => {
  await p.goto(base);
  await p.locator(".shelf img.cover").first().waitFor();
  await p.waitForTimeout(800);
});

await shoot("reader-desktop-notes", { theme: "paper" }, async (p) => {
  await openBook(p, "Pride and Prejudice");
  await chrome(p);
  await p.getByRole("button", { name: "Notes and highlights" }).click();
});

await shoot("reader-desktop-night", { theme: "night" }, async (p) => {
  await openBook(p, "The Legend of Sleepy Hollow");
  await chrome(p);
});

await shoot("reader-phone-sepia", { theme: "sepia", phone: true }, async (p) => {
  await openBook(p, "Pride and Prejudice");
  await chrome(p);
});

await shoot("reader-phone-appearance", { theme: "night", phone: true }, async (p) => {
  await openBook(p, "The Legend of Sleepy Hollow");
  await chrome(p);
  await p.getByRole("button", { name: "Appearance" }).click();
});

await shoot("library-phone", { theme: "paper", phone: true }, async (p) => {
  await p.goto(base);
  await p.locator(".shelf img.cover").first().waitFor();
});

await browser.close();
