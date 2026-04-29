import { copyFile, mkdir, readdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceDir = path.join(rootDir, "node_modules", "mermaid");
const publicDir = path.join(rootDir, "src", "markserv", "public");
const vendorDir = path.join(publicDir, "vendor");
const licensesDir = path.join(publicDir, "licenses");

const packageJson = JSON.parse(await readFile(path.join(sourceDir, "package.json"), "utf8"));
const sourceFile = path.join(sourceDir, "dist", "mermaid.esm.min.mjs");
const targetFile = path.join(vendorDir, "mermaid.esm.min.mjs");
const sourceChunksDir = path.join(sourceDir, "dist", "chunks", "mermaid.esm.min");
const targetChunksDir = path.join(vendorDir, "chunks", "mermaid.esm.min");
const sourceLicense = path.join(sourceDir, "LICENSE");
const targetLicense = path.join(licensesDir, "mermaid.LICENSE");

async function copyMjsTree(source, target) {
  await mkdir(target, { recursive: true });

  const entries = await readdir(source, { withFileTypes: true });
  await Promise.all(
    entries.map(async (entry) => {
      const sourcePath = path.join(source, entry.name);
      const targetPath = path.join(target, entry.name);

      if (entry.isDirectory()) {
        await copyMjsTree(sourcePath, targetPath);
      } else if (entry.isFile() && entry.name.endsWith(".mjs")) {
        await copyFile(sourcePath, targetPath);
      }
    }),
  );
}

await mkdir(vendorDir, { recursive: true });
await mkdir(licensesDir, { recursive: true });
await rm(targetChunksDir, { recursive: true, force: true });
await copyFile(sourceFile, targetFile);
await copyMjsTree(sourceChunksDir, targetChunksDir);
await copyFile(sourceLicense, targetLicense);

console.log(`Vendored Mermaid ${packageJson.version}`);
