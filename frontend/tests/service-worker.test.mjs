import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

const source = await readFile(
  new URL("../public/sw.js", import.meta.url),
  "utf8",
);
function worker(
  fetchImpl = async () => new Response("online"),
  immediateTimeout = false,
) {
  const listeners = {};
  const cached = [];
  const deleted = [];
  const cacheNames = ["simple-transcription-offline-old", "another-app"];
  const self = {
    location: { origin: "https://nuc.example" },
    addEventListener: (type, fn) => {
      listeners[type] = fn;
    },
    skipWaiting: async () => {},
    clients: { claim: async () => {} },
  };
  vm.runInNewContext(source, {
    self,
    URL,
    Response,
    AbortController,
    Request: class extends Request {
      constructor(url, options) {
        super(new URL(url, self.location.origin), options);
      }
    },
    setTimeout: immediateTimeout
      ? (fn) => {
          queueMicrotask(fn);
          return 0;
        }
      : setTimeout,
    clearTimeout,
    fetch: fetchImpl,
    caches: {
      open: async () => ({
        addAll: async (requests) => cached.push(...requests.map((r) => r.url)),
      }),
      keys: async () => cacheNames,
      delete: async (name) => deleted.push(name),
      match: async (path) =>
        new Response(
          path === "/offline.html" ? "offline: check Tailscale" : "icon",
        ),
    },
  });
  return {
    cached,
    deleted,
    async lifecycle(type) {
      let promise;
      listeners[type]({
        waitUntil: (p) => {
          promise = p;
        },
      });
      await promise;
    },
    request(path, mode = "navigate", method = "GET") {
      let promise;
      listeners.fetch({
        request: {
          url: new URL(path, self.location.origin).href,
          mode,
          method,
        },
        respondWith: (p) => {
          promise = p;
        },
      });
      return promise;
    },
  };
}

test("offline cache contains only the fallback, manifest and icons", async () => {
  const sw = worker();
  await sw.lifecycle("install");
  assert.equal(sw.cached.length, 6);
  assert.ok(sw.cached.includes("https://nuc.example/offline.html"));
  assert.ok(
    sw.cached.every((url) => !url.includes("/api/") && !url.endsWith(".txt")),
  );
  for (const url of sw.cached)
    await readFile(
      new URL(`../public${new URL(url).pathname}`, import.meta.url),
    );
});
test("online navigation always gets the live app", async () => {
  assert.equal(await (await worker().request("/")).text(), "online");
});
test("unreachable server and HTTP 503 return the offline prompt", async () => {
  for (const fetch of [
    async () => {
      throw new TypeError("Disconnected");
    },
    async () => new Response("down", { status: 503 }),
  ]) {
    assert.match(
      await (await worker(fetch).request("/")).text(),
      /check Tailscale/,
    );
  }
});
test("a silent unreachable connection times out to the fallback", async () => {
  const fetch = (_, { signal }) =>
    new Promise((resolve, reject) =>
      signal.addEventListener("abort", () => reject(new Error("timeout"))),
    );
  assert.match(
    await (await worker(fetch, true).request("/")).text(),
    /check Tailscale/,
  );
});
test("API and downloads never get cached or replaced by HTML", () => {
  const sw = worker();
  for (const path of [
    "/api/jobs",
    "/api/health",
    "/api/files/example/download",
    "/api/files/example/preview",
  ]) {
    assert.equal(sw.request(path), undefined);
  }
  assert.equal(sw.request("/api/jobs", "cors", "POST"), undefined);
  assert.equal(sw.request("https://other.example/"), undefined);
});
test("activation removes only older caches owned by this app", async () => {
  const sw = worker();
  await sw.lifecycle("activate");
  assert.deepEqual(sw.deleted, ["simple-transcription-offline-old"]);
});
test("installation icons have the advertised PNG dimensions", async () => {
  const manifest = JSON.parse(
    await readFile(
      new URL("../public/manifest.webmanifest", import.meta.url),
      "utf8",
    ),
  );
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.scope, "/");
  for (const icon of manifest.icons) {
    const png = await readFile(
      new URL(`../public${icon.src}`, import.meta.url),
    );
    assert.equal(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`, icon.sizes);
  }
});
