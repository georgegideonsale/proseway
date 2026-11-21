import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { Server } from "./server";

// The "Read on your phone" dialog. Turning sharing on needs a real network address, which CI
// machines may not have, so the sharing API is mocked here; tests/test_sharing_tls.py covers
// the real HTTPS listener.
let server: Server;

test.beforeAll(async ({}, info) => {
  // 18769/18770 are taken by the reader's e2e specs on another branch.
  server = new Server(info.project.name === "phone" ? 18782 : 18781);
  await server.start();
});

test.afterAll(async () => {
  await server?.stop();
});

const FP = Array.from({ length: 32 }, (_, i) => ((i * 37) % 256).toString(16).padStart(2, "0").toUpperCase()).join(":");

function state(over: Record<string, unknown>) {
  return {
    enabled: false,
    address: "",
    port: 0,
    url: "",
    scheme: "http",
    secure: false,
    secureAvailable: true,
    setupUrl: "",
    ca: null,
    expiresAt: null,
    pairing: null,
    locked: false,
    addresses: [{ interface: "Wi-Fi", address: "192.168.1.20" }],
    devices: [],
    ...over,
  };
}

const ON = state({
  enabled: true,
  address: "192.168.1.20",
  port: 8765,
  url: "https://192.168.1.20:8765",
  scheme: "https",
  secure: true,
  setupUrl: "http://192.168.1.20:8766/",
  ca: { fingerprint: FP, name: "CN=Proseway local CA 1A2B3C,O=Proseway", expiresAt: 2000000000 },
  expiresAt: Date.now() / 1000 + 7200,
  pairing: { code: "123456", expiresAt: Date.now() / 1000 + 300, url: "https://192.168.1.20:8765/pair#t=x" },
});

const QR = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#000"/></svg>`;

async function mock(page: Page) {
  let current = state({});
  const posted: unknown[] = [];
  await page.route("**/api/sharing", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      posted.push(body);
      current = body.enabled ? ON : state({});
    }
    await route.fulfill({ json: current });
  });
  await page.route("**/api/sharing/qr.svg*", (route) => route.fulfill({ body: QR, contentType: "image/svg+xml" }));
  return posted;
}

async function audit(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForTimeout(100);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

test("secure sharing: offered by default, then setup and pairing codes", async ({ page }) => {
  const posted = await mock(page);
  await page.goto(server.url);
  await page.getByRole("button", { name: "Read on your phone" }).click();
  const dialog = page.getByRole("dialog", { name: "Read on your phone" });
  // The hint is the checkbox's description, not part of its name (so it isn't read twice).
  const secure = dialog.getByRole("checkbox", { name: "Secure connection (recommended)", exact: true });
  await expect(secure).toBeChecked();
  await expect(secure).toHaveAccessibleDescription(/^Encrypts everything between your phone/);
  await audit(page);

  await dialog.getByRole("button", { name: "Turn on sharing" }).click();
  expect(posted[0]).toMatchObject({ enabled: true, secure: true, address: "192.168.1.20" });
  await expect(dialog.getByText("https://192.168.1.20:8765")).toBeVisible();
  await expect(dialog.getByRole("img", { name: /pairs your phone/ })).toBeVisible();
  await audit(page);

  await expect(dialog.locator(".pair-code")).toHaveText(/the code 1 2 3 4 5 6/);

  // First time on this phone: the QR switches to the certificate setup page. The button that
  // was clicked is gone, so focus goes to the new view's heading rather than the page.
  await dialog.getByRole("button", { name: "Set up this phone" }).click();
  await expect(dialog.getByRole("heading", { name: "Set up this phone" })).toBeFocused();
  await expect(dialog.getByRole("img", { name: /certificate setup page/ })).toBeVisible();
  const fingerprint = dialog.locator(".fingerprint");
  await expect(fingerprint).toContainText("SHA-256 fingerprint:");
  await expect(fingerprint).toContainText(FP.split(":").slice(0, 4).join(":"));
  await expect(dialog.getByRole("link", { name: "Download the certificate", exact: true })).toHaveAttribute("href", "/api/sharing/ca.crt");
  await audit(page);
  await dialog.getByRole("button", { name: "Done, show the pairing code" }).click();
  await expect(dialog.getByRole("heading", { name: "Pair your phone" })).toBeFocused();
  await expect(dialog.getByRole("img", { name: /pairs your phone/ })).toBeVisible();
});

test("plain HTTP stays available and the choice is remembered", async ({ page }) => {
  const posted = await mock(page);
  await page.goto(server.url);
  await page.getByRole("button", { name: "Read on your phone" }).click();
  const dialog = page.getByRole("dialog", { name: "Read on your phone" });
  await dialog.getByRole("checkbox", { name: /Secure connection/ }).uncheck();
  await expect(dialog.getByText(/someone else on the same network could see what you read/)).toBeVisible();
  await dialog.getByRole("button", { name: "Turn on sharing" }).click();
  expect(posted[0]).toMatchObject({ enabled: true, secure: false });
  expect(await page.evaluate(() => localStorage.getItem("proseway.share.secure"))).toBe("0");
});
