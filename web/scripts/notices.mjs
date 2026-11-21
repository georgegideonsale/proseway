// Collect licence texts of everything bundled into the built web app (fonts and runtime
// libraries) into public/THIRD_PARTY_NOTICES.txt, which ships alongside the app.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(root, "package.json"));
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const bundled = [...Object.keys(pkg.dependencies), "scheduler"];

const parts = [
  "Proseway web app: third-party notices",
  "",
  "The Proseway reader bundles the following open-source software and fonts. Each is",
  "used under the licence reproduced below. The fonts are distributed unmodified as",
  "published by Fontsource (https://fontsource.org), which splits them into Unicode-range",
  "files for efficient loading.",
  "",
];
for (const name of bundled) {
  let dir;
  try {
    dir = dirname(require.resolve(`${name}/package.json`));
  } catch {
    continue;
  }
  const meta = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  const file = ["LICENSE", "LICENSE.md", "LICENSE.txt", "OFL.txt"].map((f) => join(dir, f)).find(existsSync);
  parts.push("=".repeat(78), `${meta.name} ${meta.version} (${meta.license})`, meta.homepage ?? "", "=".repeat(78));
  parts.push(file ? readFileSync(file, "utf8").trim() : "(licence text not included in the package)", "");
}
writeFileSync(join(root, "public", "THIRD_PARTY_NOTICES.txt"), parts.join("\n") + "\n");
console.log(`notices: ${bundled.length} packages`);
