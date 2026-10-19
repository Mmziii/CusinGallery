/**
 * Storefront theme application (Task 2).
 *
 * The production shell (backend/apps/core/spa.py) already inlines the
 * owner-selected CSS custom properties into <head>, so the first paint is
 * correct with no flash. This module:
 *
 *  1. applies the same variables when the SPA runs from Vite in dev, or on
 *     any page whose shell predates the marker;
 *  2. re-applies them when /site/content/ arrives (a stale cached shell
 *     after an admin save must not keep the old palette for the session).
 *
 * Only names starting with "--" are accepted, so a malformed API payload
 * cannot set arbitrary CSS properties.
 */

export const THEME_VARIABLE_NAMES = Object.freeze([
  "--brand-green",
  "--brand-green-mid",
  "--brand-green-dark",
  "--brand-green-tint",
  "--brand-gold",
  "--brand-gold-deep",
  "--brand-ivory",
  "--brand-ink",
  "--color-primary",
  "--color-primary-dark",
  "--color-accent",
  "--color-bg",
  "--color-text",
  "--color-header-bg",
  "--color-header-text",
  "--color-header-brand",
  "--color-header-accent",
  "--color-button-text",
  "--color-border",
  "--radius-sm",
  "--radius-md",
  "--radius-lg",
  "--shadow-sm",
  "--shadow-md",
  "--shadow-lg",
  "--font-size-base",
]);

export function applyThemeVariables(variables) {
  if (!variables || typeof variables !== "object") return 0;
  const root = typeof document !== "undefined" ? document.documentElement : null;
  if (!root) return 0;
  let applied = 0;
  Object.entries(variables).forEach(([name, value]) => {
    if (!name.startsWith("--") || value === null || value === undefined) return;
    const text = String(value).trim();
    if (!text) return;
    root.style.setProperty(name, text);
    applied += 1;
  });
  return applied;
}

/** The variables the Django shell inlined before first paint, if any. */
export function readBootstrapTheme(win = typeof window !== "undefined" ? window : null) {
  if (!win || !win.__CUSIN_THEME__) return null;
  const theme = win.__CUSIN_THEME__.theme;
  return theme && theme.css_variables ? theme.css_variables : null;
}

/** Apply the bootstrap theme. Safe to call before React mounts. */
export function applyInitialTheme(win) {
  return applyThemeVariables(readBootstrapTheme(win));
}
