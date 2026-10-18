/**
 * Lazy (non-reactive) viewport checks.
 *
 * Some layout decisions are made once per interaction,
 * not per render -- e.g. whether the mega menu's hover
 * panel (desktop) or its drill-down sheet (phone) is the
 * surface that just opened. A lazy read keeps those
 * components free of a reactive subscription (and of the
 * re-render it would cause); CSS media queries remain
 * the source of truth for what is VISIBLE.
 *
 * Tolerates incomplete matchMedia mocks (tests): a
 * missing method simply reads as "not desktop".
 */
export function isDesktopViewport() {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  const query = window.matchMedia("(min-width: 1024px)");
  return Boolean(query && query.matches);
}
