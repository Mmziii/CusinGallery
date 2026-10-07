/**
 * Test helper: resolve the real stylesheet cascade for a rendered DOM and
 * report the foreground/background contrast of every text node.
 *
 * It is deliberately NOT a string/regex check on the CSS source: the CSS
 * files are parsed with postcss, custom properties (var()) are resolved
 * from :root, the result is injected into the jsdom document that holds
 * the RENDERED components, and the winning declarations come from
 * window.getComputedStyle() -- i.e. the cascade (matching, order,
 * specificity, !important) and color inheritance are decided by the DOM
 * engine, exactly as the browser would, for the elements that are really
 * mounted.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import postcss from "postcss";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STYLE_DIR = path.resolve(HERE, "../../src/styles");

/** files in the exact order src/main.jsx imports them. */
export const STYLESHEET_ORDER = ["variables.css", "globals.css", "storefront.css"];

function readSheets() {
  return STYLESHEET_ORDER.map((name) => ({
    name,
    text: fs.readFileSync(path.join(STYLE_DIR, name), "utf8"),
  }));
}

/** Collect every custom property declared on :root (last wins). */
function collectTokens(sheets) {
  const tokens = new Map();
  for (const { text } of sheets) {
    const root = postcss.parse(text);
    root.walkRules((rule) => {
      if (!rule.selectors.some((s) => s.trim() === ":root")) return;
      rule.walkDecls((decl) => {
        if (decl.prop.startsWith("--")) tokens.set(decl.prop, decl.value.trim());
      });
    });
  }
  return tokens;
}

/** Resolve var(--x), var(--x, fallback) recursively. Unknown tokens are
 *  left as-is so a typo shows up as an unresolvable value instead of
 *  silently becoming "transparent". */
export function resolveVars(value, tokens, depth = 0) {
  if (depth > 12 || !value.includes("var(")) return value;
  const out = value.replace(/var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)/g, (_, name, fallback) => {
    if (tokens.has(name)) return tokens.get(name);
    if (fallback != null) return fallback;
    return `var(${name})`;
  });
  return out === value ? out : resolveVars(out, tokens, depth + 1);
}

/**
 * Build the CSS text to inject.
 *  - every declaration's var() references are resolved,
 *  - @media blocks are collected separately (see LIMITS below) because a
 *    jsdom document has no viewport, so a media query cannot be evaluated
 *    honestly there.
 */
export function loadStyles({ keepMedia = false } = {}) {
  const sheets = readSheets();
  const tokens = collectTokens(sheets);
  const media = [];
  const chunks = [];

  for (const { name, text } of sheets) {
    const root = postcss.parse(text);
    root.walkAtRules("media", (at) => {
      const copy = at.clone();
      copy.walkDecls((decl) => {
        decl.value = resolveVars(decl.value, tokens);
      });
      media.push({ file: name, params: at.params, css: copy.toString() });
      at.remove();
    });
    root.walkDecls((decl) => {
      decl.value = resolveVars(decl.value, tokens);
    });
    chunks.push(`/* ${name} */\n${root.toString()}`);
  }

  return {
    css: chunks.join("\n"),
    media,
    styleText: keepMedia
      ? `${chunks.join("\n")}\n${media.map((entry) => entry.css).join("\n")}`
      : chunks.join("\n"),
  };
}

/** Inject the resolved CSS into a jsdom document (idempotent per document). */
export function installStyles(document) {
  const existing = document.getElementById("__cascade_css__");
  if (existing) return existing;
  const style = document.createElement("style");
  style.id = "__cascade_css__";
  style.textContent = loadStyles().styleText;
  document.head.appendChild(style);
  return style;
}

/* ------------------------------------------------------------------ color */

/** "rgb(1, 2, 3)" | "rgba(1, 2, 3, 0.5)" | "#rrggbb" -> {r,g,b,a} | null */
export function parseColor(value) {
  if (!value) return null;
  const text = String(value).trim().toLowerCase();
  if (text === "transparent") return { r: 0, g: 0, b: 0, a: 0 };
  let m = text.match(/^rgba?\(([^)]+)\)$/);
  if (m) {
    const parts = m[1].split(",").map((p) => p.trim());
    const [r, g, b] = parts.slice(0, 3).map(Number);
    const a = parts.length > 3 ? Number(parts[3]) : 1;
    if ([r, g, b].some((n) => Number.isNaN(n))) return null;
    return { r, g, b, a: Number.isNaN(a) ? 1 : a };
  }
  m = text.match(/^#([0-9a-f]{3})$/);
  if (m) {
    return {
      r: parseInt(m[1][0] + m[1][0], 16),
      g: parseInt(m[1][1] + m[1][1], 16),
      b: parseInt(m[1][2] + m[1][2], 16),
      a: 1,
    };
  }
  m = text.match(/^#([0-9a-f]{6})$/);
  if (m) {
    return {
      r: parseInt(m[1].slice(0, 2), 16),
      g: parseInt(m[1].slice(2, 4), 16),
      b: parseInt(m[1].slice(4, 6), 16),
      a: 1,
    };
  }
  // jsdom returns CSS system colors for elements with no author color
  // (buttons/inputs). A browser paints those black-on-light-grey; the
  // audit treats them as black text on the element's own/ancestor
  // background, which is the light surface they really sit on.
  if (["canvastext", "buttontext", "black", "menutext"].includes(text)) return { r: 0, g: 0, b: 0, a: 1 };
  if (text === "white") return { r: 255, g: 255, b: 255, a: 1 };
  if (["buttonface", "canvas"].includes(text)) return { r: 239, g: 239, b: 239, a: 1 };
  return null;
}

/** WCAG 2.1 relative luminance. */
export function luminance({ r, g, b }) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

/** WCAG 2.1 contrast ratio between two opaque colors. */
export function contrastRatio(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Flatten a translucent color over an opaque backdrop (alpha compositing). */
export function over(fg, bg) {
  if (fg.a >= 1) return { r: fg.r, g: fg.g, b: fg.b, a: 1 };
  return {
    r: Math.round(fg.r * fg.a + bg.r * (1 - fg.a)),
    g: Math.round(fg.g * fg.a + bg.g * (1 - fg.a)),
    b: Math.round(fg.b * fg.a + bg.b * (1 - fg.a)),
    a: 1,
  };
}

/** Foreground color of an element as the DOM engine computes it.
 *  jsdom returns the literal keyword for the two CSS-wide values the real
 *  cascade resolves for us (`inherit` from globals.css's `a { color:
 *  inherit }`, `currentcolor`); both mean "the parent's computed color",
 *  so we walk up -- exactly what the browser does. */
export function computedForeground(window, el) {
  let node = el;
  while (node && node.nodeType === 1) {
    const value = window.getComputedStyle(node).color;
    if (value !== "inherit" && value !== "currentcolor") {
      const parsed = parseColor(value);
      if (parsed) return parsed;
      throw new Error(`unresolvable color "${value}" on <${node.tagName.toLowerCase()}>`);
    }
    node = node.parentElement;
  }
  return { r: 0, g: 0, b: 0, a: 1 };
}

/**
 * Background an element's text actually sits on: the first ANCESTOR whose
 * computed background-color is not fully transparent, composited over the
 * next one, ... down to the document root.
 */
export function computedBackdrop(window, el) {
  const layers = [];
  let node = el;
  while (node && node.nodeType === 1) {
    const value = window.getComputedStyle(node).backgroundColor;
    const parsed = parseColor(value);
    if (parsed && parsed.a > 0) layers.push(parsed);
    if (parsed && parsed.a >= 1) break;
    node = node.parentElement;
  }
  let result = { r: 255, g: 255, b: 255, a: 1 };
  for (let i = layers.length - 1; i >= 0; i -= 1) result = over(layers[i], result);
  return result;
}

/**
 * Elements that RENDER text: an element is audited only when it has text of
 * its own that no element child also owns (so a container is never reported
 * on behalf of its children, and every visible string is checked exactly
 * once, at the element that paints it).
 */
export function textBlocks(root) {
  const out = [];
  const walk = (el) => {
    for (const child of el.children) {
      if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(child.tagName)) continue;
      if (child.getAttribute("aria-hidden") === "true") continue;
      if (!(child.textContent || "").trim()) continue;
      const ownsText =
        [...child.childNodes].some((node) => node.nodeType === 3 && node.textContent.trim()) ||
        ![...child.children].some((grand) => (grand.textContent || "").trim());
      if (ownsText) out.push(child);
      walk(child);
    }
  };
  walk(root);
  return out;
}

/** WCAG "large text": >= 24px, or >= 18.66px and bold. */
export function isLargeText(window, el) {
  const style = window.getComputedStyle(el);
  const size = parseFloat(style.fontSize) || 0;
  const weight = Number(style.fontWeight) || 400;
  return size >= 24 || (size >= 18.66 && weight >= 700);
}

/**
 * Run the audit over the mounted subtree. Returns one row per checked text
 * element: { el, tag, text, fg, bg, ratio, large, pass }.
 */
export function auditContrast(window, root, { minNormal = 4.5, minLarge = 3 } = {}) {
  const rows = [];
  for (const el of textBlocks(root)) {
    const own = (el.textContent || "").trim();
    if (!own) continue;
    const fg = computedForeground(window, el);
    const bg = computedBackdrop(window, el);
    const ratio = contrastRatio(fg, bg);
    const large = isLargeText(window, el);
    const min = large ? minLarge : minNormal;
    rows.push({
      el,
      tag: el.tagName.toLowerCase(),
      text: own.slice(0, 60),
      fg,
      bg,
      ratio,
      large,
      min,
      pass: ratio >= min,
    });
  }
  return rows;
}

export const fmt = ({ r, g, b }) => `rgb(${r}, ${g}, ${b})`;

/* --------------------------------------------------- raw rule lookup */
/**
 * Everything above leans on window.getComputedStyle(), which is the right
 * engine for colors but which jsdom does not implement for every property
 * (`backdrop-filter` is missing entirely on this jsdom/cssstyle version --
 * it comes back as an empty string). For those, the winning declaration is
 * resolved here from the SAME parsed rules: selector matching still goes
 * through the DOM (`el.matches`), and order/specificity/!important are
 * compared the way the cascade does.
 */
let ruleCache = null;

function rules() {
  if (ruleCache) return ruleCache;
  const sheets = readSheets();
  const tokens = collectTokens(sheets);
  const collected = [];
  let order = 0;
  const push = (rule) => {
    const decls = new Map();
    rule.walkDecls((decl) => {
      decls.set(decl.prop, { value: resolveVars(decl.value, tokens), important: decl.important });
    });
    const selectors = (rule.selector || "").split(",").map((s) => s.trim()).filter(Boolean);
    collected.push({ selectors, decls, order: order++, media: rule.__media || null });
  };

  for (const { text } of sheets) {
    const root = postcss.parse(text);
    root.walkAtRules("media", (at) => {
      at.walkRules((rule) => {
        rule.__media = at.params;
        push(rule);
      });
    });
    root.walkRules((rule) => {
      if (!rule.__media) push(rule);
    });
  }
  ruleCache = { collected };
  return ruleCache;
}

/** a=ids, b=classes/attributes/pseudo-classes, c=elements/pseudo-elements. */
export function specificity(selector) {
  const cleaned = selector
    .replace(/:where\([^)]*\)/g, "")
    .replace(/::[\w-]+/g, " ::pseudo ")
    .replace(/:not\(([^)]*)\)/g, " $1 ");
  const ids = (cleaned.match(/#[\w-]+/g) || []).length;
  const classes = (cleaned.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) || []).length;
  const types = (cleaned.match(/(^|[\s>+~(])([a-z][\w-]*)/gi) || []).length;
  return ids * 10000 + classes * 100 + types;
}

/**
 * The declaration that wins for `prop` on `el` in the authored CSS, or null
 * when no rule matches. Media-query rules are reported with their condition
 * so callers can decide (jsdom has no viewport to evaluate them).
 */
export function winningDeclaration(el, prop, { includeMedia = true } = {}) {
  const { collected } = rules();
  let best = null;
  for (const rule of collected) {
    if (!includeMedia && rule.media) continue;
    if (!rule.decls.has(prop)) continue;
    const selector = rule.selectors.find((sel) => {
      try {
        return el.matches(sel);
      } catch {
        return false;
      }
    });
    if (!selector) continue;
    const decl = rule.decls.get(prop);
    const candidate = {
      value: decl.value,
      important: decl.important,
      specificity: specificity(selector),
      order: rule.order,
      selector,
      media: rule.media,
    };
    if (
      !best ||
      (candidate.important && !best.important) ||
      (candidate.important === best.important &&
        (candidate.specificity > best.specificity ||
          (candidate.specificity === best.specificity && candidate.order > best.order)))
    ) {
      best = candidate;
    }
  }
  return best;
}

/** Properties that turn an element into a containing block for fixed
 *  descendants (CSS filter-effects / transform / containment), which is
 *  what broke the drawers inside the blurred header. */
export const CONTAINING_BLOCK_PROPS = [
  "backdrop-filter",
  "-webkit-backdrop-filter",
  "filter",
  "transform",
  "perspective",
  "contain",
  "will-change",
];

/** The ancestor (or null) that would capture a fixed-position descendant. */
export function containingBlockAncestor(el) {
  let node = el.parentElement;
  while (node && node.nodeType === 1) {
    for (const prop of CONTAINING_BLOCK_PROPS) {
      const computed = window_getComputed(node, prop);
      if (computed && computed !== "none" && computed !== "auto") return { node, prop, value: computed };
      const declared = winningDeclaration(node, prop);
      if (declared && declared.value !== "none" && declared.value !== "auto") {
        // "will-change: transform" only creates a containing block when it
        // names transform/filter/perspective; "contain" only for
        // layout/paint/strict/content.
        if (prop === "will-change" && !/transform|filter|perspective/.test(declared.value)) continue;
        if (prop === "contain" && /^(none)$/.test(declared.value)) continue;
        return { node, prop, value: declared.value };
      }
    }
    node = node.parentElement;
  }
  return null;
}

/** getComputedStyle without a window in scope (jsdom exposes one globally
 *  inside a vitest jsdom environment, but the helper is also used on a
 *  window built by hand in scripts). */
function window_getComputed(node, prop) {
  try {
    const style = (node.ownerDocument.defaultView || globalThis.window).getComputedStyle(node);
    return style.getPropertyValue(prop);
  } catch {
    return "";
  }
}

/** Every element in the subtree that is positioned fixed. */
export function fixedElements(root) {
  const out = [];
  const walk = (el) => {
    for (const child of el.children) {
      const position = window_getComputed(child, "position");
      if (position === "fixed") out.push(child);
      walk(child);
    }
  };
  walk(root);
  return out;
}
