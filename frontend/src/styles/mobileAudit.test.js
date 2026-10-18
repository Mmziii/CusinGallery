/**
 * Mobile layout + centering guard (Part S1). The owner reported a broken
 * mobile experience (horizontal scroll, off-center button text, too-small
 * tap targets) and we have no browser in CI, so this test pins the exact
 * CSS rules that fix those classes as a regression guard — the same
 * source-audit pattern as contrast.test.js.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const raw = readFileSync(join(here, "storefront.css"), "utf8");
const css = raw.replace(/\s+/g, " ");
const html = readFileSync(join(here, "..", "..", "index.html"), "utf8");

describe("S1 mobile + centering audit rules", () => {
  it("guards against horizontal scroll without breaking sticky positioning", () => {
    // `clip` must be used, not `hidden` (hidden creates a scroll container
    // and would silently break position: sticky for the header).
    expect(css).toMatch(/html\s*\{\s*overflow-x:\s*clip;\s*\}/);
    expect(css).not.toMatch(/html\s*\{[^}]*overflow-x:\s*hidden/);
  });

  it("anchors clear the sticky header (scroll-margin)", () => {
    expect(css).toMatch(/\[id\]\s*\{\s*scroll-margin-top:/);
  });

  it("centers control text with flex + tight line-height (Persian metrics)", () => {
    expect(css).toMatch(/\.btn\s*\{\s*line-height:\s*1\.2;/);
    for (const sel of [".chip", ".pagination button", ".account__nav a", ".category-bar__inner a"]) {
      expect(css.includes(sel)).toBe(true);
    }
    // those selectors live in a shared centered-controls rule
    expect(css).toMatch(/\.chip,\s*\.pagination button,[^{}]*\{[^}]*display:\s*inline-flex/);
  });

  it("animates the mobile navigation drawer with a reversible, reduced-motion-safe 250ms transition", () => {
    expect(css).toMatch(/\.site-header__drawer-panel\s*\{[^}]*animation:\s*mobile-drawer-panel-in 250ms ease-out both;/);
    expect(css).toMatch(/\.site-header__drawer-backdrop\s*\{[^}]*animation:\s*mobile-drawer-backdrop-in 250ms ease-out both;/);
    expect(css).toMatch(/\.site-header__drawer\.is-closing[^}]*animation-direction:\s*reverse/);
    expect(css).toMatch(/\.site-header__drawer-link\s*\{[^}]*min-height:\s*48px;/);
    expect(css).toMatch(/@media \(prefers-reduced-motion:\s*reduce\)\s*\{[^}]*animation-duration:\s*\.01ms/);
  });

  it("keeps the five trust benefits in one desktop row and scroll-snaps full items on phones", () => {
    expect(css).toMatch(/\.trust-strip__inner\s*\{[^}]*grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)/);
    expect(css).toMatch(/@media \(max-width:\s*767px\)\s*\{\s*\.trust-strip__inner\s*\{[^}]*scroll-snap-type:\s*x mandatory/);
    expect(css).toMatch(/\.trust-strip__item\s*\{[^}]*flex:\s*0 0 100%/);
    expect(css).toMatch(/\.trust-strip__item\s*\{[^}]*line-height:\s*1\.7/);
  });

  it("grows touch targets to at least 44px on touch devices", () => {
    expect(css).toMatch(/\.icon-btn\s*\{\s*width:\s*44px;\s*height:\s*44px;/);
    expect(css).toMatch(/\.qty-picker button\s*\{\s*width:\s*44px;\s*min-height:\s*44px;/);
    expect(css).toMatch(/\.pagination button\s*\{\s*min-height:\s*44px;/);
    // small icon-only controls keep their look but grow their hit area
    expect(css).toMatch(/inset:\s*-14px/);
    expect(css).toMatch(/\.site-header__burger\s*\{\s*width:\s*44px;\s*height:\s*44px;/);
  });

  it("prevents the iOS focus zoom: inputs are 16px under 640px", () => {
    expect(css).toMatch(/@media \(max-width:\s*640px\)\s*\{\s*input,\s*select,\s*textarea\s*\{\s*font-size:\s*16px;/);
  });

  it("applies safe-area insets to the fixed PDP bar and floating contact", () => {
    expect(css).toMatch(/\.product-detail__stickybar \{ padding-bottom: calc\(var\(--space-2\) \+ env\(safe-area-inset-bottom, 0px\)\)/);
    expect(css).toMatch(/\.floating-contact\s*\{\s*bottom:\s*calc\([^)]*env\(safe-area-inset-bottom/);
    // nothing may sit permanently under the floating contact near page end
    expect(css).toMatch(/\.site-footer\s*\{\s*padding-bottom:\s*96px/);
  });

  it("contains gallery images and enlarges them in a fixed fullscreen lightbox, never in place", () => {
    expect(css).toMatch(/\.product-gallery__stage\s*\{[^}]*overflow:\s*hidden/);
    expect(css).toMatch(/\.product-gallery__layer img\s*\{[^}]*object-fit:\s*contain/);
    expect(css).toMatch(/\.product-lightbox\s*\{[^}]*position:\s*fixed;[^}]*inset:\s*0/);
    expect(css).not.toContain(".is-zoomed");
  });

  it("styles inline address field errors and the required marker", () => {
    expect(css).toMatch(/\.field__error\s*\{\s*color:\s*var\(--color-danger\)/);
    expect(css).toMatch(/\.field__required\s*\{\s*color:\s*var\(--color-danger\)/);
    expect(css).toMatch(/\.field--error input/);
  });

  it("viewport meta requests full bleed so safe-area insets work", () => {
    expect(html).toMatch(/viewport-fit=cover/);
    expect(html).toMatch(/width=device-width/);
  });
});
