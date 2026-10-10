/**
 * Part S4 items 1 + 2: source guards.
 *
 * Item 1 asks for a test or lint rule that fails if a RAW <img> for a
 * product, category or brand image appears outside the shared image
 * component (SmartImage). Static brand assets (the logo/mark/lockup in
 * frontend/public/brand, which are site chrome, not catalog data) are
 * allowlisted, as is the single decorative hover layer in ProductCard,
 * which is annotated with @catalog-img-allowed and hides itself on error.
 *
 * Item 2 asks for the product/category/brand share image to be built
 * through one helper; these guards also stop the original bug class from
 * coming back (interpolating a raw image field into a URL string).
 */
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const SRC = path.resolve(__dirname);

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules") continue;
      walk(full, out);
    } else if (/\.(js|jsx)$/.test(entry.name)) {
      // Tests build their own fixtures; the guard is about shipped code.
      if (/\.test\.(js|jsx)$/.test(entry.name)) continue;
      out.push(full);
    }
  }
  return out;
}

/**
 * Source with comments blanked out (newline count preserved, so line
 * numbers still match the file), so prose in a comment can never trip the
 * guard -- while a real `@catalog-img-allowed` annotation is still visible
 * in the raw lines next to it.
 */
function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, ""))
    .join("\n");
}

const FILES = walk(SRC).map((file) => {
  const text = fs.readFileSync(file, "utf8");
  return {
    rel: path.relative(SRC, file),
    text,
    rawLines: text.split("\n"),
    code: stripComments(text),
  };
});

/** Brand asset paths shipped from frontend/public/brand (the site chrome). */
const STATIC_BRAND_ASSETS = /["'`](\/brand\/[^"'`]+)["'`]/;

/** Field names that carry a product / category / brand image URL. */
const CATALOG_IMAGE_FIELD = /(product|primary_image|secondary|tile_image|category|brand|\.image|logo)/i;

describe("raw catalog <img> elements", () => {
  it("only the shared SmartImage component renders catalog images", () => {
    const offenders = [];
    for (const { rel, code, rawLines } of FILES) {
      if (rel.endsWith(path.join("components", "SmartImage.jsx"))) continue;
      const lines = code.split("\n");
      lines.forEach((line, index) => {
        if (!/<img\b/.test(line)) return;
        // Static brand asset (logo/mark/lockup): chrome, not catalog data.
        if (STATIC_BRAND_ASSETS.test(line)) return;
        // Explicit, reviewed exception: the annotation comment sits right
        // above the element it covers (checked against the RAW lines, since
        // stripping comments would hide it).
        if (/@catalog-img-allowed/.test(rawLines.slice(Math.max(0, index - 8), index + 1).join(" "))) return;
        const chunk = lines.slice(index, index + 14).join(" ");
        const src = chunk.match(/src=\{([^}]+)\}/);
        if (src && CATALOG_IMAGE_FIELD.test(src[1])) {
          offenders.push(`${rel}:${index + 1} -> ${line.trim()}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the allowlist honest (static brand assets really are used)", () => {
    const users = FILES.filter(({ code }) => STATIC_BRAND_ASSETS.test(code));
    expect(users.length).toBeGreaterThan(0);
  });

  it("documents the reviewed exceptions", () => {
    const allowed = FILES.filter(({ rawLines }) => /@catalog-img-allowed/.test(rawLines.join("\n")));
    // Exactly one today: ProductCard's decorative hover layer.
    expect(allowed.map((f) => f.rel)).toEqual([path.join("components", "ProductCard.jsx")]);
  });
});

describe("share-image URL building (Part S4 item 2 regression guard)", () => {
  it("never interpolates a raw image field into a URL outside the helper", () => {
    const offenders = [];
    for (const { rel, code } of FILES) {
      if (rel.endsWith(path.join("utils", "shareImage.js"))) continue;
      code.split("\n").forEach((line, index) => {
        // The original bug: `${SITE_ORIGIN}${product.primary_image}` -- a raw
        // asset value concatenated into a URL.
        if (/\$\{[^}]*\.(image|primary_image|tile_image|logo)\}/.test(line)) {
          offenders.push(`${rel}:${index + 1} -> ${line.trim()}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });

  it("routes every og:image supplied by a page through the helper", () => {
    const offenders = [];
    for (const { rel, code } of FILES) {
      if (rel.endsWith(path.join("hooks", "usePageMeta.js"))) continue;
      code.match(/usePageMeta\(\{[\s\S]*?\}\)/g)?.forEach((call) => {
        const imageLine = call.split("\n").find((line) => /^\s*image:/.test(line));
        if (!imageLine) return;
        // The value must come from the shared helper (shareImageUrl,
        // typically stored in an ogImage/…ShareImage variable) or be
        // explicitly undefined (site-wide default).
        const allowed = /[Ss]hareImage|ogImage|undefined/.test(imageLine);
        if (!allowed) offenders.push(`${rel} -> ${imageLine.trim()}`);
      });
    }
    expect(offenders).toEqual([]);
  });
});
