/** CSS-contract guards for the phone/desktop storefront live audit. */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const raw = readFileSync(join(here, "storefront.css"), "utf8");
const css = raw.replace(/\/\*[\s\S]*?\*\//g, "");
const normalized = css.replace(/\s+/g, " ");

function matchingBrace(source, openIndex) {
  let depth = 0;
  for (let index = openIndex; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  throw new Error(`Unclosed CSS block at ${openIndex}`);
}

function mediaBlocks(source) {
  const blocks = [];
  const pattern = /@media\s+([^{}]+)\{/g;
  let match;
  while ((match = pattern.exec(source))) {
    const openIndex = pattern.lastIndex - 1;
    const closeIndex = matchingBrace(source, openIndex);
    blocks.push({
      condition: match[1].trim(),
      contentStart: openIndex + 1,
      contentEnd: closeIndex,
      body: source.slice(openIndex + 1, closeIndex),
    });
  }
  return blocks;
}

const media = mediaBlocks(css);
const phoneCss = media
  .filter(({ condition }) => /max-width\s*:\s*767px/.test(condition))
  .map(({ body }) => body)
  .join("\n");

function declarationsFor(source, selector) {
  const declarations = [];
  const rulePattern = /([^{}]+)\{([^{}]*)\}/g;
  let match;
  while ((match = rulePattern.exec(source))) {
    const selectors = match[1]
      .split(",")
      .map((value) => value.trim().replace(/\s+/g, " "));
    if (selectors.includes(selector)) declarations.push(match[2].trim());
  }
  return declarations;
}

function hasDeclaration(source, selector, declaration) {
  return declarationsFor(source, selector).some((body) => declaration.test(body));
}

function channel(value) {
  const normalizedChannel = value / 255;
  return normalizedChannel <= 0.03928
    ? normalizedChannel / 12.92
    : ((normalizedChannel + 0.055) / 1.055) ** 2.4;
}

function luminance(rgb) {
  return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
}

function contrastRatio(foreground, background) {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

function darkOverlayOnWhite(alpha) {
  const overlay = [24, 30, 12];
  return overlay.map((channelValue) => channelValue * alpha + 255 * (1 - alpha));
}

describe("storefront live-audit CSS contracts", () => {
  it("only hides the load-more control at desktop widths", () => {
    const hiddenRules = [...css.matchAll(/\.shop__load-more\s*\{([^{}]*)\}/g)]
      .filter(([, declarations]) => /display\s*:\s*none\s*;?/.test(declarations));

    expect(hiddenRules).toHaveLength(1);
    const hiddenRule = hiddenRules[0];
    const desktopQuery = media.find(
      ({ condition, contentStart, contentEnd }) =>
        /min-width\s*:\s*768px/.test(condition) &&
        hiddenRule.index >= contentStart && hiddenRule.index < contentEnd
    );
    expect(desktopQuery).toBeTruthy();
    expect(hasDeclaration(phoneCss, ".shop__load-more", /display\s*:\s*inline-flex/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".shop__load-more", /min-height\s*:\s*44px/)).toBe(true);
  });

  it("gives the audited phone controls distinct 44px hit areas without resizing their icons", () => {
    // The two card buttons keep their existing 32px/36px visible circles;
    // transparent overlays supply the missing 12px/8px respectively.
    expect(hasDeclaration(phoneCss, ".product-card__heart", /width\s*:\s*32px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".product-card__heart", /height\s*:\s*32px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".product-card__heart::before", /inset\s*:\s*-6px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".product-card__add-icon", /width\s*:\s*36px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".product-card__add-icon", /height\s*:\s*36px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".product-card__add-icon::before", /inset\s*:\s*-4px/)).toBe(true);

    // A card heart is in the media corner; its cart action lives in the
    // footer. Their hit-area overlays therefore cannot meet or overlap.
    expect(hasDeclaration(phoneCss, ".cart-link", /width\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".cart-link", /height\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(normalized, ".cart-link__icon", /width:\s*26px/)).toBe(true);
    expect(hasDeclaration(normalized, ".cart-link__icon", /height:\s*26px/)).toBe(true);

    expect(hasDeclaration(phoneCss, ".section__head a", /min-width\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".section__head a::before", /inset\s*:\s*-9px\s*-4px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".deals-mobile__all", /min-width\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".deals-mobile__all::before", /inset\s*:\s*-6px\s*-4px/)).toBe(true);

    expect(hasDeclaration(phoneCss, ".rating-input .star", /width\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".rating-input .star", /height\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(normalized, ".site-footer__social a", /width:\s*36px/)).toBe(true);
    expect(hasDeclaration(normalized, ".site-footer__social a", /height:\s*36px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".site-footer__social a::before", /inset\s*:\s*-4px/)).toBe(true);

    expect(hasDeclaration(phoneCss, ".shop__mobile-btn", /min-height\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".sheet__close", /width\s*:\s*44px/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".sheet__close", /height\s*:\s*44px/)).toBe(true);
  });

  it("keeps the audited phone text classes at 12px or larger with compact card rhythm", () => {
    const minimumTextRules = [
      [".countdown__label", /font-size\s*:\s*12px/],
      [".product-card__badges .badge", /font-size\s*:\s*12px/],
      [".product-card__brand", /font-size\s*:\s*12px/],
      [".product-card__body .price__compare", /font-size\s*:\s*12px/],
    ];
    for (const [selector, declaration] of minimumTextRules) {
      expect(hasDeclaration(phoneCss, selector, declaration), selector).toBe(true);
    }
    expect(hasDeclaration(phoneCss, ".product-card__badges .badge", /line-height\s*:\s*1\.45/)).toBe(true);
    expect(hasDeclaration(phoneCss, ".product-card__brand", /height\s*:\s*1\.56em/)).toBe(true);
  });

  it("darkens category labels enough to preserve 4.5:1 contrast over light photos", () => {
    const categoryRule = declarationsFor(css, ".category-card__name").at(-1) || "";
    expect(categoryRule).toMatch(/linear-gradient\(to top,\s*rgba\(24,30,12,\.92\)\s*0%,\s*rgba\(24,30,12,\.8\)\s*72%,\s*rgba\(24,30,12,0\)\s*100%\)/);
    expect(categoryRule).toMatch(/padding\s*:\s*44px\s+8px\s+10px/);

    // White is the worst-case photo background; at the gradient's .8 stop,
    // ivory text still exceeds WCAG's 4.5:1 normal-text threshold.
    const ratio = contrastRatio([250, 247, 240], darkOverlayOnWhite(0.8));
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it("removes the rounded review card's top-border accent but retains gold stars", () => {
    const reviewRule = declarationsFor(css, ".review-highlight").at(-1) || "";
    expect(reviewRule).not.toMatch(/border-top\s*:/);
    expect(hasDeclaration(css, ".review-highlight__stars", /color\s*:\s*var\(--brand-gold-deep\)/)).toBe(true);
  });
});
