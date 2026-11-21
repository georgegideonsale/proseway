import type { Annotation, Block, Book, Manifest, SearchResult, SharingState } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Drop the offline copies of books (chapters, notes, images) the service worker keeps. Called
 * when the server says this phone isn't paired, for instance after it was unpaired on the
 * computer: the copies shouldn't outlive the pairing.
 */
export function forgetOfflineData() {
  if (typeof caches === "undefined") return; // only exists in secure contexts
  caches
    .keys()
    .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
    .catch(() => {});
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { "X-Proseway": "1" }, credentials: "same-origin" };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError(0, "offline", "Can't reach Proseway. Is it still running on your computer?");
  }
  if (res.status === 401) forgetOfflineData();
  if (!res.ok) {
    let code = "error";
    let message = `Request failed (${res.status}).`;
    try {
      const data = await res.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

export const api = {
  info: () => request<{ version: string; ocrAvailable: boolean; listener: "local" | "lan"; sharing: boolean }>("GET", "/api/info"),
  session: () =>
    request<{ listener: "local" | "lan"; paired: boolean }>("GET", "/api/session").then((s) => {
      if (s.listener === "lan" && !s.paired) forgetOfflineData();
      return s;
    }),
  books: () => request<{ books: Book[] }>("GET", "/api/books"),
  book: (id: string) => request<{ book: Book }>("GET", `/api/books/${id}`),
  importFiles: (files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    return request<{ results: { fileName: string; bookId?: string; duplicate?: boolean; error?: { message: string } }[] }>(
      "POST",
      "/api/books",
      fd,
    );
  },
  editBook: (id: string, fields: { title?: string; author?: string }) => request<{ book: Book }>("PATCH", `/api/books/${id}`, fields),
  deleteBook: (id: string) => request<{ ok: true }>("DELETE", `/api/books/${id}`),
  cancel: (id: string) => request<{ book: Book }>("POST", `/api/books/${id}/cancel`),
  resume: (id: string) => request<{ book: Book }>("POST", `/api/books/${id}/resume`),
  reconvert: (id: string) => request<{ book: Book }>("POST", `/api/books/${id}/reconvert`),
  manifest: (id: string) => request<Manifest>("GET", `/api/books/${id}/manifest`),
  chapter: (id: string, idx: number) => request<{ index: number; blocks: Block[] }>("GET", `/api/books/${id}/chapters/${idx}`),
  search: (id: string, q: string) => request<{ results: SearchResult[]; total: number }>("GET", `/api/books/${id}/search?q=${encodeURIComponent(q)}`),
  annotations: (id: string) => request<{ annotations: Annotation[] }>("GET", `/api/books/${id}/annotations`),
  createAnnotation: (
    id: string,
    a: { kind: "highlight" | "bookmark"; blockId: string; start?: number; end?: number; color?: string; note?: string; groupId?: string },
  ) => request<{ annotation: Annotation }>("POST", `/api/books/${id}/annotations`, a),
  updateAnnotation: (aid: string, fields: { color?: string; note?: string }) =>
    request<{ annotation: Annotation }>("PATCH", `/api/annotations/${aid}`, fields),
  deleteAnnotation: (aid: string) => request<{ ok: true }>("DELETE", `/api/annotations/${aid}`),
  position: (id: string) => request<{ position: { blockId: string; seq: number; progress: number } | null }>("GET", `/api/books/${id}/position`),
  savePosition: (id: string, blockId: string, progress: number) =>
    request<{ ok: true }>("PUT", `/api/books/${id}/position`, { blockId, progress }),
  restore: (file: File) => {
    const fd = new FormData();
    fd.append("file", file, file.name);
    return request<{ result: Record<string, number> }>("POST", "/api/restore", fd);
  },
  sharing: () => request<SharingState>("GET", "/api/sharing"),
  setSharing: (enabled: boolean, address?: string, minutes?: number, secure?: boolean) =>
    request<SharingState>("POST", "/api/sharing", { enabled, address, minutes, secure }),
  newCode: () => request<SharingState>("POST", "/api/sharing/new-code"),
  revokeDevice: (id: string) => request<SharingState>("DELETE", `/api/devices/${id}`),
  pair: (secret: string) => request<{ ok: true }>("POST", "/api/pair", { secret }),
};

export const assetUrl = (bookId: string, name: string) => `/api/books/${bookId}/assets/${encodeURIComponent(name)}`;
export const coverUrl = (bookId: string, v?: number) => `/api/books/${bookId}/cover${v ? `?v=${Math.round(v)}` : ""}`;
