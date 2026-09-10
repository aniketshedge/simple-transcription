import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";

// Content-based cache names let each deployment refresh the offline page and icons.
const files = [
  "offline.html",
  "manifest.webmanifest",
  "sw.js",
  ...(await readdir("dist/icons")).sort().map((name) => `icons/${name}`),
];
const hash = createHash("sha256");
for (const file of files) hash.update(await readFile(`dist/${file}`));
const source = await readFile("dist/sw.js", "utf8");
await writeFile(
  "dist/sw.js",
  source.replace("__OFFLINE_VERSION__", hash.digest("hex").slice(0, 16)),
);
