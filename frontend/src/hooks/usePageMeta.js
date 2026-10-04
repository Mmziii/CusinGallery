import { useEffect } from "react";

/**
 * Per-page SEO metadata (Phase E).
 *
 * Sets document.title, meta description, meta robots, the canonical
 * link and the Open Graph basics for the current page, and restores
 * nothing on unmount (the next page overwrites everything -- there is
 * always exactly one page mounted).
 *
 * Honest limitation (also documented in docs/DEPLOY.md): this is a
 * client-rendered SPA, so search engines that execute JavaScript (Google)
 * see these values, but social-network crawlers that don't (Telegram,
 * Twitter, ...) only see the site-wide defaults baked into index.html.
 * True per-product OG tags would require SSR/prerendering.
 *
 * VITE_SITE_ORIGIN is the canonical public origin (build-time variable,
 * default https://cusin.ir) -- same-origin deployments only need the
 * default.
 */

const SITE_ORIGIN = (import.meta.env.VITE_SITE_ORIGIN || "https://cusin.ir").replace(/\/$/, "");
const SITE_NAME = "کازین گالری";
const DEFAULT_TITLE = `${SITE_NAME} | فروشگاه لوازم آشپزخانه، بلور و کریستال`;
const DEFAULT_DESCRIPTION =
  "فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانه. ارسال به سراسر ایران، پرداخت امن اینترنتی.";

function setMeta(attr, key, content) {
  let tag = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!content) {
    if (tag) tag.remove();
    return;
  }
  if (!tag) {
    tag = document.createElement("meta");
    tag.setAttribute(attr, key);
    document.head.appendChild(tag);
  }
  tag.setAttribute("content", content);
}

function setCanonical(href) {
  let link = document.head.querySelector('link[rel="canonical"]');
  if (!href) {
    if (link) link.remove();
    return;
  }
  if (!link) {
    link = document.createElement("link");
    link.setAttribute("rel", "canonical");
    document.head.appendChild(link);
  }
  link.setAttribute("href", href);
}

export function usePageMeta({ title, description, path, noindex = false, image } = {}) {
  useEffect(() => {
    document.title = title ? `${title} | ${SITE_NAME}` : DEFAULT_TITLE;

    setMeta("name", "description", noindex ? null : description || DEFAULT_DESCRIPTION);
    setMeta("name", "robots", noindex ? "noindex, nofollow" : null);

    const url = `${SITE_ORIGIN}${path || "/"}`;
    // Private/utility pages get NO canonical: a canonical would tell
    // crawlers to index them under that URL, which is exactly what
    // noindex forbids -- the two must never contradict each other.
    setCanonical(noindex ? null : url);

    setMeta("property", "og:title", title ? `${title} | ${SITE_NAME}` : DEFAULT_TITLE);
    setMeta("property", "og:description", description || DEFAULT_DESCRIPTION);
    setMeta("property", "og:url", url);
    setMeta("property", "og:type", (path || "").startsWith("/products/") ? "product" : "website");
    if (image) setMeta("property", "og:image", image);
  }, [title, description, path, noindex, image]);
}

export { SITE_ORIGIN, SITE_NAME };
