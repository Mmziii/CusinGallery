import { SITE_ORIGIN } from "../hooks/usePageMeta";

/**
 * Part S4 item 2: one place that decides which image represents a product,
 * category or brand in a share/SEO context (og:image, JSON-LD).
 *
 * The product page used to build `${SITE_ORIGIN}${product.primary_image}`,
 * but primary_image is an OBJECT (`{image, webp_400, webp_800, webp_1200}`)
 * and can be missing from the detail response -- so the tag became
 * "https://cusin.ir[object Object]" and the product's own image was never
 * used. Every URL here is absolute, and a product with no image falls back
 * to the shared brand placeholder.
 */

/** Shared 1200x630 brand placeholder (frontend/public/brand/), rendered
 *  from the existing mark.svg on the warm-grey field. */
export const OG_PLACEHOLDER = "/brand/og-placeholder.png";

//: Smallest share image we accept from the responsive variants. 400 is
//: below that, so it is never chosen; the original is the last resort
//: (we do not know its dimensions, and for uploaded photos it is usually
//: the largest file).
const MIN_SHARE_WIDTH = 600;
const VARIANT_ORDER = ["webp_1200", "webp_800"];

function toAbsolute(value) {
  if (!value) return null;
  const url = String(value);
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${SITE_ORIGIN}${url.startsWith("/") ? "" : "/"}${url}`;
}

/**
 * Site-root-relative (or absolute) src of the best share image for an
 * image payload, or null when there is nothing usable.
 * Accepts a string (a plain URL) or an API image object.
 */
export function shareImageSrc(image) {
  if (!image) return null;
  if (typeof image === "string") return image || null;
  for (const key of VARIANT_ORDER) {
    if (image[key]) return image[key];
  }
  if (image.image) return image.image;
  return null;
}

/**
 * ABSOLUTE share URL for an image payload; the shared brand placeholder
 * when the item has no usable image.
 */
export function shareImageUrl(image) {
  return toAbsolute(shareImageSrc(image)) || toAbsolute(OG_PLACEHOLDER);
}

/** ABSOLUTE URL for an already-resolved path (e.g. a canonical page URL). */
export function absoluteUrl(path) {
  return toAbsolute(path);
}

export { MIN_SHARE_WIDTH };
