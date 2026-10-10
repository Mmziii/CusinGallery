/*
 * Source-level guard for the browser rule that transforms, filters and paint
 * containment create containing blocks for fixed descendants. jsdom cannot
 * inspect pseudo-element styles, so parse the authored stylesheet directly.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import postcss from "postcss";
import { describe, expect, it } from "vitest";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CSS = ["globals.css", "storefront.css"]
  .map((file) => fs.readFileSync(path.join(HERE, file), "utf8"))
  .join("\n");
const root = postcss.parse(CSS);
const CONTAINING_BLOCK_PROPS = new Set([
  "backdrop-filter",
  "-webkit-backdrop-filter",
  "filter",
  "transform",
  "will-change",
  "perspective",
  "contain",
]);

function declarationsFor(selector) {
  const declarations = [];
  root.walkRules((rule) => {
    if ((rule.selectors || []).map((value) => value.trim()).includes(selector)) {
      rule.walkDecls((decl) => declarations.push({ prop: decl.prop, value: decl.value.trim() }));
    }
  });
  return declarations;
}

function valuesFor(selector, property) {
  return declarationsFor(selector).filter((decl) => decl.prop === property).map((decl) => decl.value);
}

const SHELL_TERMINALS = [
  ".site-header",
  ".site-header--compact",
  ".site-header__inner",
  ".app-shell",
  ".app-shell__main",
  ".route-fade",
  ".body-wrapper",
  "#root",
  "html",
  "body",
];

function targetsShellAncestor(selector) {
  const terminal = selector.trim().split(/[\s>+~]+/).at(-1);
  if (!terminal || terminal.includes("::")) return false;
  return SHELL_TERMINALS.some((target) =>
    terminal === target || terminal.startsWith(`${target}.`) || terminal.startsWith(`${target}[`) || terminal.startsWith(`${target}:`)
  );
}

describe("fixed UI stylesheet guard", () => {
  it("keeps the blur on the compact-header pseudo-element, never on the header", () => {
    const pseudo = declarationsFor(".site-header--compact::before");
    expect(pseudo).toEqual(expect.arrayContaining([
      { prop: "-webkit-backdrop-filter", value: "blur(12px)" },
      { prop: "backdrop-filter", value: "blur(12px)" },
    ]));

    const blurRules = [];
    root.walkRules((rule) => {
      rule.walkDecls((decl) => {
        if (["backdrop-filter", "-webkit-backdrop-filter"].includes(decl.prop)) {
          blurRules.push(...(rule.selectors || []).map((selector) => selector.trim()));
        }
      });
    });
    expect(blurRules).toEqual([".site-header--compact::before", ".site-header--compact::before"]);
  });

  it("keeps shell ancestors free of fixed-containing-block properties", () => {
    const forbidden = [];
    root.walkRules((rule) => {
      for (const selector of rule.selectors || []) {
        if (!targetsShellAncestor(selector)) continue;
        rule.walkDecls((decl) => {
          if (CONTAINING_BLOCK_PROPS.has(decl.prop)) {
            forbidden.push({ selector: selector.trim(), prop: decl.prop, value: decl.value.trim() });
          }
        });
      }
    });
    expect(forbidden, "shell ancestors must not capture fixed or portaled UI").toEqual([]);

    // MainLayout adds .route-fade to the app-shell main. An opacity-only
    // animation is safe for the product page's fixed mobile buy bar.
    const routeFrames = [];
    root.walkAtRules("keyframes", (atRule) => {
      if (atRule.params === "route-in") atRule.walkDecls((decl) => routeFrames.push(decl.prop));
    });
    expect(routeFrames).not.toContain("transform");
  });

  it("keeps both drawer roots viewport-sized, scrollable, and paired with a compensated body lock", () => {
    for (const selector of [".site-header__drawer", ".minicart"]) {
      expect(valuesFor(selector, "height"), `${selector} viewport fallback and dynamic height`).toEqual(
        expect.arrayContaining(["100vh", "100dvh"])
      );
    }
    expect(valuesFor(".site-header__drawer", "overflow-y")).toContain("auto");
    expect(valuesFor(".site-header__drawer", "overscroll-behavior")).toContain("contain");
    expect(valuesFor("body.body--scroll-locked", "overflow")).toContain("hidden");
    expect(valuesFor("body.body--scroll-locked", "padding-inline-end")).toContain(
      "var(--overlay-scrollbar-compensation, 0px)"
    );
  });
});
