/**
 * Test helper: resolve the value a browser would use for one CSS property.
 *
 * Why this exists: jsdom's getComputedStyle takes the LAST matching declaration
 * in source order. It ignores specificity and !important. That is not how
 * browsers resolve styles, and the bug this guards against is exactly a
 * specificity/importance question (`.cusin-palette { display: flex }` beating
 * the browser's [hidden] rule). So this resolver applies the CSS rules:
 *   1. !important beats normal declarations,
 *   2. then higher specificity wins,
 *   3. then the later rule in source order.
 * Media rules are evaluated at a given viewport width (max-width / min-width).
 * `visibility` is inherited; `display` falls back to the browser's [hidden]
 * default (display: none) when no author rule sets it.
 *
 * It is verified against spec-defined outcomes in cssVisibility.test.js.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const THEME_CSS = path.resolve(HERE, "../../../backend/static/admin_theme/css/theme.css");

const STYLE_RULE = 1;
const MEDIA_RULE = 4;
const INHERITED = new Set(["visibility"]);

/** The real stylesheet text, exactly as the admin serves it. */
export function readThemeCss(file = THEME_CSS) {
  return fs.readFileSync(file, "utf8");
}

/** Split a selector list on commas that are not inside (), [] or quotes. */
function splitSelectorList(text) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let current = "";
  for (const ch of text) {
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
    } else if (ch === "(" || ch === "[") {
      depth += 1;
    } else if (ch === ")" || ch === "]") {
      depth -= 1;
    } else if (ch === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }
    current += ch;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

/** CSS specificity as one number: ids * 10000 + classes * 100 + types. */
export function specificity(selector) {
  const text = selector.replace(/"[^"]*"|'[^']*'/g, '""');
  const ids = (text.match(/#[\w-]+/g) || []).length;
  const classes =
    (text.match(/\.[\w-]+/g) || []).length +
    (text.match(/\[[^\]]*\]/g) || []).length +
    (text.match(/:(?!:)[\w-]+/g) || []).length;
  const types =
    (text.match(/(^|[\s>+~,(])[a-zA-Z][\w-]*/g) || []).length +
    (text.match(/::[\w-]+/g) || []).length;
  return ids * 10000 + classes * 100 + types;
}

function matches(el, selector) {
  try {
    return el.matches(selector);
  } catch {
    // selectors jsdom cannot parse (e.g. some pseudo-elements) never apply here
    return false;
  }
}

/** Evaluate a media query list at `width` px. Print never applies on screen. */
export function mediaMatches(mediaText, width) {
  return mediaText.split(",").some((query) => {
    const text = query.trim().toLowerCase();
    if (!text || text.startsWith("print")) return false;
    const conditions = text.match(/\([^)]+\)/g) || [];
    if (!conditions.length) return false;
    return conditions.every((raw) => {
      const [feature, value] = raw.slice(1, -1).split(":").map((part) => part.trim());
      const px = parseFloat(value);
      if (feature === "max-width") return width <= px;
      if (feature === "min-width") return width >= px;
      // prefers-reduced-motion, prefers-color-scheme, ...: not applied here
      return false;
    });
  });
}

function* styleRules(rules, width) {
  for (const rule of rules) {
    if (rule.type === STYLE_RULE) {
      yield rule;
    } else if (rule.type === MEDIA_RULE && mediaMatches(rule.media.mediaText, width)) {
      yield* styleRules(rule.cssRules, width);
    }
  }
}

function compareKeys(a, b) {
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return 0;
}

/** The winning declaration for `prop` on `el` among author rules, or null. */
export function specifiedValue(doc, el, prop, width) {
  let best = null;
  let order = 0;
  for (const sheet of doc.styleSheets) {
    for (const rule of styleRules(sheet.cssRules, width)) {
      order += 1;
      const value = rule.style.getPropertyValue(prop);
      if (!value) continue;
      const important = rule.style.getPropertyPriority(prop) === "important" ? 1 : 0;
      for (const selector of splitSelectorList(rule.selectorText)) {
        if (!matches(el, selector)) continue;
        const key = [important, specificity(selector), order];
        if (!best || compareKeys(key, best.key) > 0) best = { key, value: value.trim() };
      }
    }
  }
  return best ? best.value : null;
}

/**
 * The value a browser would use for `prop` on `el` at a viewport `width`.
 * Returns a string such as "none", "flex" or "hidden".
 */
export function resolveStyle(el, prop, { width = 1280 } = {}) {
  const doc = el.ownerDocument;
  const specified = specifiedValue(doc, el, prop, width);
  if (specified !== null) return specified;
  if (INHERITED.has(prop)) {
    const parent = el.parentElement;
    return parent ? resolveStyle(parent, prop, { width }) : "visible";
  }
  // browser default for [hidden]; any author display rule has already won above
  if (prop === "display" && el.hasAttribute("hidden")) return "none";
  return doc.defaultView.getComputedStyle(el).getPropertyValue(prop);
}
