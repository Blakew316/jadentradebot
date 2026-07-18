/* Service worker for the Jaden's Risk Calculator (JRC) PWA.
   The app is fully client-side, so a small cache-first shell makes it work
   offline once installed. Bump CACHE on breaking asset changes. */
"use strict";

const CACHE = "jrc-v9";
const SHELL = [
  "./",
  "manifest.webmanifest",
  "bg.jpg",
  "icons/icon-180.png",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-512-maskable.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  // Let the browser stream the background video directly — Range requests
  // and cache-first do not mix, and the poster image covers offline.
  const path = new URL(req.url).pathname;
  if (req.destination === "video" || path.endsWith("/bg.mp4") || path.endsWith("/bg.webm")) return;

  if (req.mode === "navigate") {
    // Navigations: freshest page when online, cached shell when offline.
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE).then((cache) => cache.put("./", copy));
          return resp;
        })
        .catch(() => caches.match("./"))
    );
    return;
  }

  event.respondWith(
    caches.match(req, { ignoreSearch: true }).then(
      (hit) =>
        hit ||
        fetch(req).then((resp) => {
          if (resp.status === 200) {   // never cache partial (206) responses
            const copy = resp.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return resp;
        })
    )
  );
});
