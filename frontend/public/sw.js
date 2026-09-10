/* The build script replaces this token with a hash of the offline assets. */
const CACHE = "simple-transcription-offline-__OFFLINE_VERSION__";
const STATIC_ASSETS = [
  "/offline.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/maskable-512.png",
  "/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      await cache.addAll(
        STATIC_ASSETS.map((url) => new Request(url, { cache: "reload" })),
      );
      // Only the fallback and icons are cached: activation cannot replace an open app's code.
      await self.skipWaiting();
    }),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) {
        if (name.startsWith("simple-transcription-offline-") && name !== CACHE)
          await caches.delete(name);
      }
      await self.clients.claim();
    })(),
  );
});

async function navigate(request) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(request, {
      signal: controller.signal,
      cache: "no-store",
    });
    if (response.status >= 500) throw new Error("Server unavailable");
    return response;
  } catch {
    const cached = await caches.match("/offline.html", { cacheName: CACHE });
    return (
      cached ||
      new Response(
        "Can’t reach your server. Check Tailscale or home Wi-Fi, then reload.",
        {
          status: 503,
          headers: { "Content-Type": "text/plain; charset=utf-8" },
        },
      )
    );
  } finally {
    clearTimeout(timeout);
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  // API responses, recordings, transcript previews and downloads must never enter this cache.
  // In particular, a failed transcript download must not be replaced with an HTML page.
  if (url.pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(navigate(request));
  } else if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(
      caches
        .match(url.pathname, { cacheName: CACHE })
        .then((cached) => cached || fetch(request)),
    );
  }
});
