/**
 * Brand token contrast guard (Part R1): computes WCAG 2.1 contrast ratios
 * for every text/background token pair the UI actually uses and fails when
 * a normal-text pair drops below 4.5:1. This is the regression guard for
 * the "gold on white is unreadable" bug class: --brand-gold on a light
 * surface is ~1.9:1 and must never be a TEXT color (gold is allowed only on
 * dark green, or as a decorative accent / badge background with dark text).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "variables.css"), "utf8");

const TOKENS = {};
for (const [, name, value] of css.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) {
  TOKENS[name] = value;
}

function channel(c) {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}
function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}
export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const WHITE = "#ffffff";

/** [text token, background token or literal] pairs used for NORMAL text. */
const TEXT_PAIRS = [
  ["brand-ink", "brand-ivory"], // body text on page background
  ["brand-ink", WHITE], // body text on cards
  ["color-text-muted", "brand-ivory"], // secondary text
  ["color-text-muted", WHITE],
  ["brand-ivory", "brand-green-dark"], // header / footer text
  [WHITE, "brand-green"], // primary buttons
  [WHITE, "brand-green-dark"],
  ["brand-green-dark", "brand-gold"], // badge text on gold background
  ["brand-gold-deep", WHITE], // accent links on cards
  ["brand-gold-deep", "brand-ivory"], // accent links on page background
  [WHITE, "brand-gold-deep"],
  ["brand-green-dark", "brand-ivory"], // headings
];

describe("brand token contrast (WCAG 2.1)", () => {
  it("parses the brand tokens", () => {
    expect(TOKENS["brand-gold"]).toBe("#CEB464");
    expect(TOKENS["brand-green-dark"]).toBe("#2F3A18");
  });

  it("every normal text pair meets 4.5:1", () => {
    const failures = [];
    for (const [text, bg] of TEXT_PAIRS) {
      const fg = TOKENS[text] || text;
      const background = TOKENS[bg] || bg;
      const ratio = contrast(fg, background);
      if (ratio < 4.5) failures.push(`${text} on ${bg} = ${ratio.toFixed(2)}:1`);
    }
    expect(failures).toEqual([]);
  });

  it("documents why --brand-gold must never be text on light surfaces", () => {
    // informational assertion: gold on ivory/white is far below 4.5:1, so
    // the only legal gold-text contexts are dark-green surfaces.
    expect(contrast(TOKENS["brand-gold"], TOKENS["brand-ivory"])).toBeLessThan(2.5);
    expect(contrast(TOKENS["brand-gold"], WHITE)).toBeLessThan(2.5);
    // ...while gold on dark green passes even for normal text.
    expect(contrast(TOKENS["brand-gold"], TOKENS["brand-green-dark"])).toBeGreaterThanOrEqual(4.5);
  });
});
