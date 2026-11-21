import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { makeFixture, Server } from "./server";

// Automated WCAG checks (axe-core) on the main screens, in a light and a dark theme.
let server: Server;

test.beforeAll(async ({}, info) => {
  server = new Server(info.project.name === "phone" ? 18768 : 18767);
  await server.start();
  const fixture = makeFixture();
  const fs = await import("node:fs");
  const form = new FormData();
  form.append("files", new Blob([fs.readFileSync(fixture)], { type: "application/pdf" }), "A Quiet Valley.pdf");
  await fetch(`${server.url}/api/books`, { method: "POST", body: form, headers: { "X-Proseway": "1" } });
  // Wait for the conversion to finish.
  for (let i = 0; i < 120; i++) {
    const { books } = await (await fetch(`${server.url}/api/books`)).json();
    if (books[0]?.status === "ready") break;
    await new Promise((r) => setTimeout(r, 500));
  }
});

test.afterAll(async () => {
  await server?.stop();
});

async function setTheme(page: Page, theme: string) {
  await page.addInitScript((t) => {
    localStorage.setItem("proseway.prefs.v1", JSON.stringify({ theme: t, font: "literata", size: 19, leading: 1.62, measure: "medium", justify: false }));
  }, theme);
}

async function audit(page: Page) {
  // Measure final colours, not frames of an entrance animation.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForTimeout(100);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    serious.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} ${n.failureSummary?.split("\n")[1] ?? ""}`).join(" | ")}`),
  ).toEqual([]);
}

for (const theme of ["paper", "night"]) {
  test(`library has no serious accessibility violations (${theme})`, async ({ page }) => {
    await setTheme(page, theme);
    await page.goto(server.url);
    await expect(page.getByRole("heading", { name: "Your library" })).toBeVisible();
    await audit(page);
  });

  test(`reader and notes panel have no serious accessibility violations (${theme})`, async ({ page }) => {
    await setTheme(page, theme);
    await page.goto(server.url);
    await page.locator(".book a").first().click();
    await expect(page.locator("article")).toBeVisible();
    await audit(page);
    await page.keyboard.press("n");
    await expect(page.getByRole("dialog", { name: "Notes" })).toBeVisible();
    await audit(page);
  });
}
