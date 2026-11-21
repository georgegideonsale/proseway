// Proseway service worker: keeps the app shell and the chapters you've opened available
// offline. It only ever talks to the Proseway server it was installed from.
//
// When the server says this phone isn't paired (401, for instance after it was unpaired on
// the computer), every cache is dropped: cached chapters, notes and images must not outlive
// the pairing. The server also sends Clear-Site-Data with that 401.
const VERSION = "proseway-v2";
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

function forget() {
  return caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))));
}

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

  // Static build assets are content-hashed and public: cache first. Book images are book
  // data, so they go network first below, like chapters.
  if (url.pathname.startsWith("/assets/")) {
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
          } else if (res.status === 401) {
            event.waitUntil(forget());
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
