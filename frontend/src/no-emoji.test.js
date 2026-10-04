/**
 * No-emoji guard (Part R2): the UI must never use emoji / Unicode
 * pictographs (no Google-style emoji). Icons are the inline SVG set in
 * components/Icon.jsx. This test scans every frontend source file and
 * fails when a pictograph codepoint appears (tests themselves are
 * excluded -- they may reference codepoints in order to police them).
 * Persian punctuation («»،؛‌ … ٪) and the multiplication sign are text,
 * not pictographs, and are allowed.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SRC = join(dirname(fileURLToPath(import.meta.url)));

const RANGES = [
  [0x1f000, 0x1faff], // emoji & pictographs
  [0x2190, 0x21ff], // arrows (↩ ←)
  [0x2300, 0x23ff], // miscellaneous technical (⌕)
  [0x25a0, 0x25ff], // geometric shapes (▾)
  [0x2600, 0x26ff], // miscellaneous symbols (★ ☎ ♥ ⚠)
  [0x2700, 0x27bf], // dingbats (✓ ✕)
  [0x2b00, 0x2bff], // stars/arrows extended
  [0xfe0f, 0xfe0f], // variation selector
];

function pictographs(text) {
  const found = new Set();
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (RANGES.some(([a, b]) => cp >= a && cp <= b)) found.add(`U+${cp.toString(16)}`);
  }
  return [...found];
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(jsx?|css)$/.test(entry) && !entry.includes(".test.")) out.push(path);
  }
  return out;
}

describe("no emoji in the UI source", () => {
  it("no pictograph codepoints anywhere in frontend/src", () => {
    const offenders = [];
    for (const file of walk(SRC)) {
      const hits = pictographs(readFileSync(file, "utf8"));
      if (hits.length) offenders.push(`${file}: ${hits.join(", ")}`);
    }
    expect(offenders).toEqual([]);
  });
});
