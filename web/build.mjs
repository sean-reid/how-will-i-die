// Production build: minify app.js and app.css, give them content-hashed names,
// and emit a dist/ with the HTML rewritten to reference the hashed files. The
// source files still work when served directly, so dev needs no build step.

import * as esbuild from "esbuild";
import { createHash } from "node:crypto";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

rmSync("dist", { recursive: true, force: true });
mkdirSync("dist", { recursive: true });

async function bundle(entry, loader) {
  const result = await esbuild.build({
    entryPoints: [entry],
    bundle: true,
    minify: true,
    write: false,
    loader,
  });
  return result.outputFiles[0].text;
}

function emit(prefix, ext, code) {
  const hash = createHash("sha256").update(code).digest("hex").slice(0, 8);
  const name = `${prefix}.${hash}.${ext}`;
  writeFileSync(`dist/${name}`, code);
  return name;
}

const jsName = emit("app", "js", await bundle("app.js", {}));
const cssName = emit("app", "css", await bundle("app.css", { ".css": "css" }));

for (const html of ["index.html", "about.html"]) {
  const rewritten = readFileSync(html, "utf8")
    .replace("app.css", cssName)
    .replace("app.js", jsName);
  writeFileSync(`dist/${html}`, rewritten);
}

cpSync("favicon.svg", "dist/favicon.svg");
cpSync("data", "dist/data", { recursive: true });

console.log(`built dist/ with ${jsName} and ${cssName}`);
