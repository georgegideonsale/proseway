// Proseway service worker: keeps the app shell and the chapters you've opened available
// offline. It only ever talks to the Proseway server it was installed from.
const VERSION = "proseway-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function cacheable(url) {
  if (url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith("/assets/")) return true;
  return /^\/api\/books\/[0-9a-f]{32}\/(manifest|chapters\/\d+|assets\/.+|cover|annotations|position)$/.test(url.pathname);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Static build assets are content-hashed: cache first.
  if (url.pathname.startsWith("/assets/") || /\/assets\/[^/]+\.(png|jpg)$/.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) caches.open(VERSION).then((c) => c.put(req, res.clone()));
            return res;
          }),
      ),
    );
    return;
  }
  // Book data: network first, fall back to the last copy we saw.
  if (cacheable(url)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || Response.error())),
    );
    return;
  }
  // Navigation: network first, cached shell when offline.
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/")));
  }
});
