/**
 * Part S4 item 2: the share image is chosen in ONE place.
 *
 * Regression guard for the reported bug: the product page built
 * og:image as `${SITE_ORIGIN}${product.primary_image}`, but primary_image
 * is an object ({image, webp_*}); the tag therefore never pointed at a
 * real file. These tests pin the picking rules:
 *   - prefer the largest WebP variant of at least 600 px (1200 -> 800);
 *   - otherwise the original upload;
 *   - always absolute;
 *   - a product/category/brand with no image gets the brand placeholder.
 */
import { describe, expect, it } from "vitest";

import { SITE_ORIGIN } from "../hooks/usePageMeta";
import { OG_PLACEHOLDER, shareImageSrc, shareImageUrl } from "./shareImage";

describe("shareImageSrc", () => {
  const full = {
    image: "/media/products/pan.jpg",
    webp_400: "/media/products/pan-400.webp",
    webp_800: "/media/products/pan-800.webp",
    webp_1200: "/media/products/pan-1200.webp",
  };

  it("prefers the largest variant of at least 600px wide", () => {
    expect(shareImageSrc(full)).toBe("/media/products/pan-1200.webp");
    expect(shareImageSrc({ ...full, webp_1200: "" })).toBe("/media/products/pan-800.webp");
  });

  it("never picks the 400px variant (below 600px) and falls back to the original", () => {
    expect(shareImageSrc({ image: "/media/products/pan.jpg", webp_400: "/media/products/pan-400.webp" })).toBe(
      "/media/products/pan.jpg"
    );
  });

  it("accepts a plain string and returns null when there is no image", () => {
    expect(shareImageSrc("/media/products/pan.jpg")).toBe("/media/products/pan.jpg");
    expect(shareImageSrc(null)).toBeNull();
    expect(shareImageSrc({})).toBeNull();
  });
});

describe("shareImageUrl", () => {
  it("returns an ABSOLUTE url for a relative path", () => {
    expect(shareImageUrl({ webp_1200: "/media/products/pan-1200.webp" })).toBe(
      `${SITE_ORIGIN}/media/products/pan-1200.webp`
    );
  });

  it("leaves an already-absolute url alone", () => {
    const absolute = "https://cdn.example.test/products/pan.webp";
    expect(shareImageUrl({ webp_1200: absolute })).toBe(absolute);
  });

  it("falls back to the shared brand placeholder when there is no image", () => {
    expect(shareImageUrl(null)).toBe(`${SITE_ORIGIN}${OG_PLACEHOLDER}`);
    expect(shareImageUrl(undefined)).toBe(`${SITE_ORIGIN}${OG_PLACEHOLDER}`);
    expect(shareImageUrl({})).toBe(`${SITE_ORIGIN}${OG_PLACEHOLDER}`);
  });

  it("never produces an object-ish url (the original bug)", () => {
    // Passing the whole image object is the common mistake; the result
    // must still be a real URL, never "[object Object]".
    expect(shareImageUrl({ id: 3, image: "/media/products/pan.jpg" })).toBe(
      `${SITE_ORIGIN}/media/products/pan.jpg`
    );
    expect(shareImageUrl({ id: 3 })).not.toContain("object");
  });
});
