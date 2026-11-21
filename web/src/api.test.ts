import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

// The service worker keeps chapters, notes and images for offline reading. When the server
// says this phone isn't paired (for instance it was unpaired on the computer), the page drops
// them.
function fakeCaches() {
  const deleted: string[] = [];
  const store = {
    keys: vi.fn(async () => ["proseway-v2", "other"]),
    delete: vi.fn(async (k: string) => (deleted.push(k), true)),
  };
  vi.stubGlobal("caches", store);
  return deleted;
}

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })),
  );
}

const settle = () => new Promise((r) => setTimeout(r, 0));

afterEach(() => vi.unstubAllGlobals());

describe("offline copies", () => {
  it("are dropped when a request comes back 401", async () => {
    const deleted = fakeCaches();
    respond(401, { error: { code: "not_paired", message: "This device isn't paired yet." } });
    await expect(api.books()).rejects.toBeInstanceOf(ApiError);
    await settle();
    expect(deleted).toEqual(["proseway-v2", "other"]);
  });

  it("are dropped when the session says the phone isn't paired", async () => {
    const deleted = fakeCaches();
    respond(200, { listener: "lan", paired: false });
    await api.session();
    await settle();
    expect(deleted).toEqual(["proseway-v2", "other"]);
  });

  it("are kept for a paired phone and on the computer", async () => {
    const deleted = fakeCaches();
    respond(200, { listener: "lan", paired: true });
    await api.session();
    respond(200, { listener: "local", paired: true });
    await api.session();
    respond(403, { error: { code: "local_only", message: "No." } });
    await expect(api.books()).rejects.toBeInstanceOf(ApiError);
    await settle();
    expect(deleted).toEqual([]);
  });
});
